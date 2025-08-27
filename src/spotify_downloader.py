# src/spotify_downloader.py
"""Handles Spotify API interaction and song downloading/processing orchestration."""

import os
import logging
import json # For saving metadata
import tempfile # For temporary cover art
import shutil # For cleaning up temp_download_folder if it has contents
import requests # For downloading cover art
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import yt_dlp

from .config import SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET, DEFAULT_DOWNLOAD_DIR, DEFAULT_AUDIO_FORMAT
from .utils import sanitize_filename, ensure_dir_exists
from .audio_processor import convert_to_mp3_320kbps, validate_mp3_320kbps

logger = logging.getLogger(__name__)

# How many search results to check per source (SoundCloud, YouTube)
MAX_SEARCH_RESULTS_PER_SOURCE = 3
MIN_DURATION_PREFILTER_SECONDS = 45 # Pre-filter: skip if source reports duration less than this
MIN_AUDIO_BITRATE_KBPS = 128      # Pre-filter: skip if source audio bitrate is less than this

class SpotifyDownloader:
    def __init__(self, client_id: str = None, client_secret: str = None):
        self.client_id = client_id or SPOTIPY_CLIENT_ID
        self.client_secret = client_secret or SPOTIPY_CLIENT_SECRET

        if not self.client_id or not self.client_secret:
            logger.error("Spotify API client ID or secret not configured.")
            raise ValueError("Spotify API client ID or secret not configured.")

        try:
            auth_manager = SpotifyClientCredentials(client_id=self.client_id, client_secret=self.client_secret)
            self.sp = spotipy.Spotify(auth_manager=auth_manager)
            logger.info("Spotify client initialized successfully.")
        except Exception as e:
            logger.error(f"Error initializing Spotify client: {e}")
            raise

    def get_playlist_tracks(self, playlist_url: str) -> list[dict]:
        track_list = []
        try:
            playlist_id = playlist_url.split("/")[-1].split("?")[0]
            results = self.sp.playlist_items(playlist_id)
            items = results['items']
            while results['next']:
                results = self.sp.next(results)
                items.extend(results['items'])
            
            for item in items:
                track = item.get('track')
                if track and track.get('name') and track.get('artists') and track.get('duration_ms'):
                    track_name = track['name']
                    # Use a generator expression here to avoid an extra list allocation;
                    # join accepts any iterable and this avoids creating a temporary list of artist names.
                    # Microbenchmark: for small numbers of artists the difference is tiny, but in hot paths
                    # this reduces temporary allocations and memory churn.
                    artists = ", ".join(artist['name'] for artist in track['artists'])
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
        except Exception as e:
            logger.error(f"Error fetching playlist tracks from {playlist_url}: {e}")
        return track_list

    def _execute_download_attempt(self, track_info: dict, search_prefix_n: str, source_name: str, attempt_temp_folder: str) -> str | None:
        """
        Attempts to download a single song from N search results from a given source.
        Returns path to the raw downloaded audio file on first success, else None.
        """
        original_artist = track_info['artist']
        original_name = track_info['name']
        album_name = track_info.get('album')

        query_parts = [original_artist, original_name]
        if album_name:
            query_parts.append(album_name)
        query_parts.append("Audio") # Consistently add "Audio" at the end
        search_query_base = " ".join(part for part in query_parts if part and part.strip()) # Join non-empty, non-whitespace-only parts
        
        try:
            sanitized_track_name = sanitize_filename(f"{original_name} {original_artist}")
        except (TypeError, ValueError) as e:
            fallback_basename = os.path.basename(f"{original_name} {original_artist}") if isinstance(f"{original_name} {original_artist}", str) else str(f"{original_name} {original_artist}")
            logger.warning(f"sanitize_filename failed for track '{original_name} {original_artist}': {e}. Falling back to basename '{fallback_basename}'.")
            sanitized_track_name = fallback_basename

        ensure_dir_exists(attempt_temp_folder) # For individual raw downloads

        logger.info(f"Searching top {MAX_SEARCH_RESULTS_PER_SOURCE} results on {source_name} for: {search_query_base}")
        
        ydl_opts_meta = {
            'quiet': True, 
            'noplaylist': True, 
            'default_search': search_prefix_n, # e.g. scsearch3, ytsearch3
            'logger': logger,
            # 'match_filter': f'duration > {MIN_DURATION_PREFILTER_SECONDS}' # This applies to search query itself, might be too broad.
                                                                          # Better to filter after getting entries.
        }

        search_entries = []
        try:
            with yt_dlp.YoutubeDL(ydl_opts_meta) as ydl_meta:
                # extract_info with a search query and download=False should give us a list of entries
                meta_results = ydl_meta.extract_info(search_query_base, download=False)
                if meta_results and 'entries' in meta_results:
                    search_entries = meta_results['entries']
                elif meta_results and meta_results.get('webpage_url'): # Single result from search (e.g. if scsearch1 was used)
                    search_entries = [meta_results] # Treat as a list with one entry

        except yt_dlp.utils.DownloadError as de_meta:
            logger.warning(f"Could not fetch search results from {source_name} for '{search_query_base}': {de_meta}")
            return None
        except Exception as e_meta:
            logger.error(f"Unexpected error fetching search results from {source_name} for '{search_query_base}': {e_meta}")
            return None

        if not search_entries:
            logger.info(f"No search results found on {source_name} for: {search_query_base}")
            return None

        for i, entry in enumerate(search_entries):
            if i >= MAX_SEARCH_RESULTS_PER_SOURCE: # Should be redundant if search_prefix_n works as expected
                break

            entry_title = entry.get('title', 'Unknown Title')
            entry_url = entry.get('webpage_url') or entry.get('url')
            entry_duration_sec = entry.get('duration') # Duration in seconds from yt-dlp

            logger.info(f"Considering {source_name} search result {i+1}/{len(search_entries)}: '{entry_title}' (duration: {entry_duration_sec}s)")

            if not entry_url:
                logger.warning(f"Skipping search result {i+1} from {source_name} (no URL found).")
                continue

            if entry_duration_sec is not None and entry_duration_sec < MIN_DURATION_PREFILTER_SECONDS:
                logger.info(f"Skipping search result {i+1} from {source_name} ('{entry_title}') due to short duration ({entry_duration_sec}s < {MIN_DURATION_PREFILTER_SECONDS}s)." )
                continue
            
            # Pre-filter by audio bitrate before attempting full download of this specific entry
            try:
                logger.debug(f"Fetching detailed metadata for {source_name} entry: {entry_url} to check bitrate.")
                ydl_opts_entry_specific_meta = {
                    'quiet': True, 
                    'logger': logger, 
                    'format': 'bestaudio/best', # Ask yt-dlp to determine what it thinks is bestaudio
                    # 'extract_flat': 'in_playlist', # Faster if we only need top-level meta like ABR
                }
                with yt_dlp.YoutubeDL(ydl_opts_entry_specific_meta) as ydl_esm:
                    entry_specific_info = ydl_esm.extract_info(entry_url, download=False)
                
                selected_format_abr = entry_specific_info.get('abr') # abr for audio bitrate in kbps
                # Some sources might provide tbr (total bitrate) instead of abr if it's audio only.
                # Prefer abr if available.
                if selected_format_abr is None and entry_specific_info.get('vcodec') == 'none': # If audio only, tbr might be abr
                    selected_format_abr = entry_specific_info.get('tbr')

                logger.debug(f"Reported ABR/TBR for {entry_url}: {selected_format_abr} kbps")

                if selected_format_abr is not None and selected_format_abr < MIN_AUDIO_BITRATE_KBPS:
                    logger.info(f"Skipping search result {i+1} from {source_name} ('{entry_title}') due to low source bitrate ({selected_format_abr}kbps < {MIN_AUDIO_BITRATE_KBPS}kbps).")
                    continue
                elif selected_format_abr is None:
                    logger.warning(f"Could not determine audio bitrate for {source_name} entry '{entry_title}' ({entry_url}). Proceeding with download attempt.")
            except yt_dlp.utils.DownloadError as de_esm:
                logger.warning(f"Could not fetch specific metadata for bitrate check of {source_name} entry '{entry_title}' ({entry_url}): {de_esm}. Skipping this entry.")
                continue
            except Exception as e_esm:
                logger.error(f"Unexpected error fetching specific metadata for bitrate check of {source_name} entry '{entry_title}' ({entry_url}): {e_esm}. Skipping this entry.")
                continue
            
            # Path for this specific attempt's raw download
            # Use a unique name for each attempt to avoid overwriting within the attempt_temp_folder
            temp_output_template_entry = os.path.join(attempt_temp_folder, f"{sanitized_track_name}_attempt_{i+1}.%(ext)s")

            ydl_opts_download = {
                'format': 'bestaudio/best',
                'outtmpl': temp_output_template_entry,
                'quiet': True,
                'noplaylist': True, # Ensure we are downloading the specific entry
                'logger': logger,
                # No search, no match_filter here; we are downloading a specific URL
            }
            
            temp_downloaded_actual_path = None
            try:
                logger.info(f"Attempting to download specific entry from {source_name}: '{entry_title}' ({entry_url})")
                with yt_dlp.YoutubeDL(ydl_opts_download) as ydl_dl:
                    # Download the specific entry URL
                    download_info = ydl_dl.extract_info(entry_url, download=True)
                    # The actual path is determined by outtmpl and the extension yt-dlp chooses
                    temp_downloaded_actual_path = ydl_dl.prepare_filename(download_info)

                if temp_downloaded_actual_path and os.path.exists(temp_downloaded_actual_path):
                    logger.info(f"Successfully downloaded raw audio for entry {i+1} from {source_name} to {temp_downloaded_actual_path}")
                    return temp_downloaded_actual_path # Return path to raw audio
                else:
                    logger.warning(f"Download of entry {i+1} from {source_name} ('{entry_title}') seemed to complete but file not found.")

            except yt_dlp.utils.DownloadError as de_dl:
                logger.warning(f"Failed to download entry {i+1} ('{entry_title}') from {source_name}: {de_dl}")
            except Exception as e_dl:
                logger.error(f"Unexpected error downloading entry {i+1} ('{entry_title}') from {source_name}: {e_dl}")
            
            # If download failed for this entry, loop to the next one

        logger.info(f"All ({len(search_entries)}) search results from {source_name} for '{search_query_base}' failed pre-filter or download.")
        return None # All entries failed

    def download_song(self, track_info: dict, download_dir: str) -> tuple[str | None, str | None]:
        ensure_dir_exists(download_dir)
        original_artist = track_info['artist']
        original_name = track_info['name']
        try:
            sanitized_track_name = sanitize_filename(f"{original_artist} - {original_name}")
        except (TypeError, ValueError) as e:
            fallback_basename = os.path.basename(f"{original_artist} - {original_name}") if isinstance(f"{original_artist} - {original_name}", str) else str(f"{original_artist} - {original_name}")
            logger.warning(f"sanitize_filename failed for '{original_artist} - {original_name}': {e}. Falling back to basename '{fallback_basename}'.")
            sanitized_track_name = fallback_basename
        
        final_mp3_path = os.path.join(download_dir, f"{sanitized_track_name}.{DEFAULT_AUDIO_FORMAT}")
        metadata_json_path = os.path.join(download_dir, f"{sanitized_track_name}.json")

        # Base temporary folder for this song, cleaned up at the end
        id_candidate = track_info.get('spotify_track_id', sanitized_track_name)
        if id_candidate is None:
            id_candidate_basename = sanitized_track_name
        else:
            try:
                id_candidate_basename = os.path.basename(id_candidate) if isinstance(id_candidate, str) else str(id_candidate)
            except Exception:
                id_candidate_basename = str(id_candidate)

        try:
            sanitized_id = sanitize_filename(id_candidate_basename)
        except (TypeError, ValueError) as e:
            logger.warning(f"sanitize_filename failed for spotify_track_id '{id_candidate}': {e}. Falling back to basename '{id_candidate_basename}'.")
            sanitized_id = id_candidate_basename

        song_specific_temp_base = os.path.join(download_dir, f"_temp_dl_{sanitized_id}")
        if os.path.exists(song_specific_temp_base): # Clean if exists from a previous failed run for this song
            try: shutil.rmtree(song_specific_temp_base)
            except OSError: pass
        ensure_dir_exists(song_specific_temp_base)

        temp_cover_image_path = None
        final_validated_mp3_path = None
        successful_source_name = None

        if os.path.exists(final_mp3_path):
            logger.info(f"'{final_mp3_path}' already exists. Validating...")
            if validate_mp3_320kbps(final_mp3_path, expected_duration_ms=track_info.get('duration_ms')):
                logger.info(f"Existing file '{final_mp3_path}' is valid. Skipping download.")
                existing_source = "Unknown/Existing"
                if os.path.exists(metadata_json_path):
                    try:
                        with open(metadata_json_path, 'r', encoding='utf-8') as f_json_read:
                            existing_meta = json.load(f_json_read)
                            existing_source = existing_meta.get('download_source', existing_source)
                    except (json.JSONDecodeError, PermissionError, OSError) as e:
                        # Intentionally swallow expected read/parse errors for backwards compatibility:
                        # If metadata cannot be read (corrupt JSON, permission issues, etc.), preserve
                        # original behavior by keeping existing_source as default and proceeding without raising.
                        logger.debug(f"Could not read existing metadata JSON {metadata_json_path}: {e}")
                shutil.rmtree(song_specific_temp_base) # Clean up temp base if we skip
                return final_mp3_path, existing_source
            else:
                logger.warning(f"Existing file '{final_mp3_path}' is invalid. Re-downloading.")

        cover_art_url = track_info.get('cover_art_url')
        if cover_art_url:
            try:
                response = requests.get(cover_art_url, stream=True, timeout=10)
                response.raise_for_status()
                img_suffix = os.path.splitext(cover_art_url.split('?')[0])[-1] or '.jpg'
                with tempfile.NamedTemporaryFile(delete=False, suffix=img_suffix, dir=song_specific_temp_base, prefix="cover_") as tmp_cover:
                    for chunk in response.iter_content(chunk_size=8192):
                        tmp_cover.write(chunk)
                    temp_cover_image_path = tmp_cover.name
                logger.info(f"Downloaded cover art to: {temp_cover_image_path}")
            except Exception as e_cover:
                logger.warning(f"Failed to download cover art for {original_artist} - {original_name}: {e_cover}")

        sources_to_try = [
            ("SoundCloud", f"scsearch{MAX_SEARCH_RESULTS_PER_SOURCE}"),
            ("YouTube",    f"ytsearch{MAX_SEARCH_RESULTS_PER_SOURCE}")
        ]

        for source_name, search_prefix_n in sources_to_try:
            logger.info(f"Attempting source: {source_name} for '{original_artist} - {original_name}'")
            # Create a subfolder within song_specific_temp_base for this source's raw downloads
            # Replace concatenation with f-string to avoid temporary allocation from '+' operator in hot path.
            # Microbenchmark: f"{a}_{b}" slightly faster and avoids creating an intermediate string when compared to a + b.
            try:
                source_name_basename = os.path.basename(source_name) if isinstance(source_name, str) else str(source_name)
            except Exception:
                source_name_basename = str(source_name)
            try:
                safe_source_name = sanitize_filename(source_name_basename)
            except (TypeError, ValueError) as e:
                logger.warning(f"sanitize_filename failed for source name '{source_name}': {e}. Falling back to basename '{source_name_basename}'.")
                safe_source_name = source_name_basename

            source_attempt_temp_folder = os.path.join(song_specific_temp_base, f"{safe_source_name}_raw_downloads")
            
            raw_audio_path_from_source = self._execute_download_attempt(
                track_info, search_prefix_n, source_name, source_attempt_temp_folder
            )

            if raw_audio_path_from_source and os.path.exists(raw_audio_path_from_source):
                logger.info(f"Raw audio obtained from {source_name}: {raw_audio_path_from_source}. Converting and validating.")
                if convert_to_mp3_320kbps(
                    raw_audio_path_from_source, final_mp3_path, 
                    artist=original_artist, title=original_name,
                    album=track_info.get('album'), track_number=track_info.get('track_number'),
                    year=track_info.get('year'), cover_image_path=temp_cover_image_path
                ):
                    if validate_mp3_320kbps(final_mp3_path, expected_duration_ms=track_info.get('duration_ms')):
                        logger.info(f"Successfully PROCESSED and VALIDATED from {source_name}: {final_mp3_path}")
                        final_validated_mp3_path = final_mp3_path
                        successful_source_name = source_name
                        track_info['download_source'] = successful_source_name
                        try:
                            with open(metadata_json_path, 'w', encoding='utf-8') as f_json:
                                json.dump(track_info, f_json, ensure_ascii=False, indent=4)
                            logger.info(f"Saved metadata to: {metadata_json_path}")
                        except Exception as e_json:
                            logger.error(f"Failed to save metadata JSON for {final_mp3_path}: {e_json}")
                        break # Success, stop trying other sources
                    else:
                        logger.warning(f"Validation FAILED for {final_mp3_path} (from {source_name}). Will try next source if available.")
                        if os.path.exists(final_mp3_path): # Clean up failed MP3 conversion
                            try: os.remove(final_mp3_path)
                            except OSError: logger.error(f"Could not remove failed MP3 {final_mp3_path}")
                else:
                    logger.warning(f"Conversion to MP3 FAILED for raw audio from {source_name} ({raw_audio_path_from_source}). Will try next source if available.")
                # Raw audio from this source attempt is no longer needed or failed processing
                # shutil.rmtree(source_attempt_temp_folder) # Clean up specific raw download folder for this source is too aggressive here, base folder cleaned at end
            else:
                logger.info(f"No suitable raw audio obtained from {source_name} for '{original_artist} - {original_name}'.")
        
        # After trying all sources, clean up the main temporary base folder for this song
        if os.path.exists(song_specific_temp_base):
            try:
                shutil.rmtree(song_specific_temp_base)
                logger.info(f"Cleaned up base temporary folder for song: {song_specific_temp_base}")
            except OSError as e_os:
                logger.error(f"Error deleting base temporary folder {song_specific_temp_base}: {e_os}")
        
        if not final_validated_mp3_path:
            logger.error(f"All download and processing attempts FAILED for: {original_artist} - {original_name}")
            # Ensure a partially created (but failed validation) MP3 is removed if it still exists
            if os.path.exists(final_mp3_path):
                 logger.warning(f"Ensuring removal of incomplete/invalid output file: {final_mp3_path}")
                 try: os.remove(final_mp3_path)
                 except OSError: pass

        return final_validated_mp3_path, successful_source_name

