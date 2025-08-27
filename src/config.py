import os
import re
import warnings
from typing import Optional, Set
from dotenv import load_dotenv
from pydub import AudioSegment

load_dotenv()


def _get_env(name: str, *, required: bool = False) -> Optional[str]:
    """
    Retrieve an environment variable with defensive validation.

    This helper trims surrounding whitespace, treats empty strings as missing,
    and rejects obvious placeholder values that indicate a hard-coded or
    non-production secret (e.g., "your_client_id", "changeme", "default").

    Args:
        name: The environment variable name to retrieve.
        required: If True, raises a ValueError when the variable is missing.

    Returns:
        The trimmed environment variable value or None if not set.

    Raises:
        ValueError: If required is True and the environment variable is missing or invalid.
    """
    raw = os.getenv(name)
    if raw is None:
        if required:
            raise ValueError(f"Required environment variable '{name}' is not set.")
        return None
    value = raw.strip()
    if value == "":
        if required:
            raise ValueError(f"Environment variable '{name}' is set but empty.")
        return None
    # Reject common placeholder tokens to avoid accidental hard-coded secrets
    placeholder_tokens = {"your_client_id", "your_client_secret", "changeme", "default", "none"}
    if value.lower() in placeholder_tokens:
        message = (
            f"Environment variable '{name}' appears to be a placeholder value "
            f"('{value}'). Please set a valid value in your environment."
        )
        if required:
            raise ValueError(message)
        warnings.warn(message, RuntimeWarning)
        return None
    return value


