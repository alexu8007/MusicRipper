import os
from dotenv import load_dotenv
from pydub import AudioSegment
from typing import Optional
import re

load_dotenv()

"""
Configuration module for the music ripper application.

Behavior:
- Environment variables (loaded via dotenv and os.environ) are consulted for
  sensitive or environment-specific values. If an environment variable is
  not present, the code falls back to the default value explicitly defined
  in this module (which may be None for credentials).
- Use validate_config() to perform explicit validation; it is called at module
  import time to fail fast on invalid configuration values.

Note:
- This module keeps the previous runtime behavior: SPOTIPY_CLIENT_ID and
  SPOTIPY_CLIENT_SECRET default to None when the corresponding environment
  variables are not provided.
"""

def _get_env_var(name: str, default: Optional[str]) -> Optional[str]:
    """
    Read an environment variable and fall back to default if unset.

    Args:
        name: The name of the environment variable to read.
        default: The value to return if the environment variable is not set.

    Returns:
        The environment value if present; otherwise the provided default.
    """
    return os.environ.get(name, default)


# Spotify API Credentials (loaded from environment variables; fall back to None)
SPOTIPY_CLIENT_ID: Optional[str] = _get_env_var("SPOTIPY_CLIENT_ID", None)
"""Spotify client ID. Read from environment variable 'SPOTIPY_CLIENT_ID'. Falls back to None if unset."""

SPOTIPY_CLIENT_SECRET: Optional[str] = _get_env_var("SPOTIPY_CLIENT_SECRET", None)
"""Spotify client secret. Read from environment variable 'SPOTIPY_CLIENT_SECRET'. Falls back to None if unset."""


# Default download settings
DEFAULT_DOWNLOAD_DIR: str = "Downloads"
"""Default directory where downloads are saved. Can be overridden by external configuration if desired."""

DEFAULT_AUDIO_FORMAT: str = "mp3"
"""Default audio file format used for downloads. Common values: 'mp3', 'wav', 'flac', 'aac', 'ogg', 'm4a'."""

DEFAULT_AUDIO_BITRATE: str = "320k"  # 320 kbps
"""Default audio bitrate string. Expected format is '<number>k' (e.g., '320k')."""


# Logging configuration (Example)
LOG_LEVEL: str = "INFO"
"""Logging level. Expected values: 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'."""

LOG_FILE: str = "music_ripper.log"
"""Default log file path."""


# FFmpeg path (if not in system PATH, pydub might need it)
# On Windows, it might be like: "C:\\path\\to\\ffmpeg\\bin\\ffmpeg.exe"
# On macOS/Linux, it might be like: "/usr/local/bin/ffmpeg"
# If ffmpeg and ffprobe are in PATH, pydub should find them automatically.
# from pydub import AudioSegment
# AudioSegment.converter = "/usr/local/bin/ffmpeg" # Example for macOS if installed via brew
# AudioSegment.ffprobe   = "/usr/local/bin/ffprobe" # Example for macOS if installed via brew


def validate_config() -> None:
    """
    Validate configuration values and fail fast if any are invalid.

    Checks performed:
    - DEFAULT_DOWNLOAD_DIR is a non-empty string.
    - DEFAULT_AUDIO_FORMAT is one of the supported formats.
    - DEFAULT_AUDIO_BITRATE matches the pattern '<digits>k' (e.g., '320k').
    - LOG_LEVEL is one of the standard logging levels.
    - If SPOTIPY_CLIENT_ID or SPOTIPY_CLIENT_SECRET are provided, they must be non-empty strings.

    Raises:
        ValueError: If any configuration value is invalid.
    """
    if not isinstance(DEFAULT_DOWNLOAD_DIR, str) or not DEFAULT_DOWNLOAD_DIR.strip():
        raise ValueError(f"DEFAULT_DOWNLOAD_DIR must be a non-empty string (got: {DEFAULT_DOWNLOAD_DIR!r})")

    supported_formats = {"mp3", "wav", "flac", "aac", "ogg", "m4a"}
    if not isinstance(DEFAULT_AUDIO_FORMAT, str) or DEFAULT_AUDIO_FORMAT.lower() not in supported_formats:
        raise ValueError(
            f"DEFAULT_AUDIO_FORMAT must be one of {sorted(supported_formats)} (got: {DEFAULT_AUDIO_FORMAT!r})"
        )

    if not isinstance(DEFAULT_AUDIO_BITRATE, str) or not re.match(r'^\d+k$', DEFAULT_AUDIO_BITRATE):
        raise ValueError(
            "DEFAULT_AUDIO_BITRATE must be a string matching the pattern '<number>k', e.g. '320k' "
            f"(got: {DEFAULT_AUDIO_BITRATE!r})"
        )

    valid_log_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    if not isinstance(LOG_LEVEL, str) or LOG_LEVEL.upper() not in valid_log_levels:
        raise ValueError(f"LOG_LEVEL must be one of {sorted(valid_log_levels)} (got: {LOG_LEVEL!r})")

    if SPOTIPY_CLIENT_ID is not None and (not isinstance(SPOTIPY_CLIENT_ID, str) or not SPOTIPY_CLIENT_ID.strip()):
        raise ValueError("SPOTIPY_CLIENT_ID, if set, must be a non-empty string")

    if SPOTIPY_CLIENT_SECRET is not None and (not isinstance(SPOTIPY_CLIENT_SECRET, str) or not SPOTIPY_CLIENT_SECRET.strip()):
        raise ValueError("SPOTIPY_CLIENT_SECRET, if set, must be a non-empty string")


# Perform validation at module import time to fail fast on invalid configuration.
validate_config()