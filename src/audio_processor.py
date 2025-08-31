# src/audio_processor.py
"""Handles audio processing tasks like conversion and validation."""

import os
import logging
from typing import Any, Dict, Optional

from pydub import AudioSegment
from pydub.utils import mediainfo
from pydub.exceptions import CouldntDecodeError

from .config import DEFAULT_AUDIO_FORMAT, DEFAULT_AUDIO_BITRATE
from .utils import sanitize_filename

logger = logging.getLogger(__name__)

# Default tolerance for duration check in milliseconds (e.g., 5 seconds)
DEFAULT_DURATION_TOLERANCE_MS = 5000


class FileSystemAdapter:
    """Adapter for filesystem operations to enable injection in tests."""

    def exists(self, path: str) -> bool:
        return os.path.exists(path)

    def makedirs(self, path: str, exist_ok: bool = True) -> None:
        os.makedirs(path, exist_ok=exist_ok)

    def remove(self, path: str) -> None:
        os.remove(path)


class AudioAdapter:
    """Adapter for audio-related external interactions (pydub/ffmpeg)."""

    def from_file(self, path: str) -> AudioSegment:
        return AudioSegment.from_file(path)

    def export(self, audio_segment: AudioSegment, output_path: str, export_params: Dict[str, Any]) -> None:
        audio_segment.export(output_path, **export_params)

    def mediainfo(self, path: str) -> Dict[str, Any]:
        return mediainfo(path)


# Module-level adapters that can be replaced in tests to avoid real I/O/subprocess calls.
file_system_adapter: FileSystemAdapter = FileSystemAdapter()
audio_adapter: AudioAdapter = AudioAdapter()


def _validate_path_string(path: str, param_name: str) -> None:
    """Validate that a provided path is a non-empty string."""
    if not isinstance(path, str) or not path.strip():
        raise ValueError(f"{param_name} must be a non-empty string.")


def _ensure_output_directory(output_path: str) -> None:
    """Ensure the directory for the output path exists."""
    directory = os.path.dirname(output_path) or "."
    file_system_adapter.makedirs(directory, exist_ok=True)


def _build_export_tags(artist: str, title: str, album: Optional[str], track_number: Optional[str], year: Optional[str]) -> Dict[str, str]:
    """Construct ID3 tag dictionary for export."""
    tags: Dict[str, str] = {"artist": artist, "title": title}
    if album:
        tags["album"] = album
    if track_number:
        tags["tracknumber"] = track_number
    if year:
        tags["date"] = year
    return tags


def _embed_cover_if_exists(export_params: Dict[str, Any], cover_image_path: Optional[str]) -> None:
    """Add cover art to export parameters if the file exists; otherwise log appropriately."""
    if not cover_image_path:
        return
    if file_system_adapter.exists(cover_image_path):
        export_params["cover"] = cover_image_path
        logger.info("Embedding cover art from: %s", cover_image_path)
    else:
        logger.warning("Cover image path provided (%s) but file not found. Skipping cover art.", cover_image_path)


def _safe_remove_file(path: str) -> None:
    """Remove a file and log errors explicitly (do not swallow exceptions silently)."""
    try:
        if file_system_adapter.exists(path):
            file_system_adapter.remove(path)
    except FileNotFoundError:
        # File already removed or never existed
        logger.debug("Attempted to remove file that does not exist: %s", path)
    except OSError as ose:
        logger.error("Could not remove partially created/failed output file %s: %s", path, ose)


def _get_audio_duration_ms(path: str) -> int:
    """
    Return the duration of an audio file in milliseconds.

    Note: This loads metadata and may load audio into memory depending on backend.
    PERFORMANCE: Loading full audio into memory can be expensive; consider streaming or metadata-only approaches if available.
    """
    audio = audio_adapter.from_file(path)
    return int(audio.duration_seconds * 1000)


def _is_format_and_bitrate_320(info: Dict[str, Any]) -> bool:
    """Check whether media info indicates MP3 format and approx 320kbps bitrate."""
    file_format = str(info.get("format_name", "")).lower()
    bit_rate_str = str(info.get("bit_rate", "0"))
    try:
        bit_rate = int(bit_rate_str)
    except (ValueError, TypeError):
        logger.warning("Could not parse bitrate from mediainfo: %s", bit_rate_str)
        return False
    is_mp3 = "mp3" in file_format
    is_320kbps = 315000 <= bit_rate <= 325000
    return bool(is_mp3 and is_320kbps)


