import os
import re
from pathlib import Path
from typing import NamedTuple, Optional, Tuple

from dotenv import load_dotenv
from pydub import AudioSegment

load_dotenv()


def get_env_variable(key: str, default: Optional[str] = None, required: bool = False) -> Optional[str]:
    """
    Retrieve an environment variable, with optional default and required checking.

    Args:
        key: The environment variable name.
        default: A default value to return if the environment variable is not set.
        required: If True, raise a ValueError when the environment variable is missing.

    Returns:
        The environment variable value or the provided default.

    Raises:
        ValueError: If required is True and the environment variable is not set.
    """
    value = os.getenv(key, default)
    if required and (value is None or str(value).strip() == ""):
        raise ValueError(f"Required environment variable '{key}' is not set or is empty.")
    return value


class Config(NamedTuple):
    """
    Immutable configuration object for the application.

    Attributes:
        spotipy_client_id: Spotify client ID (may be None).
        spotipy_client_secret: Spotify client secret (may be None).
        default_download_dir: Default directory to save downloads.
        default_audio_format: Default audio file format (e.g., 'mp3').
        default_audio_bitrate: Default audio bitrate string (e.g., '320k').
        log_level: Logging level string (e.g., 'INFO').
        log_file: Path to the log file.
        ffmpeg_converter: Optional path to ffmpeg converter executable.
        ffprobe_path: Optional path to ffprobe executable.
    """
    spotipy_client_id: Optional[str]
    spotipy_client_secret: Optional[str]
    default_download_dir: str
    default_audio_format: str
    default_audio_bitrate: str
    log_level: str
    log_file: str
    ffmpeg_converter: Optional[str]
    ffprobe_path: Optional[str]


# Spotify API Credentials (loaded from environment/.env file)
# TODO: Move secrets to a secure secret manager or ensure they are provided via protected environment variables.
SPOTIPY_CLIENT_ID: Optional[str] = get_env_variable("SPOTIPY_CLIENT_ID")
SPOTIPY_CLIENT_SECRET: Optional[str] = get_env_variable("SPOTIPY_CLIENT_SECRET")

# Default download settings (can be overridden via environment variables)
DEFAULT_DOWNLOAD_DIR: str = get_env_variable("DEFAULT_DOWNLOAD_DIR", "Downloads") or "Downloads"
DEFAULT_AUDIO_FORMAT: str = get_env_variable("DEFAULT_AUDIO_FORMAT", "mp3") or "mp3"
DEFAULT_AUDIO_BITRATE: str = get_env_variable("DEFAULT_AUDIO_BITRATE", "320k") or "320k"

# Logging configuration (Example)
LOG_LEVEL: str = get_env_variable("LOG_LEVEL", "INFO") or "INFO"
LOG_FILE: str = get_env_variable("LOG_FILE", "music_ripper.log") or "music_ripper.log"

# FFmpeg path (optional overrides via environment)
FFMPEG_CONVERTER: Optional[str] = get_env_variable("FFMPEG_CONVERTER")
FFPROBE_PATH: Optional[str] = get_env_variable("FFPROBE_PATH")

# AudioSegment configuration examples (left commented in original file)
# If ffmpeg and ffprobe are in PATH, pydub should find them automatically.
# To override pydub's defaults, you can set:
# AudioSegment.converter = FFMPEG_CONVERTER
# AudioSegment.ffprobe = FFPROBE_PATH


def _validate_audio_format(format_name: str) -> None:
    """
    Validate the audio format string.

    Args:
        format_name: Audio format to validate.

    Raises:
        ValueError: If the format is not supported.
    """
    supported_formats = {"mp3", "wav", "flac", "aac", "ogg", "m4a"}
    if format_name.lower() not in supported_formats:
        raise ValueError(
            f"Unsupported audio format '{format_name}'. Supported formats: {', '.join(sorted(supported_formats))}."
        )


