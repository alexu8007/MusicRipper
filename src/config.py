import os
from dotenv import load_dotenv

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

# Spotify API Credentials (loaded from .env file)
SPOTIPY_CLIENT_ID = os.getenv("SPOTIPY_CLIENT_ID")
SPOTIPY_CLIENT_SECRET = os.getenv("SPOTIPY_CLIENT_SECRET")
# Must exactly match a Redirect URI registered in your Spotify app's settings.
# Spotify no longer accepts "localhost"; use the loopback IP literal instead.
SPOTIPY_REDIRECT_URI = os.getenv("SPOTIPY_REDIRECT_URI", "http://127.0.0.1:8888/callback")
# Reading playlist items requires a user login (the Authorization Code flow).
SPOTIFY_SCOPES = "playlist-read-private playlist-read-collaborative"
# Holds your Spotify login (including a long-lived refresh token). Never commit it.
SPOTIFY_TOKEN_CACHE = os.path.join(PROJECT_ROOT, ".spotify_token_cache")

# Default download settings
DEFAULT_DOWNLOAD_DIR = "Downloads"
DEFAULT_AUDIO_FORMAT = "mp3"

# Audio quality. Sources below MIN_SOURCE_BITRATE_KBPS are skipped. The MP3 is
# encoded at a bitrate matching the source (never above it), capped at
# MAX_OUTPUT_BITRATE_KBPS, because re-encoding can't restore lost detail.
MIN_SOURCE_BITRATE_KBPS = 128
MAX_OUTPUT_BITRATE_KBPS = 320

# Logging configuration (Example)
LOG_LEVEL = "INFO"
LOG_FILE = "music_ripper.log"

# Optional: let yt-dlp use your browser's cookies when YouTube asks you to
# "Sign in to confirm you're not a bot". E.g. "firefox" or "chrome:Profile 1".
YTDLP_COOKIES_FROM_BROWSER = os.getenv("YTDLP_COOKIES_FROM_BROWSER")
# Optional: path to a Netscape-format cookies.txt file instead.
YTDLP_COOKIES_FILE = os.getenv("YTDLP_COOKIES_FILE")

# FFmpeg/FFprobe are located automatically (PATH plus common install folders
# such as C:\ffmpeg\bin, Homebrew and winget locations). To point at a specific
# install, set FFMPEG_PATH / FFPROBE_PATH in .env to the executable or its
# folder; see src/external_tools.py.