def convert_to_mp3_320kbps(input_path: str, output_path: str, 
                           artist: str = "Unknown Artist", 
                           title: str = "Unknown Title", 
                           album: str | None = None, 
                           track_number: str | None = None, 
                           year: str | None = None, 
                           cover_image_path: str | None = None) -> bool:
    """
    Converts an audio file to MP3 format at 320kbps.
    Adds ID3 tags for artist, title, album, track number, year, and cover art.

    Args:
        input_path: Path to the input audio file.
        output_path: Path to save the converted MP3 file.
        artist: Song artist for ID3 tag.
        title: Song title for ID3 tag.
        album: Album name for ID3 tag.
        track_number: Track number for ID3 tag.
        year: Release year for ID3 tag.
        cover_image_path: Path to the cover image file.

    Returns:
        True if conversion was successful, False otherwise.
    """
    try:
        _validate_path_string(input_path, "input_path")
        _validate_path_string(output_path, "output_path")
    except ValueError as ve:
        logger.error("Invalid argument: %s", ve)
        return False

    try:
        logger.info("Attempting to convert %s to MP3 320kbps with extended metadata.", input_path)

        # Input file must exist before attempting conversion
        if not file_system_adapter.exists(input_path):
            logger.warning("Input file does not exist: %s", input_path)
            return False

        # PERFORMANCE: This reads the entire file into memory via pydub.
        # Consider switching to streaming export/ffmpeg CLI if large files are expected.
        try:
            audio = audio_adapter.from_file(input_path)
        except CouldntDecodeError as cde:
            logger.error("Could not decode input file %s: %s", input_path, cde)
            return False
        except FileNotFoundError as fnf:
            logger.error("Input file not found during open: %s", fnf)
            return False
        except OSError as ose:
            logger.error("OS error while opening input file %s: %s", input_path, ose)
            return False

        tags = _build_export_tags(artist, title, album, track_number, year)

        # Ensure output directory exists
        try:
            _ensure_output_directory(output_path)
        except OSError as ose:
            logger.error("Could not ensure output directory for %s: %s", output_path, ose)
            return False

        export_params: Dict[str, Any] = {
            "format": DEFAULT_AUDIO_FORMAT,
            "bitrate": DEFAULT_AUDIO_BITRATE,
            "tags": tags
        }

        _embed_cover_if_exists(export_params, cover_image_path)

        try:
            audio_adapter.export(audio, output_path, export_params)
        except (OSError, ValueError) as e:
            logger.error("Error exporting audio to %s: %s", output_path, e)
            _safe_remove_file(output_path)
            return False
        except Exception as e:
            # Log unexpected errors explicitly and attempt cleanup
            logger.error("Unexpected error during export to %s: %s", output_path, e)
            _safe_remove_file(output_path)
            return False

        logger.info("Successfully converted %s to %s at %s with extended tags.", input_path, output_path, DEFAULT_AUDIO_BITRATE)
        return True
    except Exception as e:
        # Catch-all ensures unexpected errors are logged while preserving behavior
        logger.error("Unhandled exception in convert_to_mp3_320kbps for %s: %s", input_path, e)
        if file_system_adapter.exists(output_path):
            _safe_remove_file(output_path)
        return False


