# src/spotify_downloader.py
"""Handles Spotify API interaction and song downloading/processing orchestration."""

import os
import re
import logging
import json # For saving metadata
import tempfile # For temporary cover art
import shutil # For cleaning up temp_download_folder if it has contents
from dataclasses import dataclass, field

import requests # For downloading cover art
import spotipy
from spotipy.cache_handler import CacheFileHandler
from spotipy.oauth2 import SpotifyOAuth, SpotifyOauthError
import yt_dlp

from .config import (
    SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET, SPOTIPY_REDIRECT_URI, SPOTIFY_SCOPES, SPOTIFY_TOKEN_CACHE,
    DEFAULT_DOWNLOAD_DIR, DEFAULT_AUDIO_FORMAT, MIN_SOURCE_BITRATE_KBPS,
    YTDLP_COOKIES_FROM_BROWSER, YTDLP_COOKIES_FILE,
)
from .utils import sanitize_filename, ensure_dir_exists, describe_ytdlp_error, format_duration
from .audio_processor import (
    FFMPEG_TOOLS, DEFAULT_DURATION_TOLERANCE_MS, AudioProcessingError,
    choose_output_bitrate_kbps, convert_to_mp3, describe_quality, probe_audio, validate_mp3,
)
from .external_tools import find_js_runtimes

logger = logging.getLogger(__name__)

# How many search results to check per source (SoundCloud, YouTube)
MAX_SEARCH_RESULTS_PER_SOURCE = 3
SOURCES = (("SoundCloud", "scsearch"), ("YouTube", "ytsearch"))

_LINK_PREFIX = r"(?:spotify:|(?:https?://)?open\.spotify\.com/(?:intl-[A-Za-z-]+/)?)"
_PLAYLIST_LINK_RE = re.compile(_LINK_PREFIX + r"(?:user[:/][^:/]+[:/])?playlist[:/]([0-9A-Za-z]+)")
_OTHER_LINK_RE = re.compile(_LINK_PREFIX + r"(track|album|artist|show|episode|audiobook)[:/]")
_SPOTIFY_ID_RE = re.compile(r"[0-9A-Za-z]{22}")


class PlaylistFetchError(Exception):
    """The playlist couldn't be read; the message explains why and how to fix it."""


class CandidateRejected(Exception):
    """A search result was skipped or failed to download/convert; the message says why."""


@dataclass
class DownloadResult:
    path: str | None = None
    source: str | None = None
    quality: str | None = None  # e.g. "MP3 128 kbps (source: mp3 ~128 kbps)"
    failures: list[str] = field(default_factory=list)  # why each source / search result didn't work
    warnings: list[str] = field(default_factory=list)  # non-fatal problems, e.g. missing cover art


def parse_playlist_id(link: str) -> str:
    """Accepts open.spotify.com playlist URLs, spotify:playlist: URIs and bare IDs."""
    link = link.strip()
    if match := _PLAYLIST_LINK_RE.search(link):
        return match.group(1)
    if _SPOTIFY_ID_RE.fullmatch(link):
        return link
    if match := _OTHER_LINK_RE.search(link):
        raise PlaylistFetchError(f"That is a Spotify {match.group(1)} link; only playlist links are supported.")
    raise PlaylistFetchError(
        f"'{link}' is not a Spotify playlist link. Expected something like "
        "https://open.spotify.com/playlist/<id> or spotify:playlist:<id> (short spotify.link URLs "
        "must be opened in a browser first to get the full link).")


