"""Configuration settings for the Music Ripper application.

This module centralizes all configuration constants and environment variable loading.
It handles Spotify API credentials, download settings, and FFmpeg configuration.
"""

import os
from dotenv import load_dotenv
from pydub import AudioSegment

load_dotenv()

# Spotify API Credentials
# These are loaded from the .env file in the project root
# Required for accessing Spotify's Web API to fetch playlist information
SPOTIPY_CLIENT_ID = os.getenv("SPOTIPY_CLIENT_ID")
SPOTIPY_CLIENT_SECRET = os.getenv("SPOTIPY_CLIENT_SECRET")

# Default download and audio processing settings
DEFAULT_DOWNLOAD_DIR = "Downloads"  # Default folder for downloaded music files
DEFAULT_AUDIO_FORMAT = "mp3"        # Output format for all downloaded audio
DEFAULT_AUDIO_BITRATE = "320k"      # High-quality audio bitrate (320 kbps)

# Logging configuration
LOG_LEVEL = "INFO"                  # Default logging level for the application
LOG_FILE = "music_ripper.log"       # Log file name for persistent logging

# FFmpeg Configuration
# FFmpeg is required for audio processing and conversion
# If FFmpeg is not in your system PATH, uncomment and modify the lines below:
#
# Windows example:
# AudioSegment.converter = "C:\\path\\to\\ffmpeg\\bin\\ffmpeg.exe"
# AudioSegment.ffprobe = "C:\\path\\to\\ffmpeg\\bin\\ffprobe.exe"
#
# macOS/Linux example (if installed via package manager):
# AudioSegment.converter = "/usr/local/bin/ffmpeg"
# AudioSegment.ffprobe = "/usr/local/bin/ffprobe"
#
# Note: If FFmpeg and FFprobe are in your system PATH, pydub will find them automatically 