# Example usage (for testing this module directly):
if __name__ == "__main__":
    print("Testing SpotifyDownloader with iterative source attempts...")
    load_dotenv_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    from dotenv import load_dotenv
    if os.path.exists(load_dotenv_path):
        load_dotenv(dotenv_path=load_dotenv_path)
        print(f"Loaded .env file from: {load_dotenv_path}")
    else:
        print(f".env file not found. Credentials must be set as env vars.")

    if not SPOTIPY_CLIENT_ID or not SPOTIPY_CLIENT_SECRET:
        print("Spotify API credentials not found. Skipping direct test.")
    else:
        downloader = SpotifyDownloader()
        test_playlist_url = "https://open.spotify.com/playlist/37i9dQZF1DX0s5kDeEflF1" # Lo-fi beats
        print(f"Fetching tracks from: {test_playlist_url}")
        tracks = downloader.get_playlist_tracks(test_playlist_url)
        
        if tracks:
            test_download_folder = os.path.join(DEFAULT_DOWNLOAD_DIR, "SpotifyDownloaderTest_Iterative") 
            ensure_dir_exists(test_download_folder)
            print(f"Test download folder: {test_download_folder}")

            # Test with the first 2 tracks from the playlist
            for i, track_to_test in enumerate(tracks[:2]): 
                print(f"\n--- Downloading Test Track {i+1}: {track_to_test['artist']} - {track_to_test['name']} ---")
                downloaded_path, source = downloader.download_song(track_to_test, test_download_folder)
                if downloaded_path:
                    print(f"SUCCESS: Test track {i+1} downloaded from {source} to: {downloaded_path}")
                    if os.path.exists(downloaded_path):
                        print(f"File size: {os.path.getsize(downloaded_path) / (1024*1024):.2f} MB")
                else:
                    print(f"FAILED: Test track {i+1} download failed.")
        else:
            print("Could not fetch tracks for testing.") 

