import unittest

from src.utils import describe_ytdlp_error, format_duration


class DescribeYtDlpErrorTests(unittest.TestCase):
    def test_bot_check_gets_cookie_hint_without_cli_advice(self):
        message = describe_ytdlp_error(Exception(
            "ERROR: [youtube] 5NV6Rdv1a3I: Sign in to confirm you're not a bot. Use --cookies-from-browser or "
            "--cookies for the authentication. See  https://github.com/yt-dlp/yt-dlp/wiki/FAQ for details"))
        self.assertTrue(message.startswith("[youtube] 5NV6Rdv1a3I: Sign in to confirm you're not a bot."))
        self.assertIn("YTDLP_COOKIES_FROM_BROWSER", message)
        self.assertNotIn("--cookies", message)

    def test_outdated_extractor_suggests_update(self):
        message = describe_ytdlp_error(Exception(
            "ERROR: No suitable extractor (Soundcloud) found for URL https://api.soundcloud.com/tracks/1"))
        self.assertIn('pip install -U "yt-dlp[default]"', message)

    def test_other_errors_pass_through(self):
        self.assertEqual(describe_ytdlp_error(Exception("ERROR: [youtube] abc: Video unavailable")),
                         "[youtube] abc: Video unavailable")


class FormatDurationTests(unittest.TestCase):
    def test_format_duration(self):
        self.assertEqual(format_duration(248413), "4:08")
        self.assertEqual(format_duration(30000), "0:30")


if __name__ == "__main__":
    unittest.main()
