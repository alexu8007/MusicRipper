"""Configuration module for the music ripper application.

This module centralizes configuration values, loads environment variables, and
performs lightweight runtime validation without throwing exceptions. It preserves
the original resolution order and default values.

Expected environment variables:
- SPOTIPY_CLIENT_ID: (optional) Spotify API client ID.
- SPOTIPY_CLIENT_SECRET: (optional) Spotify API client secret.
- DEFAULT_DOWNLOAD_DIR: (optional) default directory for downloads (string).
- DEFAULT_AUDIO_FORMAT: (optional) default audio format (e.g. "mp3").
- DEFAULT_AUDIO_BITRATE: (optional) default audio bitrate (e.g. "320k").
- LOG_LEVEL: (optional) logging level ("DEBUG","INFO","WARNING","ERROR","CRITICAL").
- LOG_FILE: (optional) path to log file.

Notes:
- This module uses warnings to signal potential misconfigurations but does not
  raise errors, preserving previous runtime behavior.
"""

import os
import re
import warnings
from typing import Optional

from dotenv import load_dotenv
from pydub import AudioSegment

load_dotenv()

# Spotify API Credentials (loaded from .env file)
SPOTIPY_CLIENT_ID: Optional[str] = os.getenv("SPOTIPY_CLIENT_ID")
SPOTIPY_CLIENT_SECRET: Optional[str] = os.getenv("SPOTIPY_CLIENT_SECRET")

# Default download settings
DEFAULT_DOWNLOAD_DIR: str = os.getenv("DEFAULT_DOWNLOAD_DIR", "Downloads")
DEFAULT_AUDIO_FORMAT: str = os.getenv("DEFAULT_AUDIO_FORMAT", "mp3")
DEFAULT_AUDIO_BITRATE: str = os.getenv("DEFAULT_AUDIO_BITRATE", "320k")  # 320 kbps

# Logging configuration (Example)
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE: str = os.getenv("LOG_FILE", "music_ripper.log")

# FFmpeg path (if not in system PATH, pydub might need it)
# On Windows, it might be like: "C:\\path\\to\\ffmpeg\\bin\\ffmpeg.exe"
# On macOS/Linux, it might be like: "/usr/local/bin/ffmpeg"
# If ffmpeg and ffprobe are in PATH, pydub should find them automatically.
# from pydub import AudioSegment
# AudioSegment.converter = "/usr/local/bin/ffmpeg" # Example for macOS if installed via brew
# AudioSegment.ffprobe   = "/usr/local/bin/ffprobe" # Example for macOS if installed via brew


def _validate_config() -> None:
    """Perform minimal validation of configuration values and warn on issues.

    This function intentionally does not raise exceptions so as to preserve
    previous behavior; instead it emits warnings with clear guidance.
    """
    # Validate Spotify credentials shape (non-empty strings if provided)
    if SPOTIPY_CLIENT_ID is not None and not isinstance(SPOTIPY_CLIENT_ID, str):
        warnings.warn("SPOTIPY_CLIENT_ID is set but is not a string. "
                      "Expected a string client ID.", UserWarning)
    if SPOTIPY_CLIENT_SECRET is not None and not isinstance(SPOTIPY_CLIENT_SECRET, str):
        warnings.warn("SPOTIPY_CLIENT_SECRET is set but is not a string. "
                      "Expected a string client secret.", UserWarning)

    # DEFAULT_DOWNLOAD_DIR should be a non-empty string
    if not isinstance(DEFAULT_DOWNLOAD_DIR, str) or DEFAULT_DOWNLOAD_DIR.strip() == "":
        warnings.warn(f"DEFAULT_DOWNLOAD_DIR='{DEFAULT_DOWNLOAD_DIR}' looks invalid. "
                      "Falling back to 'Downloads' may occur elsewhere.", UserWarning)

    # DEFAULT_AUDIO_FORMAT basic validation
    allowed_formats = {"mp3", "wav", "flac", "aac", "ogg", "m4a"}
    if not isinstance(DEFAULT_AUDIO_FORMAT, str) or DEFAULT_AUDIO_FORMAT.strip() == "":
        warnings.warn(f"DEFAULT_AUDIO_FORMAT='{DEFAULT_AUDIO_FORMAT}' looks invalid. "
                      "Expected a non-empty audio format string.", UserWarning)
    else:
        fmt = DEFAULT_AUDIO_FORMAT.strip().lower()
        if fmt not in allowed_formats:
            warnings.warn(f"DEFAULT_AUDIO_FORMAT='{DEFAULT_AUDIO_FORMAT}' is not a commonly "
                          f"recognized format. Known formats: {sorted(allowed_formats)}.",
                          UserWarning)

    # DEFAULT_AUDIO_BITRATE basic validation, expect patterns like '320k' or '192k'
    if not isinstance(DEFAULT_AUDIO_BITRATE, str) or DEFAULT_AUDIO_BITRATE.strip() == "":
        warnings.warn(f"DEFAULT_AUDIO_BITRATE='{DEFAULT_AUDIO_BITRATE}' looks invalid. "
                      "Expected a string like '320k'.", UserWarning)
    else:
        bitrate_pattern = re.compile(r"^\d+k$", re.IGNORECASE)
        if not bitrate_pattern.match(DEFAULT_AUDIO_BITRATE.strip()):
            warnings.warn(f"DEFAULT_AUDIO_BITRATE='{DEFAULT_AUDIO_BITRATE}' does not match "
                          "expected pattern like '320k'.", UserWarning)

    # LOG_LEVEL validation
    valid_log_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    if not isinstance(LOG_LEVEL, str) or LOG_LEVEL.strip().upper() not in valid_log_levels:
        warnings.warn(f"LOG_LEVEL='{LOG_LEVEL}' is not a valid log level. "
                      f"Expected one of: {sorted(valid_log_levels)}. Defaulting behavior "
                      "will follow existing runtime logic.", UserWarning)

    # LOG_FILE should be a string if provided
    if not isinstance(LOG_FILE, str) or LOG_FILE.strip() == "":
        warnings.warn(f"LOG_FILE='{LOG_FILE}' looks invalid. Expected a file path string.", UserWarning)


# Run validation at import time (non-throwing)
_validate_config()