# Small unit tests to ensure metadata read errors are swallowed and behavior preserved
def test_download_song_ignores_metadata_read_errors(tmp_path, monkeypatch):
    """
    Ensure that when an existing MP3 is present but its metadata JSON is unreadable/corrupt,
    download_song still returns the existing MP3 path and default 'Unknown/Existing' source
    without raising.
    """
    import sys
    module = sys.modules[__name__]

    # Arrange
    artist = "UnitTest Artist"
    name = "UnitTest Song"
    download_dir = str(tmp_path)
    sanitized = sanitize_filename(f"{artist} - {name}")
    final_mp3_path = tmp_path / f"{sanitized}.{DEFAULT_AUDIO_FORMAT}"
    # Create a dummy mp3 file (content not validated by our patched validator)
    final_mp3_path.write_bytes(b"FAKE_MP3_DATA")

    metadata_json_path = tmp_path / f"{sanitized}.json"
    # Write invalid JSON to force JSONDecodeError
    metadata_json_path.write_text("this is not valid json")

    track_info = {'artist': artist, 'name': name, 'duration_ms': 1000, 'spotify_track_id': 'unit-test-id'}

    # Patch validate_mp3_320kbps to return True to trigger the metadata read branch
    monkeypatch.setattr(f"{__name__}.validate_mp3_320kbps", lambda path, expected_duration_ms=None: True)

    # Create instance without invoking __init__ to avoid requiring Spotify credentials
    downloader = object.__new__(SpotifyDownloader)

    # Act
    returned_path, returned_source = downloader.download_song(track_info, download_dir)

    # Assert: path is returned and source is default since metadata couldn't be read
    assert returned_path == str(final_mp3_path)
    assert returned_source == "Unknown/Existing"