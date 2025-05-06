import os
from dotenv import load_dotenv
from pydub import AudioSegment

load_dotenv()

# Spotify API Credentials (loaded from .env file)
SPOTIPY_CLIENT_ID = os.getenv("SPOTIPY_CLIENT_ID")
SPOTIPY_CLIENT_SECRET = os.getenv("SPOTIPY_CLIENT_SECRET")

# Default download settings
DEFAULT_DOWNLOAD_DIR = "Downloads"
DEFAULT_AUDIO_FORMAT = "mp3"
DEFAULT_AUDIO_BITRATE = "320k" # 320 kbps

# Logging configuration (Example)
LOG_LEVEL = "INFO"
LOG_FILE = "music_ripper.log"

# FFmpeg path (if not in system PATH, pydub might need it)
# On Windows, it might be like: "C:\\path\\to\\ffmpeg\\bin\\ffmpeg.exe"
# On macOS/Linux, it might be like: "/usr/local/bin/ffmpeg"
# If ffmpeg and ffprobe are in PATH, pydub should find them automatically.
# from pydub import AudioSegment
# AudioSegment.converter = "/usr/local/bin/ffmpeg" # Example for macOS if installed via brew
# AudioSegment.ffprobe   = "/usr/local/bin/ffprobe" # Example for macOS if installed via brew 