def explain_spotify_error(error: spotipy.SpotifyException) -> str:
    status = error.http_status
    # spotipy prefixes the message with the request URL; the last line is Spotify's reason.
    detail = str(error.msg).strip().splitlines()[-1].strip() if error.msg else ""
    reason = f"HTTP {status}" + (f": {detail}" if detail else "")
    if status == 401:
        return (f"Spotify rejected the login ({reason}). Delete the saved login at {SPOTIFY_TOKEN_CACHE} "
                "and run again to log in fresh.")
    if status == 403:
        return (f"Spotify refused access to this playlist ({reason}). Since Spotify's February 2026 API "
                "changes, apps in Development Mode can only read playlists that the logged-in account owns "
                "or collaborates on. To download someone else's playlist, open it in Spotify, choose "
                "'...' > 'Add to other playlist' > 'New playlist', and use the new playlist's link. Also make "
                "sure the Spotify account that created the app has Premium, and, if you didn't create the "
                "app yourself, that your account is added under 'User Management' in the app's dashboard.")
    if status == 404:
        return (f"Spotify couldn't find this playlist ({reason}). Check the link. Playlists made by Spotify "
                "itself (editorial and 'Made For You' mixes, whose IDs start with 37i9dQZF) aren't available "
                "to third-party apps; copy their songs into a playlist of your own instead.")
    if status == 429:
        return f"Spotify is rate-limiting requests ({reason}). Wait a few minutes and try again."
    return f"Spotify API error ({reason})."


def explain_oauth_error(error: SpotifyOauthError) -> str:
    code = getattr(error, "error", None)
    description = getattr(error, "error_description", None) or str(error)
    if code == "invalid_client":
        return (f"Spotify rejected the app credentials ({description}). Check SPOTIPY_CLIENT_ID and "
                "SPOTIPY_CLIENT_SECRET in .env against your app in the Spotify Developer Dashboard.")
    if code == "invalid_grant":
        return (f"Spotify rejected the saved login ({description}). This happens when access was revoked or "
                f"the redirect URI changed. Delete {SPOTIFY_TOKEN_CACHE} and run again to log in.")
    if code == "access_denied":
        return "The Spotify login was cancelled. Run again and click 'Agree' so Music Ripper can read your playlists."
    return (f"Spotify login failed ({description}). Make sure SPOTIPY_REDIRECT_URI ({SPOTIPY_REDIRECT_URI}) "
            "exactly matches a Redirect URI in your app's settings on the Spotify Developer Dashboard.")


def _codec_name(acodec: str | None) -> str | None:
    if not acodec or acodec == "none":
        return None
    return "aac" if acodec.startswith("mp4a") else acodec


