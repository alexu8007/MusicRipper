import unittest
from unittest import mock

from spotipy import SpotifyException
from spotipy.oauth2 import SpotifyOauthError

from src.spotify_downloader import PlaylistFetchError, SpotifyDownloader, parse_playlist_id

PLAYLIST_ID = "0aCBjAb1LZ6ODNLvrimWcZ"


def track(name, artist="Artist", duration_ms=200000):
    return {"id": name, "name": name, "artists": [{"name": artist}], "duration_ms": duration_ms,
            "track_number": 1, "album": {"name": "Album", "release_date": "2020-01-01",
                                         "images": [{"url": "https://i.scdn.co/image/x"}]}}


class ParsePlaylistIdTests(unittest.TestCase):
    def test_accepted_forms(self):
        for link in (f"https://open.spotify.com/playlist/{PLAYLIST_ID}?si=5f09e7fe28bc4bff",
                     f"https://open.spotify.com/intl-de/playlist/{PLAYLIST_ID}",
                     f"open.spotify.com/playlist/{PLAYLIST_ID}",
                     f"spotify:playlist:{PLAYLIST_ID}",
                     f"spotify:user:someone:playlist:{PLAYLIST_ID}",
                     PLAYLIST_ID):
            with self.subTest(link=link):
                self.assertEqual(parse_playlist_id(link), PLAYLIST_ID)

    def test_album_link_is_explained(self):
        with self.assertRaisesRegex(PlaylistFetchError, "album link; only playlist links"):
            parse_playlist_id(f"https://open.spotify.com/album/{PLAYLIST_ID}")

    def test_garbage_is_explained(self):
        with self.assertRaisesRegex(PlaylistFetchError, "is not a Spotify playlist link"):
            parse_playlist_id("https://example.com/whatever")


class SpotifyDownloaderTests(unittest.TestCase):
    def setUp(self):
        self.downloader = SpotifyDownloader(client_id="id", client_secret="secret")
        self.downloader.sp = mock.Mock()

    def test_uses_user_login_with_loopback_redirect(self):
        auth = self.downloader.auth_manager
        self.assertEqual(auth.redirect_uri, "http://127.0.0.1:8888/callback")
        self.assertIn("playlist-read-private", auth.scope)
        self.assertIn("playlist-read-collaborative", auth.scope)

    def test_reads_new_item_key_deprecated_track_key_and_pages(self):
        first = {"items": [{"item": track("New")}, {"track": track("Old")}, {"item": None}, None], "next": "page2"}
        second = {"items": [{"item": track("Paged")}], "next": None}
        self.downloader.sp.playlist_items.return_value = first
        self.downloader.sp.next.return_value = second
        tracks = self.downloader.get_playlist_tracks(f"https://open.spotify.com/playlist/{PLAYLIST_ID}")
        self.assertEqual([t["name"] for t in tracks], ["New", "Old", "Paged"])
        self.downloader.sp.playlist_items.assert_called_once_with(PLAYLIST_ID, additional_types=("track",))
        self.assertEqual(tracks[0]["year"], "2020")

    def test_403_explains_ownership_rule(self):
        self.downloader.sp.playlist_items.side_effect = SpotifyException(
            403, -1, f"https://api.spotify.com/v1/playlists/{PLAYLIST_ID}/items:\n Forbidden")
        with self.assertRaises(PlaylistFetchError) as ctx:
            self.downloader.get_playlist_tracks(PLAYLIST_ID)
        self.assertIn("HTTP 403: Forbidden", str(ctx.exception))
        self.assertIn("owns or collaborates on", str(ctx.exception))

    def test_404_mentions_spotify_made_playlists(self):
        self.downloader.sp.playlist_items.side_effect = SpotifyException(404, -1, "Resource not found")
        with self.assertRaisesRegex(PlaylistFetchError, "37i9dQZF"):
            self.downloader.get_playlist_tracks(PLAYLIST_ID)

    def test_bad_credentials_are_explained(self):
        self.downloader.sp.playlist_items.side_effect = SpotifyOauthError(
            "error", error="invalid_client", error_description="Invalid client")
        with self.assertRaisesRegex(PlaylistFetchError, "SPOTIPY_CLIENT_ID"):
            self.downloader.get_playlist_tracks(PLAYLIST_ID)


if __name__ == "__main__":
    unittest.main()
