import os
import re
from typing import Any, Dict, Optional
from dotenv import load_dotenv
from pydub import AudioSegment

load_dotenv()

"""
Configuration module for the music ripper application.

This module centralizes configuration values, loads them from environment variables (with documented defaults),
and validates them at import time. Each configuration item is documented in CONFIG_DOCS and has explicit
type and range checks to fail fast and clearly when misconfigured.

Validation errors raise specific exceptions (TypeError, ValueError, FileNotFoundError, OSError) with
clear messages describing the problem and how to fix it.
"""

# Human-readable documentation for each configuration key (name -> description and expected type)
CONFIG_DOCS: Dict[str, str] = {
    "SPOTIPY_CLIENT_ID": "Spotify client ID (str). Loaded from environment variable SPOTIPY_CLIENT_ID. Optional; if absent, set to None.",
    "SPOTIPY_CLIENT_SECRET": "Spotify client secret (str). Loaded from environment variable SPOTIPY_CLIENT_SECRET. Optional; if absent, set to None.",
    "DEFAULT_DOWNLOAD_DIR": "Default directory where downloaded audio files are stored (str). Loaded from DEFAULT_DOWNLOAD_DIR env var or defaults to 'Downloads'.",
    "DEFAULT_AUDIO_FORMAT": "Default audio file format/extension (str). Supported: mp3, wav, flac, aac, ogg. Loaded from DEFAULT_AUDIO_FORMAT env var or defaults to 'mp3'.",
    "DEFAULT_AUDIO_BITRATE": "Default audio bitrate (str) expressed like '320k'. Numeric part should be an integer (e.g., 128, 192, 320) and suffix 'k'. Loaded from DEFAULT_AUDIO_BITRATE env var or defaults to '320k'.",
    "LOG_LEVEL": "Logging level (str). One of: DEBUG, INFO, WARNING, ERROR, CRITICAL. Loaded from LOG_LEVEL env var or defaults to 'INFO'.",
    "LOG_FILE": "Path to log file (str). Loaded from LOG_FILE env var or defaults to 'music_ripper.log'.",
    "FFMPEG_PATH": "Optional path to ffmpeg binary (str). If provided via FFMPEG_PATH env var, pydub AudioSegment.converter will be set accordingly. If provided path does not exist, a FileNotFoundError is raised.",
    "FFPROBE_PATH": "Optional path to ffprobe binary (str). If provided via FFPROBE_PATH env var, pydub AudioSegment.ffprobe will be set accordingly. If provided path does not exist, a FileNotFoundError is raised.",
}

# Helper validators and loaders


def _ensure_str(value: Any, name: str) -> str:
    """
    Ensure the provided value is a string. Raises TypeError if not.

    :param value: Value to check.
    :param name: Name of the configuration item (used in error messages).
    :return: The value cast to str.
    """
    if value is None:
        raise TypeError(f"Configuration '{name}' must be a string, not None. Set it via environment variable '{name}'.")
    if not isinstance(value, str):
        raise TypeError(f"Configuration '{name}' must be a string, got {type(value).__name__}.")
    if value == "":
        raise ValueError(f"Configuration '{name}' is an empty string. Provide a non-empty value or unset the environment variable to use defaults where applicable.")
    return value


def _validate_bitrate(bitrate: str) -> str:
    """
    Validate bitrate string like '320k'. Numeric part must be an integer between 32 and 512 (kbps).
    Returns the same bitrate string if valid.

    :param bitrate: Bitrate string to validate.
    :return: Validated bitrate string.
    :raises ValueError: If format or numeric range is invalid.
    """
    if not isinstance(bitrate, str):
        raise TypeError("DEFAULT_AUDIO_BITRATE must be a string like '320k'.")
    match = re.fullmatch(r"(\d+)[kK]", bitrate.strip())
    if not match:
        raise ValueError("DEFAULT_AUDIO_BITRATE must be in the form '<number>k' (e.g., '320k').")
    numeric = int(match.group(1))
    if not (32 <= numeric <= 512):
        raise ValueError("DEFAULT_AUDIO_BITRATE numeric value must be between 32 and 512 (kbps).")
    return f"{numeric}k"