class SpotifyDownloader:
    def __init__(self, client_id: str = None, client_secret: str = None, redirect_uri: str = None,
                 open_browser: bool = True):
        self.client_id = client_id or SPOTIPY_CLIENT_ID
        self.client_secret = client_secret or SPOTIPY_CLIENT_SECRET
        self.redirect_uri = redirect_uri or SPOTIPY_REDIRECT_URI

        if not self.client_id or not self.client_secret:
            logger.error("Spotify API client ID or secret not configured.")
            raise ValueError("Spotify API client ID or secret not configured.")

        # Reading playlist items requires a user login (Authorization Code flow); the
        # app-only Client Credentials flow now gets "401 Valid user authentication required".
        self.auth_manager = SpotifyOAuth(
            client_id=self.client_id,
            client_secret=self.client_secret,
            redirect_uri=self.redirect_uri,
            scope=SPOTIFY_SCOPES,
            cache_handler=CacheFileHandler(cache_path=SPOTIFY_TOKEN_CACHE),
            open_browser=open_browser,
        )
        self.sp = spotipy.Spotify(auth_manager=self.auth_manager)
        self.js_runtimes = find_js_runtimes()
        logger.info("Spotify client initialized successfully.")

    def has_cached_login(self) -> bool:
        """True if a saved Spotify login can be used without opening the browser."""
        try:
            cached = self.auth_manager.cache_handler.get_cached_token()
            return self.auth_manager.validate_token(cached) is not None
        except (SpotifyOauthError, spotipy.SpotifyException, requests.exceptions.RequestException):
            return False

    def get_playlist_tracks(self, playlist_url: str) -> list[dict]:
        """Returns the playlist's tracks; raises PlaylistFetchError with an explanation on failure."""
        playlist_id = parse_playlist_id(playlist_url)
        try:
            # spotipy >= 2.26 uses GET /playlists/{id}/items (the old /tracks endpoint was removed).
            results = self.sp.playlist_items(playlist_id, additional_types=("track",))
            items = results['items']
            while results['next']:
                results = self.sp.next(results)
                items.extend(results['items'])
        except SpotifyOauthError as e:
            logger.error(f"Spotify login failed: {e}")
            raise PlaylistFetchError(explain_oauth_error(e)) from e
        except spotipy.SpotifyException as e:
            logger.error(f"Error fetching playlist tracks from {playlist_url}: {e}")
            raise PlaylistFetchError(explain_spotify_error(e)) from e
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error fetching playlist tracks from {playlist_url}: {e}")
            raise PlaylistFetchError(f"Could not reach Spotify ({e}). Check your internet connection.") from e

        track_list = []
        for item in items:
            # Spotify renamed "track" to "item" in February 2026; "track" is deprecated.
            track = (item or {}).get('item') or (item or {}).get('track')
            if track and track.get('name') and track.get('artists') and track.get('duration_ms'):
                track_name = track['name']
                artists = ", ".join([artist['name'] for artist in track['artists']])
                duration_ms = track['duration_ms']
                album_info = track.get('album', {})
                album_name = album_info.get('name')
                track_number = track.get('track_number')
                release_date = album_info.get('release_date')
                year = release_date.split('-')[0] if release_date else None
                cover_art_url = images[0].get('url') if (images := album_info.get('images', [])) else None

                track_list.append({
                    "name": track_name, "artist": artists, "duration_ms": duration_ms,
                    "album": album_name, "track_number": str(track_number) if track_number else None,
                    "year": year, "cover_art_url": cover_art_url,
                    "spotify_track_id": track.get('id') # Store Spotify ID for reference
                })
        logger.info(f"Fetched {len(track_list)} tracks with extended metadata from: {playlist_url}")
        return track_list

    def _ydl_options(self, **extra) -> dict:
        opts = {
            'quiet': True,
            'noprogress': True,
            'noplaylist': True,
            'logger': logger,
        }
        if self.js_runtimes: # yt-dlp only enables Deno by default; allow whatever is installed
            opts['js_runtimes'] = self.js_runtimes
        if FFMPEG_TOOLS.ffmpeg:
            opts['ffmpeg_location'] = os.path.dirname(FFMPEG_TOOLS.ffmpeg)
        if YTDLP_COOKIES_FILE:
            opts['cookiefile'] = YTDLP_COOKIES_FILE
        elif YTDLP_COOKIES_FROM_BROWSER:
            browser, _, profile = YTDLP_COOKIES_FROM_BROWSER.partition(":")
            opts['cookiesfrombrowser'] = (browser.strip().lower(), profile.strip() or None)
        opts.update(extra)
        return opts

    def _search(self, search_prefix: str, query: str) -> list[dict]:
        """Lists the top search results; raises yt_dlp.utils.DownloadError if the search fails."""
        # extract_flat lists results without resolving each one, so a single
        # unavailable video can't abort the whole search.
        with yt_dlp.YoutubeDL(self._ydl_options(extract_flat='in_playlist')) as ydl:
            results = ydl.extract_info(f"{search_prefix}{MAX_SEARCH_RESULTS_PER_SOURCE}:{query}", download=False)
        entries = [entry for entry in (results or {}).get('entries') or [] if entry]
        return entries[:MAX_SEARCH_RESULTS_PER_SOURCE]

    def _download_candidate(self, entry: dict, track_info: dict, output_template: str) -> tuple[str, str, float | None, str | None]:
        """
        Pre-filters one search result and downloads its best audio stream.
        Returns (raw file path, source URL, source bitrate in kbps, source codec).
        Raises CandidateRejected explaining why the result can't be used.
        """
        entry_url = entry.get('webpage_url') or entry.get('url')
        if not entry_url:
            raise CandidateRejected("search result has no URL")

        expected_ms = track_info.get('duration_ms')
        entry_duration_sec = entry.get('duration') # Duration in seconds from yt-dlp
        if expected_ms and entry_duration_sec is not None and \
                abs(entry_duration_sec * 1000 - expected_ms) > DEFAULT_DURATION_TOLERANCE_MS:
            raise CandidateRejected(
                f"length {format_duration(entry_duration_sec * 1000)} doesn't match Spotify's "
                f"{format_duration(expected_ms)} (likely a different version, a preview or a mix)")

        ydl_opts = self._ydl_options(
            format='bestaudio/best',
            # Rank audio by bitrate first; otherwise yt-dlp prefers Opus, e.g. picking
            # SoundCloud's 64 kbps Opus stream over its 128 kbps MP3 stream.
            format_sort=['abr'],
            outtmpl=output_template,
        )
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(entry_url, download=False)
            except yt_dlp.utils.DownloadError as e:
                raise CandidateRejected(f"could not load track details: {describe_ytdlp_error(e)}") from e

            if 'preview' in str(info.get('format_id') or '').lower():
                raise CandidateRejected("only a 30-second preview is available (SoundCloud Go+ track)")
            source_kbps = info.get('abr')
            if source_kbps is None and info.get('vcodec') in (None, 'none'): # audio only: total bitrate is the audio bitrate
                source_kbps = info.get('tbr')
            if source_kbps is not None and source_kbps < MIN_SOURCE_BITRATE_KBPS:
                raise CandidateRejected(
                    f"best available audio is only {source_kbps:.0f} kbps (minimum is {MIN_SOURCE_BITRATE_KBPS} kbps)")

            logger.info(f"Downloading '{info.get('title')}' ({entry_url}), format {info.get('format_id')}, "
                        f"reported bitrate {source_kbps} kbps")
            try:
                info = ydl.process_ie_result(info, download=True)
            except yt_dlp.utils.DownloadError as e:
                raise CandidateRejected(f"download failed: {describe_ytdlp_error(e)}") from e

            downloads = info.get('requested_downloads') or [{}]
            raw_path = downloads[0].get('filepath') or ydl.prepare_filename(info)

        if not raw_path or not os.path.exists(raw_path) or os.path.getsize(raw_path) == 0:
            raise CandidateRejected("download finished but no audio file was written")
        return raw_path, entry_url, source_kbps, _codec_name(info.get('acodec'))

    def _process_candidate(self, entry: dict, track_info: dict, work_dir: str, attempt_name: str,
                           final_mp3_path: str, source_name: str, cover_image_path: str | None) -> dict:
        """Downloads, converts and validates one search result. Returns quality metadata."""
        raw_path, source_url, source_kbps, source_codec = self._download_candidate(
            entry, track_info, os.path.join(work_dir, f"{attempt_name}.%(ext)s"))

        if not source_kbps: # the site didn't report it; measure the downloaded file instead
            try:
                probed = probe_audio(raw_path)
                source_kbps, source_codec = probed.bitrate_kbps, source_codec or probed.codec
            except AudioProcessingError as e:
                logger.warning(f"Could not measure source bitrate of {raw_path}: {e}")
            if source_kbps and source_kbps < MIN_SOURCE_BITRATE_KBPS:
                raise CandidateRejected(
                    f"downloaded audio is only {source_kbps:.0f} kbps (minimum is {MIN_SOURCE_BITRATE_KBPS} kbps)")

        output_kbps = choose_output_bitrate_kbps(source_kbps)
        quality = describe_quality(output_kbps, source_kbps, source_codec)
        try:
            convert_to_mp3(
                raw_path, final_mp3_path, output_kbps,
                artist=track_info['artist'], title=track_info['name'],
                album=track_info.get('album'), track_number=track_info.get('track_number'),
                year=track_info.get('year'), cover_image_path=cover_image_path,
                comment=f"Source: {source_name} {source_url} - {quality}",
            )
            validate_mp3(final_mp3_path, expected_bitrate_kbps=output_kbps,
                         expected_duration_ms=track_info.get('duration_ms'))
        except AudioProcessingError as e:
            if os.path.exists(final_mp3_path): # Clean up failed MP3 conversion
                try: os.remove(final_mp3_path)
                except OSError: logger.error(f"Could not remove failed MP3 {final_mp3_path}")
            raise CandidateRejected(str(e)) from e

        return {
            "download_source": source_name,
            "source_url": source_url,
            "source_codec": source_codec,
            "source_bitrate_kbps": round(source_kbps) if source_kbps else None,
            "output_bitrate_kbps": output_kbps,
            "quality": quality,
        }

    def _reuse_existing(self, final_mp3_path: str, metadata_json_path: str, track_info: dict) -> DownloadResult | None:
        logger.info(f"'{final_mp3_path}' already exists. Validating...")
        try:
            validate_mp3(final_mp3_path, expected_duration_ms=track_info.get('duration_ms'))
        except AudioProcessingError as e:
            logger.warning(f"Existing file '{final_mp3_path}' is invalid ({e}). Re-downloading.")
            return None

        logger.info(f"Existing file '{final_mp3_path}' is valid. Skipping download.")
        existing_meta = {}
        if os.path.exists(metadata_json_path):
            try:
                with open(metadata_json_path, 'r', encoding='utf-8') as f_json_read:
                    existing_meta = json.load(f_json_read)
            except (OSError, ValueError) as e:
                logger.warning(f"Could not read {metadata_json_path}: {e}")
        return DownloadResult(
            path=final_mp3_path,
            source=existing_meta.get('download_source', "Unknown/Existing"),
            quality=existing_meta.get('quality', "existing file (source quality unknown)"),
        )

    def _download_cover_art(self, track_info: dict, folder: str, result: DownloadResult) -> str | None:
        cover_art_url = track_info.get('cover_art_url')
        if not cover_art_url:
            return None
        try:
            response = requests.get(cover_art_url, stream=True, timeout=10)
            response.raise_for_status()
            # Spotify serves JPEGs without a file extension; pydub needs one to embed the cover.
            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg", dir=folder, prefix="cover_") as tmp_cover:
                for chunk in response.iter_content(chunk_size=8192):
                    tmp_cover.write(chunk)
            logger.info(f"Downloaded cover art to: {tmp_cover.name}")
            return tmp_cover.name
        except (requests.exceptions.RequestException, OSError) as e_cover:
            message = f"cover art could not be downloaded ({e_cover}); saved without it"
            logger.warning(f"{track_info['artist']} - {track_info['name']}: {message}")
            result.warnings.append(message)
            return None

    def download_song(self, track_info: dict, download_dir: str) -> DownloadResult:
        """Downloads one track, trying each source's search results in turn.

        On failure, DownloadResult.failures lists why every source and result was rejected.
        """
        ensure_dir_exists(download_dir)
        original_artist = track_info['artist']
        original_name = track_info['name']
        sanitized_track_name = sanitize_filename(f"{original_artist} - {original_name}")

        final_mp3_path = os.path.join(download_dir, f"{sanitized_track_name}.{DEFAULT_AUDIO_FORMAT}")
        metadata_json_path = os.path.join(download_dir, f"{sanitized_track_name}.json")

        if os.path.exists(final_mp3_path):
            existing = self._reuse_existing(final_mp3_path, metadata_json_path, track_info)
            if existing:
                return existing

        # Base temporary folder for this song, cleaned up at the end
        song_specific_temp_base = os.path.join(download_dir, f"_temp_dl_{sanitize_filename(track_info.get('spotify_track_id') or sanitized_track_name)}")
        if os.path.exists(song_specific_temp_base): # Clean if exists from a previous failed run for this song
            try: shutil.rmtree(song_specific_temp_base)
            except OSError: pass
        ensure_dir_exists(song_specific_temp_base)

        result = DownloadResult()
        query_parts = [original_artist, original_name]
        if track_info.get('album'):
            query_parts.append(track_info['album'])
        query_parts.append("Audio") # Consistently add "Audio" at the end
        search_query = " ".join(part for part in query_parts if part and part.strip())

        try:
            cover_image_path = self._download_cover_art(track_info, song_specific_temp_base, result)

            for source_name, search_prefix in SOURCES:
                logger.info(f"Searching top {MAX_SEARCH_RESULTS_PER_SOURCE} results on {source_name} for: {search_query}")
                try:
                    entries = self._search(search_prefix, search_query)
                except yt_dlp.utils.DownloadError as e:
                    result.failures.append(f"{source_name}: search failed: {describe_ytdlp_error(e)}")
                    continue
                if not entries:
                    result.failures.append(f"{source_name}: no search results for \"{search_query}\"")
                    continue

                for index, entry in enumerate(entries, 1):
                    label = f"{source_name} result {index} \"{entry.get('title') or 'untitled'}\""
                    try:
                        quality_meta = self._process_candidate(
                            entry, track_info, song_specific_temp_base,
                            f"{sanitize_filename(source_name)}_{index}", final_mp3_path,
                            source_name, cover_image_path)
                    except CandidateRejected as e:
                        logger.info(f"Rejected {label}: {e}")
                        result.failures.append(f"{label}: {e}")
                        continue
                    except Exception as e: # unexpected; log it and keep trying other results
                        logger.exception(f"Unexpected error processing {label}")
                        result.failures.append(f"{label}: unexpected error: {type(e).__name__}: {e}")
                        continue

                    logger.info(f"Successfully PROCESSED and VALIDATED from {source_name}: {final_mp3_path} ({quality_meta['quality']})")
                    result.path, result.source, result.quality = final_mp3_path, source_name, quality_meta['quality']
                    try:
                        with open(metadata_json_path, 'w', encoding='utf-8') as f_json:
                            json.dump({**track_info, **quality_meta}, f_json, ensure_ascii=False, indent=4)
                        logger.info(f"Saved metadata to: {metadata_json_path}")
                    except OSError as e_json:
                        logger.error(f"Failed to save metadata JSON for {final_mp3_path}: {e_json}")
                    return result
        finally:
            # After trying all sources, clean up the main temporary base folder for this song
            if os.path.exists(song_specific_temp_base):
                try:
                    shutil.rmtree(song_specific_temp_base)
                    logger.info(f"Cleaned up base temporary folder for song: {song_specific_temp_base}")
                except OSError as e_os:
                    logger.error(f"Error deleting base temporary folder {song_specific_temp_base}: {e_os}")

        logger.error(f"All download and processing attempts FAILED for: {original_artist} - {original_name}")
        for failure in result.failures:
            logger.error(f"  - {failure}")
        return result

