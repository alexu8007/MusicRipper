import datetime
import unittest

from src.dependency_check import (
    CheckResult, check_packages, check_python, check_spotify_config, check_youtube_support,
    check_ytdlp_freshness, parse_version,
)

GOOD_VERSIONS = {
    "spotipy": "2.26.0", "yt-dlp": "2026.8.19", "pydub": "0.25.1", "requests": "2.34.2",
    "python-dotenv": "1.2.3", "rich": "15.0.0", "Pillow": "12.3.0",
}


class VersionTests(unittest.TestCase):
    def test_parse_version(self):
        self.assertEqual(parse_version("2026.08.19"), (2026, 8, 19))
        self.assertEqual(parse_version("12.3.0.dev0"), (12, 3, 0))
        self.assertLess(parse_version("2.25.1"), parse_version("2.26.0"))


class PackageCheckTests(unittest.TestCase):
    def run_check(self, **overrides):
        versions = {**GOOD_VERSIONS, **overrides}
        result = CheckResult()
        check_packages(result, get_version=versions.get)
        return result

    def test_all_good(self):
        result = self.run_check()
        self.assertEqual((result.errors, result.warnings), ([], []))

    def test_outdated_spotipy_is_an_error_with_reason(self):
        result = self.run_check(spotipy="2.25.1")
        self.assertEqual(len(result.errors), 1)
        self.assertIn("spotipy 2.25.1 is too old", result.errors[0])
        self.assertIn("/tracks", result.errors[0])

    def test_missing_package_is_an_error(self):
        result = self.run_check(**{"yt-dlp": None})
        self.assertIn("yt-dlp is not installed", result.errors[0])

    def test_missing_pillow_is_only_a_warning(self):
        result = self.run_check(Pillow=None)
        self.assertEqual(result.errors, [])
        self.assertIn("Pillow is not installed", result.warnings[0])


class PythonCheckTests(unittest.TestCase):
    def test_old_python_is_rejected(self):
        result = CheckResult()
        check_python(result, version_info=(3, 9, 7))
        self.assertIn("Python 3.9.7 is too old", result.errors[0])

    def test_supported_python(self):
        result = CheckResult()
        check_python(result, version_info=(3, 12, 3))
        self.assertEqual(result.errors, [])


class YtDlpChecksTests(unittest.TestCase):
    def test_old_ytdlp_gets_update_warning(self):
        result = CheckResult()
        check_ytdlp_freshness(result, "2025.4.30", today=datetime.date(2026, 9, 30))
        self.assertIn("yt-dlp 2025.4.30 is 518 days old", result.warnings[0])

    def test_recent_ytdlp_is_fine(self):
        result = CheckResult()
        check_ytdlp_freshness(result, "2026.08.19", today=datetime.date(2026, 9, 30))
        self.assertEqual(result.warnings, [])

    def test_missing_js_runtime_warns(self):
        result = CheckResult()
        check_youtube_support(result, runtimes={})
        self.assertTrue(any("Deno" in warning for warning in result.warnings))


class SpotifyConfigTests(unittest.TestCase):
    def check(self, redirect_uri, client_id="id", client_secret="secret"):
        result = CheckResult()
        check_spotify_config(result, client_id, client_secret, redirect_uri)
        return result

    def test_default_loopback_uri_is_fine(self):
        result = self.check("http://127.0.0.1:8888/callback")
        self.assertEqual((result.errors, result.warnings), ([], []))

    def test_localhost_is_rejected(self):
        self.assertIn("uses 'localhost'", self.check("http://localhost:8888/callback").errors[0])

    def test_plain_http_is_rejected(self):
        self.assertIn("must use https", self.check("http://example.com/callback").errors[0])

    def test_https_is_fine(self):
        self.assertEqual(self.check("https://example.com/callback").errors, [])

    def test_loopback_without_port_warns(self):
        self.assertIn("has no port", self.check("http://127.0.0.1/callback").warnings[0])

    def test_missing_credentials(self):
        result = self.check("http://127.0.0.1:8888/callback", client_id=None)
        self.assertIn("Spotify credentials are missing", result.errors[0])


if __name__ == "__main__":
    unittest.main()