def _validate_format(audio_format: str) -> str:
    """
    Validate audio format against a whitelist.

    :param audio_format: Format string to validate.
    :return: Lowercased validated format.
    :raises ValueError: If format not supported.
    """
    if not isinstance(audio_format, str):
        raise TypeError("DEFAULT_AUDIO_FORMAT must be a string.")
    fmt = audio_format.strip().lower()
    allowed = {"mp3", "wav", "flac", "aac", "ogg"}
    if fmt not in allowed:
        raise ValueError(f"DEFAULT_AUDIO_FORMAT '{audio_format}' is not supported. Allowed values: {', '.join(sorted(allowed))}.")
    return fmt


def _validate_log_level(level: str) -> str:
    """
    Validate logging level string.

    :param level: Logging level to validate.
    :return: Uppercased logging level.
    :raises ValueError: If level not one of supported values.
    """
    if not isinstance(level, str):
        raise TypeError("LOG_LEVEL must be a string.")
    lvl = level.strip().upper()
    allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    if lvl not in allowed:
        raise ValueError(f"LOG_LEVEL '{level}' is invalid. Allowed values: {', '.join(sorted(allowed))}.")
    return lvl


def _validate_path(path: str, name: str, create_if_missing: bool = False) -> str:
    """
    Validate filesystem path string. Optionally create the directory if missing.

    :param path: Path to validate.
    :param name: Configuration name for error messages.
    :param create_if_missing: Create directory if it does not exist.
    :return: Absolute path string.
    :raises TypeError, OSError: If invalid type or creation fails.
    """
    if not isinstance(path, str):
        raise TypeError(f"{name} must be a string representing a filesystem path.")
    if path.strip() == "":
        raise ValueError(f"{name} must not be empty.")
    abs_path = os.path.abspath(path)
    # If it's intended to be a directory, offer to create it
    if create_if_missing:
        try:
            os.makedirs(abs_path, exist_ok=True)
        except OSError as e:
            raise OSError(f"Could not create directory for {name} at '{abs_path}': {e.strerror}") from e
    return abs_path


def _validate_executable_path(path: str, name: str) -> str:
    """
    Validate that an optional executable path exists on the filesystem.

    :param path: Path to executable.
    :param name: Configuration key name for error messages.
    :return: Absolute path string.
    :raises FileNotFoundError: If path is provided but does not exist.
    """
    if path is None or path == "":
        return ""
    if not isinstance(path, str):
        raise TypeError(f"{name} must be a string representing a path to an executable.")
    abs_path = os.path.abspath(path)
    if not os.path.isfile(abs_path):
        raise FileNotFoundError(f"{name} was set to '{path}' but no file exists at that location.")
    return abs_path