def _validate_audio_bitrate(bitrate: str) -> None:
    """
    Validate audio bitrate string (expects pattern like '320k').

    Args:
        bitrate: Bitrate string to validate.

    Raises:
        ValueError: If bitrate is malformed or outside reasonable bounds.
    """
    if not isinstance(bitrate, str):
        raise ValueError("Audio bitrate must be a string like '320k'.")
    if not re.fullmatch(r"\d+k", bitrate.strip().lower()):
        raise ValueError("Audio bitrate must be a string matching pattern like '320k'.")
    numeric_part = int(bitrate.strip().lower()[:-1])
    if numeric_part < 32 or numeric_part > 512:
        raise ValueError("Audio bitrate must be between 32k and 512k.")


def _validate_and_prepare_download_dir(path_str: str) -> str:
    """
    Validate the download directory path and create it if necessary.

    Args:
        path_str: Path string to validate.

    Returns:
        The absolute path string of the directory.

    Raises:
        ValueError: If the path is invalid or cannot be created.
    """
    if not isinstance(path_str, str) or path_str.strip() == "":
        raise ValueError("Download directory must be a non-empty string.")
    path = Path(path_str).expanduser()
    try:
        path.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        raise ValueError(f"Unable to create or access download directory '{path}': {exc}")
    return str(path.resolve())


def _validate_config(config: Config) -> None:
    """
    Run validations on a Config instance and raise descriptive exceptions on invalid values.

    Args:
        config: Config instance to validate.

    Raises:
        ValueError: For any invalid configuration values.
    """
    _validate_audio_format(config.default_audio_format)
    _validate_audio_bitrate(config.default_audio_bitrate)
    # Ensure download dir exists or can be created
    _validate_and_prepare_download_dir(config.default_download_dir)
    # Validate log level basic shape
    if not isinstance(config.log_level, str) or config.log_level.strip() == "":
        raise ValueError("LOG_LEVEL must be a non-empty string.")
    if not isinstance(config.log_file, str) or config.log_file.strip() == "":
        raise ValueError("LOG_FILE must be a non-empty string.")


def get_config() -> Config:
    """
    Construct and return an immutable Config object representing current configuration.

    This function centralizes validation and creation of a frozen configuration object.
    Module-level constants remain available for backward compatibility.

    Returns:
        A validated, immutable Config object.

    Raises:
        ValueError: If any configuration value is invalid.
    """
    config = Config(
        spotipy_client_id=SPOTIPY_CLIENT_ID,
        spotipy_client_secret=SPOTIPY_CLIENT_SECRET,
        default_download_dir=DEFAULT_DOWNLOAD_DIR,
        default_audio_format=DEFAULT_AUDIO_FORMAT,
        default_audio_bitrate=DEFAULT_AUDIO_BITRATE,
        log_level=LOG_LEVEL,
        log_file=LOG_FILE,
        ffmpeg_converter=FFMPEG_CONVERTER,
        ffprobe_path=FFPROBE_PATH,
    )
    _validate_config(config)
    return config


# Create a module-level cached immutable configuration so callers can either import module-level
# variables or call get_config() for an immutable view.
_CONFIG: Config = get_config()


def get_cached_config() -> Config:
    """
    Return the cached immutable configuration object.

    This provides a stable, testable configuration object without exposing mutable globals.

    Returns:
        The module-level validated Config instance.
    """
    return _CONFIG


# Preserve original module-level names for backward compatibility, reflecting validated values.
SPOTIPY_CLIENT_ID = _CONFIG.spotipy_client_id
SPOTIPY_CLIENT_SECRET = _CONFIG.spotipy_client_secret
DEFAULT_DOWNLOAD_DIR = _CONFIG.default_download_dir
DEFAULT_AUDIO_FORMAT = _CONFIG.default_audio_format
DEFAULT_AUDIO_BITRATE = _CONFIG.default_audio_bitrate
LOG_LEVEL = _CONFIG.log_level
LOG_FILE = _CONFIG.log_file
FFMPEG_CONVERTER = _CONFIG.ffmpeg_converter
FFPROBE_PATH = _CONFIG.ffprobe_path

# Note: pydub.AudioSegment configuration comments remain to guide users on how to set ffmpeg/ffprobe paths.
# Example:
# AudioSegment.converter = FFMPEG_CONVERTER
# AudioSegment.ffprobe = FFPROBE_PATH