# Example usage (for testing this module directly):
if __name__ == "__main__":
    # Run from the project root with: python -m src.spotify_downloader
    print("Testing SpotifyDownloader with iterative source attempts...")

    if not SPOTIPY_CLIENT_ID or not SPOTIPY_CLIENT_SECRET:
        print("Spotify API credentials not found. Skipping direct test.")
    else:
        downloader = SpotifyDownloader()
        # Must be a playlist you own or collaborate on (see README).
        test_playlist_url = os.getenv("TEST_PLAYLIST_URL", "")
        print(f"Fetching tracks from: {test_playlist_url}")
        try:
            tracks = downloader.get_playlist_tracks(test_playlist_url)
        except PlaylistFetchError as e:
            print(f"Could not fetch tracks for testing: {e}")
            tracks = []

        if tracks:
            test_download_folder = os.path.join(DEFAULT_DOWNLOAD_DIR, "SpotifyDownloaderTest_Iterative")
            ensure_dir_exists(test_download_folder)
            print(f"Test download folder: {test_download_folder}")

            # Test with the first 2 tracks from the playlist
            for i, track_to_test in enumerate(tracks[:2]):
                print(f"\n--- Downloading Test Track {i+1}: {track_to_test['artist']} - {track_to_test['name']} ---")
                outcome = downloader.download_song(track_to_test, test_download_folder)
                if outcome.path:
                    print(f"SUCCESS: Test track {i+1} downloaded from {outcome.source} to: {outcome.path} ({outcome.quality})")
                    print(f"File size: {os.path.getsize(outcome.path) / (1024*1024):.2f} MB")
                else:
                    print(f"FAILED: Test track {i+1} download failed:")
                    for failure in outcome.failures:
                        print(f"  - {failure}")