class _Config:
    """
    Centralized, read-only access to configuration values for the application.

    Use the properties on the instantiated CONFIG object for programmatic access.
    Module-level constants are preserved for backward compatibility.
    """

    ALLOWED_AUDIO_FORMATS: Set[str] = {"mp3", "wav", "flac", "ogg", "m4a"}
    BITRATE_PATTERN = re.compile(r"^(\d{1,3})k$", re.IGNORECASE)
    MIN_BITRATE_K = 32
    MAX_BITRATE_K = 320
    ALLOWED_LOG_LEVELS: Set[str] = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

    def __init__(self) -> None:
        # Credentials (may be None if not provided)
        self._spotipy_client_id: Optional[str] = _get_env("SPOTIPY_CLIENT_ID")
        self._spotipy_client_secret: Optional[str] = _get_env("SPOTIPY_CLIENT_SECRET")

        # Defaults (validated below)
        self._default_download_dir: str = "Downloads"
        self._default_audio_format: str = "mp3"
        self._default_audio_bitrate: str = "320k"
        self._log_level: str = "INFO"
        self._log_file: str = "music_ripper.log"

        # Run validations to guard against obvious misconfiguration
        self._validate_download_dir(self._default_download_dir)
        self._default_audio_format = self._validate_audio_format(self._default_audio_format)
        self._default_audio_bitrate = self._validate_audio_bitrate(self._default_audio_bitrate)
        self._log_level = self._validate_log_level(self._log_level)
        self._log_file = self._validate_log_file(self._log_file)

    @staticmethod
    def _validate_download_dir(path: str) -> None:
        """
        Ensure the download directory is a non-empty relative or absolute path.

        This function performs a basic validation to guard against obviously
        invalid values; it does not create directories.
        """
        if not isinstance(path, str) or path.strip() == "":
            raise ValueError("DEFAULT_DOWNLOAD_DIR must be a non-empty string.")

    def _validate_audio_format(self, fmt: str) -> str:
        """
        Validate and normalize the audio format.

        If the provided format is not allowed, a warning is emitted and the
        default 'mp3' is returned to preserve runtime semantics.
        """
        fmt_normalized = fmt.strip().lower()
        if fmt_normalized not in self.ALLOWED_AUDIO_FORMATS:
            warnings.warn(
                f"DEFAULT_AUDIO_FORMAT '{fmt}' is not supported. Falling back to 'mp3'.",
                RuntimeWarning,
            )
            return "mp3"
        return fmt_normalized

    def _validate_audio_bitrate(self, bitrate: str) -> str:
        """
        Validate the audio bitrate string (e.g., '320k').

        Ensures the format matches '<number>k' and that the numeric value is within
        a reasonable range. If invalid, falls back to '320k' with a warning.
        """
        if not isinstance(bitrate, str):
            warnings.warn("DEFAULT_AUDIO_BITRATE must be a string. Falling back to '320k'.", RuntimeWarning)
            return "320k"
        m = self.BITRATE_PATTERN.match(bitrate.strip().lower())
        if not m:
            warnings.warn(
                f"DEFAULT_AUDIO_BITRATE '{bitrate}' is not in the expected format '<number>k'. "
                f"Falling back to '320k'.",
                RuntimeWarning,
            )
            return "320k"
        kb = int(m.group(1))
        if not (self.MIN_BITRATE_K <= kb <= self.MAX_BITRATE_K):
            warnings.warn(
                f"DEFAULT_AUDIO_BITRATE '{bitrate}' is outside the supported range "
                f"{self.MIN_BITRATE_K}k-{self.MAX_BITRATE_K}k. Falling back to '320k'.",
                RuntimeWarning,
            )
            return "320k"
        return f"{kb}k"

    def _validate_log_level(self, level: str) -> str:
        """
        Validate the logging level string. Normalizes to an uppercase value and
        falls back to 'INFO' if not recognized.
        """
        if not isinstance(level, str):
            return "INFO"
        normalized = level.strip().upper()
        if normalized not in self.ALLOWED_LOG_LEVELS:
            warnings.warn(f"LOG_LEVEL '{level}' is not recognized. Falling back to 'INFO'.", RuntimeWarning)
            return "INFO"
        return normalized

    @staticmethod
    def _validate_log_file(path: str) -> str:
        """
        Basic validation for a logfile path. Ensures it's a non-empty string.

        This is intentionally conservative and will allow relative and absolute
        paths. Avoids accepting empty strings.
        """
        if not isinstance(path, str) or path.strip() == "":
            warnings.warn("LOG_FILE must be a non-empty string. Falling back to 'music_ripper.log'.", RuntimeWarning)
            return "music_ripper.log"
        return path.strip()

    @property
    def spotipy_client_id(self) -> Optional[str]:
        """Read-only Spotify client ID loaded from environment (or None)."""
        return self._spotipy_client_id

    @property
    def spotipy_client_secret(self) -> Optional[str]:
        """Read-only Spotify client secret loaded from environment (or None)."""
        return self._spotipy_client_secret

    @property
    def default_download_dir(self) -> str:
        """Read-only default directory where downloads will be saved."""
        return self._default_download_dir

    @property
    def default_audio_format(self) -> str:
        """Read-only default audio format (whitelisted)."""
        return self._default_audio_format

    @property
    def default_audio_bitrate(self) -> str:
        """Read-only default audio bitrate (e.g., '320k')."""
        return self._default_audio_bitrate

    @property
    def log_level(self) -> str:
        """Read-only log level (one of DEBUG, INFO, WARNING, ERROR, CRITICAL)."""
        return self._log_level

    @property
    def log_file(self) -> str:
        """Read-only path to the log file."""
        return self._log_file


# Instantiate the centralized config object
CONFIG = _Config()

# Preserve original module-level names for backward compatibility.
# These are simple values (not properties) so importing modules that expect
# module-level constants continue to function unchanged.
SPOTIPY_CLIENT_ID = CONFIG.spotipy_client_id
SPOTIPY_CLIENT_SECRET = CONFIG.spotipy_client_secret

DEFAULT_DOWNLOAD_DIR = CONFIG.default_download_dir
DEFAULT_AUDIO_FORMAT = CONFIG.default_audio_format
DEFAULT_AUDIO_BITRATE = CONFIG.default_audio_bitrate

LOG_LEVEL = CONFIG.log_level
LOG_FILE = CONFIG.log_file

# FFmpeg path (if not in system PATH, pydub might need it)
# On Windows, it might be like: "C:\\path\\to\\ffmpeg\\bin\\ffmpeg.exe"
# On macOS/Linux, it might be like: "/usr/local/bin/ffmpeg"
# If ffmpeg and ffprobe are in PATH, pydub should find them automatically.
# from pydub import AudioSegment
# AudioSegment.converter = "/usr/local/bin/ffmpeg" # Example for macOS if installed via brew
# AudioSegment.ffprobe   = "/usr/local/bin/ffprobe" # Example for macOS if installed via brew