def _load_and_validate_config() -> Dict[str, Any]:
    """
    Load configuration values from environment variables (with documented defaults), validate them,
    and return a dictionary with validated configuration values.

    :return: Dictionary with validated configuration values.
    :raises TypeError, ValueError, FileNotFoundError, OSError: On invalid configuration values.
    """
    # Load raw values from environment with documented defaults to preserve previous behavior
    raw_spotify_client_id = os.getenv("SPOTIPY_CLIENT_ID", "")
    raw_spotify_client_secret = os.getenv("SPOTIPY_CLIENT_SECRET", "")

    raw_download_dir = os.getenv("DEFAULT_DOWNLOAD_DIR", "Downloads")
    raw_audio_format = os.getenv("DEFAULT_AUDIO_FORMAT", "mp3")
    raw_audio_bitrate = os.getenv("DEFAULT_AUDIO_BITRATE", "320k")
    raw_log_level = os.getenv("LOG_LEVEL", "INFO")
    raw_log_file = os.getenv("LOG_FILE", "music_ripper.log")
    raw_ffmpeg_path = os.getenv("FFMPEG_PATH", "")
    raw_ffprobe_path = os.getenv("FFPROBE_PATH", "")

    config: Dict[str, Any] = {}

    # Spotify credentials: optional; if provided must be non-empty strings.
    if raw_spotify_client_id is None or raw_spotify_client_id.strip() == "":
        config["SPOTIPY_CLIENT_ID"] = None
    else:
        config["SPOTIPY_CLIENT_ID"] = _ensure_str(raw_spotify_client_id, "SPOTIPY_CLIENT_ID")

    if raw_spotify_client_secret is None or raw_spotify_client_secret.strip() == "":
        config["SPOTIPY_CLIENT_SECRET"] = None
    else:
        config["SPOTIPY_CLIENT_SECRET"] = _ensure_str(raw_spotify_client_secret, "SPOTIPY_CLIENT_SECRET")

    # Download directory: ensure it's a valid path and create it if missing to avoid runtime errors.
    config["DEFAULT_DOWNLOAD_DIR"] = _validate_path(raw_download_dir, "DEFAULT_DOWNLOAD_DIR", create_if_missing=True)

    # Audio format validation
    config["DEFAULT_AUDIO_FORMAT"] = _validate_format(raw_audio_format)

    # Audio bitrate validation
    config["DEFAULT_AUDIO_BITRATE"] = _validate_bitrate(raw_audio_bitrate)

    # Logging config
    config["LOG_LEVEL"] = _validate_log_level(raw_log_level)
    config["LOG_FILE"] = _validate_path(raw_log_file, "LOG_FILE", create_if_missing=False)

    # Optional ffmpeg/ffprobe executable paths
    ffmpeg_validated = _validate_executable_path(raw_ffmpeg_path, "FFMPEG_PATH")
    ffprobe_validated = _validate_executable_path(raw_ffprobe_path, "FFPROBE_PATH")
    config["FFMPEG_PATH"] = ffmpeg_validated
    config["FFPROBE_PATH"] = ffprobe_validated

    return config


# Perform load and validation at import time so consumers get validated constants.
_CONFIG = _load_and_validate_config()

# Spotify API Credentials (loaded from environment variables)
# Type: Optional[str] - Spotify client credentials are optional; not hard-coded here.
SPOTIPY_CLIENT_ID: Optional[str] = _CONFIG["SPOTIPY_CLIENT_ID"]
SPOTIPY_CLIENT_SECRET: Optional[str] = _CONFIG["SPOTIPY_CLIENT_SECRET"]

# Default download settings
# DEFAULT_DOWNLOAD_DIR: str - Directory where downloaded audio files will be saved.
DEFAULT_DOWNLOAD_DIR: str = _CONFIG["DEFAULT_DOWNLOAD_DIR"]
# DEFAULT_AUDIO_FORMAT: str - File extension/format to use for saved audio files.
DEFAULT_AUDIO_FORMAT: str = _CONFIG["DEFAULT_AUDIO_FORMAT"]
# DEFAULT_AUDIO_BITRATE: str - Bitrate for audio encoding, e.g., '320k'.
DEFAULT_AUDIO_BITRATE: str = _CONFIG["DEFAULT_AUDIO_BITRATE"]

# Logging configuration
# LOG_LEVEL: str - Logging level used by the application.
LOG_LEVEL: str = _CONFIG["LOG_LEVEL"]
# LOG_FILE: str - Path to the logfile for application logs.
LOG_FILE: str = _CONFIG["LOG_FILE"]

# FFmpeg/ffprobe paths (if provided)
# FFMPEG_PATH: str - Optional path to ffmpeg binary. If empty, pydub will try to find ffmpeg in PATH.
FFMPEG_PATH: str = _CONFIG["FFMPEG_PATH"]
# FFPROBE_PATH: str - Optional path to ffprobe binary. If empty, pydub will try to find ffprobe in PATH.
FFPROBE_PATH: str = _CONFIG["FFPROBE_PATH"]

# If explicit ffmpeg/ffprobe paths are provided, configure pydub to use them.
if FFMPEG_PATH:
    AudioSegment.converter = FFMPEG_PATH
if FFPROBE_PATH:
    AudioSegment.ffprobe = FFPROBE_PATH

# Note: All secrets must be provided via environment variables. This module will not contain hard-coded credentials.
# The CONFIG_DOCS mapping contains descriptions and expected types for programmatic access/documentation.
# End of configuration module.