def validate_mp3_320kbps(file_path: str, expected_duration_ms: int | None = None, duration_tolerance_ms: int = DEFAULT_DURATION_TOLERANCE_MS) -> bool:
    """
    Validates if a file is an MP3, has a bitrate of approximately 320kbps,
    and optionally matches an expected duration within a tolerance.

    Args:
        file_path: Path to the audio file.
        expected_duration_ms: Expected duration of the audio in milliseconds.
        duration_tolerance_ms: Tolerance for the duration check in milliseconds.

    Returns:
        True if validation passes, False otherwise.
    """
    try:
        _validate_path_string(file_path, "file_path")
    except ValueError as ve:
        logger.error("Invalid argument: %s", ve)
        return False

    if not file_system_adapter.exists(file_path):
        logger.warning("Validation failed: File %s does not exist.", file_path)
        return False

    try:
        info = audio_adapter.mediainfo(file_path)
    except FileNotFoundError:
        logger.error("Media file not found when attempting mediainfo: %s", file_path)
        return False
    except OSError as ose:
        logger.error("OS error while running mediainfo on %s: %s", file_path, ose)
        return False
    except Exception as e:
        logger.error("Unexpected error while retrieving media info for %s: %s", file_path, e)
        return False

    if not _is_format_and_bitrate_320(info):
        file_format = str(info.get("format_name", ""))
        bit_rate_str = str(info.get("bit_rate", "0"))
        try:
            bit_rate = int(bit_rate_str)
        except (ValueError, TypeError):
            bit_rate = 0
        logger.warning("Validation failed for %s: Format=%s, Bitrate=%sbps. Expected MP3 and ~320kbps.", file_path, file_format, bit_rate)
        return False

    if expected_duration_ms is not None:
        try:
            actual_duration_ms = _get_audio_duration_ms(file_path)
            lower_bound = expected_duration_ms - duration_tolerance_ms
            upper_bound = expected_duration_ms + duration_tolerance_ms

            if not (lower_bound <= actual_duration_ms <= upper_bound):
                logger.warning(
                    "Validation failed for %s: Duration mismatch. Expected %sms, got %sms (Tolerance: %sms).",
                    file_path,
                    expected_duration_ms,
                    actual_duration_ms,
                    duration_tolerance_ms,
                )
                return False
            logger.info("Duration validation successful for %s: Expected %sms, got %sms.", file_path, expected_duration_ms, actual_duration_ms)
        except CouldntDecodeError as cde:
            logger.error("Could not decode file to determine duration %s: %s", file_path, cde)
            return False
        except FileNotFoundError:
            logger.error("File disappeared while attempting to get duration: %s", file_path)
            return False
        except OSError as ose:
            logger.error("OS error while computing duration for %s: %s", file_path, ose)
            return False
        except Exception as e:
            logger.error("Unexpected error while computing duration for %s: %s", file_path, e)
            return False

    logger.info("Validation successful for %s.", file_path)
    return True


# Example usage (for testing this module directly):
if __name__ == "__main__":
    # This part would require actual audio files and ffmpeg to be installed
    # For now, it serves as a placeholder for direct module testing.

    # Create dummy directories and files for testing
    if not os.path.exists("temp_audio"):
        os.makedirs("temp_audio")

    input_dummy_file = "temp_audio/test_input.wav"  # Replace with a real audio file for testing
    output_dummy_file = "temp_audio/test_output.mp3"

    # Create a simple dummy wav to test conversion if it doesn't exist
    if not os.path.exists(input_dummy_file):
        try:
            print(f"Creating dummy input file: {input_dummy_file}")
            AudioSegment.silent(duration=1000).export(input_dummy_file, format="wav")
        except Exception as e:
            print(f"Could not create dummy input file for testing: {e}")
            print("Please ensure ffmpeg is installed and in your PATH, or pydub is configured with its location.")
            print("Skipping direct test of audio_processor.py")

    if os.path.exists(input_dummy_file):
        print("\n--- Testing Audio Conversion (with extended metadata) ---")
        # Create a dummy cover image for testing
        dummy_cover_path = "temp_audio/dummy_cover.jpg"
        try:
            from PIL import Image  # type: ignore
            img = Image.new("RGB", (60, 30), color="red")
            img.save(dummy_cover_path)
            print(f"Created dummy cover image: {dummy_cover_path}")
        except ImportError:
            print("Pillow library not found, skipping dummy cover image creation for test.")
            dummy_cover_path = None
        except Exception as e:
            print(f"Could not create dummy cover image: {e}")
            dummy_cover_path = None

        if convert_to_mp3_320kbps(
            input_dummy_file,
            output_dummy_file,
            artist="Test Artist",
            title="Test Title",
            album="Test Album",
            track_number="1/10",
            year="2023",
            cover_image_path=dummy_cover_path,
        ):
            print(f"Conversion test potentially successful (output: {output_dummy_file})")

            print("\n--- Testing Audio Validation (with duration) ---")
            # For this test, we don't have an original Spotify duration, so we skip that part of validation here
            if validate_mp3_320kbps(output_dummy_file, expected_duration_ms=None):
                print("Validation test successful (format, bitrate).")
            else:
                print("Validation test failed (format, bitrate).")

            # Clean up dummy output file
            if os.path.exists(output_dummy_file):
                os.remove(output_dummy_file)
        else:
            print("Conversion test failed.")

        if dummy_cover_path and os.path.exists(dummy_cover_path):
            os.remove(dummy_cover_path)
        # Clean up dummy input file
        if os.path.exists(input_dummy_file) and "test_input.wav" in input_dummy_file:
            os.remove(input_dummy_file)
        if os.path.exists("temp_audio"):
            try:
                os.rmdir("temp_audio")  # Only removes if empty
            except OSError:
                pass  # Directory might not be empty if other files were created
    else:
        print(f"Skipping audio_processor tests as input file {input_dummy_file} was not available/creatable.")