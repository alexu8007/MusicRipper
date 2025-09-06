# src/audio_processor.py
"""Handles audio processing tasks like conversion and validation."""

import os
import logging
from typing import Optional, Dict, Any

from pydub import AudioSegment
from pydub.utils import mediainfo

from .config import DEFAULT_AUDIO_FORMAT, DEFAULT_AUDIO_BITRATE
from .utils import sanitize_filename

logger = logging.getLogger(__name__)

# Default tolerance for duration check in milliseconds (e.g., 5 seconds)
DEFAULT_DURATION_TOLERANCE_MS = 5000


def _ensure_output_dir(output_path: str) -> bool:
    """Ensure the directory for output_path exists. Returns True on success."""
    directory = os.path.dirname(output_path)
    if not directory:
        # No directory to create (file in current working dir)
        return True
    try:
        os.makedirs(directory, exist_ok=True)
        return True
    except OSError as os_err:
        logger.error(f"Could not create output directory {directory}: {os_err}")
        return False


def _build_export_tags(artist: str, title: str, album: Optional[str],
                       track_number: Optional[str], year: Optional[str]) -> Dict[str, str]:
    """Builds a tags dictionary for pydub export based on provided metadata."""
    tags: Dict[str, str] = {"artist": artist, "title": title}
    if album:
        tags["album"] = album
    if track_number:
        tags["tracknumber"] = track_number  # pydub/ffmpeg usually expect 'tracknumber'
    if year:
        tags["date"] = year  # pydub/ffmpeg usually expect 'date' for year
    return tags


def _embed_cover_if_exists(export_params: Dict[str, Any], cover_image_path: Optional[str]) -> None:
    """If cover image exists, add it to export params; otherwise log diagnostic info."""
    if cover_image_path:
        if os.path.exists(cover_image_path):
            export_params["cover"] = cover_image_path
            logger.info(f"Embedding cover art from: {cover_image_path}")
        else:
            logger.warning(
                f"Cover image path provided ({cover_image_path}) but file not found. Skipping cover art."
            )


def _remove_file_if_exists(path: str) -> None:
    """Attempt to remove a file if it exists, logging failures but not raising."""
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError as rm_err:
        logger.error(f"Could not remove partially created/failed output file {path}: {rm_err}")


def _load_audio_segment(input_path: str) -> AudioSegment:
    """Load an AudioSegment from a file. May raise FileNotFoundError, OSError, or pydub decode errors."""
    return AudioSegment.from_file(input_path)


def _export_audio_segment(audio: AudioSegment, output_path: str, export_params: Dict[str, Any]) -> None:
    """Export an AudioSegment to disk with provided parameters. May raise OSError or related errors."""
    audio.export(output_path, **export_params)


def convert_to_mp3_320kbps(
    input_path: str,
    output_path: str,
    artist: str = "Unknown Artist",
    title: str = "Unknown Title",
    album: Optional[str] = None,
    track_number: Optional[str] = None,
    year: Optional[str] = None,
    cover_image_path: Optional[str] = None,
) -> bool:
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
    # Basic input validation
    if not isinstance(input_path, str) or not input_path:
        logger.error("convert_to_mp3_320kbps: input_path must be a non-empty string.")
        return False
    if not isinstance(output_path, str) or not output_path:
        logger.error("convert_to_mp3_320kbps: output_path must be a non-empty string.")
        return False

    logger.info(f"Attempting to convert {input_path} to MP3 320kbps with extended metadata.")
    # Ensure output directory exists before doing heavy work
    if not _ensure_output_dir(output_path):
        return False

    try:
        audio = _load_audio_segment(input_path)
    except FileNotFoundError as fnf_err:
        logger.error(f"Input file not found: {fnf_err}")
        return False
    except (OSError, ValueError) as load_err:
        logger.error(f"Error loading audio file {input_path}: {load_err}")
        return False
    except Exception as unexpected_err:  # deliberate catch-all for unexpected pydub errors
        logger.error(f"Unexpected error loading audio file {input_path}: {unexpected_err}")
        return False

    tags = _build_export_tags(artist, title, album, track_number, year)

    export_params: Dict[str, Any] = {
        "format": DEFAULT_AUDIO_FORMAT,
        "bitrate": DEFAULT_AUDIO_BITRATE,
        "tags": tags,
    }

    _embed_cover_if_exists(export_params, cover_image_path)

    try:
        _export_audio_segment(audio, output_path, export_params)
        logger.info(
            f"Successfully converted {input_path} to {output_path} at {DEFAULT_AUDIO_BITRATE} with extended tags."
        )
        return True
    except (OSError, FileNotFoundError) as export_err:
        logger.error(f"Error exporting audio to {output_path}: {export_err}")
        _remove_file_if_exists(output_path)
        return False
    except Exception as unexpected_export_err:
        # Documented deliberate swallow: anything else is treated as conversion failure and cleaned up.
        logger.error(f"Unexpected error during export for {output_path}: {unexpected_export_err}")
        _remove_file_if_exists(output_path)
        return False


def _safe_get_mediainfo(file_path: str) -> Dict[str, Any]:
    """Wrapper around mediainfo that returns a dict or empty dict on failure."""
    try:
        return mediainfo(file_path) or {}
    except FileNotFoundError:
        logger.warning(f"mediainfo: file not found {file_path}")
        return {}
    except OSError as os_err:
        logger.error(f"mediainfo OSError for {file_path}: {os_err}")
        return {}
    except Exception as unexpected_err:
        logger.error(f"Unexpected mediainfo error for {file_path}: {unexpected_err}")
        return {}


def _parse_bitrate(bit_rate_str: Optional[str]) -> int:
    """Parse bitrate string to integer bits per second, return 0 on failure."""
    if not bit_rate_str:
        return 0
    try:
        return int(bit_rate_str)
    except (ValueError, TypeError):
        # Some files may contain non-numeric or None values; treat as 0 so validation fails gracefully.
        return 0


def _get_duration_ms(file_path: str) -> Optional[int]:
    """Return duration in milliseconds for a file, or None if it cannot be read."""
    try:
        audio = _load_audio_segment(file_path)
        return int(audio.duration_seconds * 1000)
    except FileNotFoundError:
        logger.error(f"Duration check failed: file not found {file_path}")
        return None
    except (OSError, ValueError) as dur_err:
        logger.error(f"Error reading duration for {file_path}: {dur_err}")
        return None
    except Exception as unexpected_err:
        logger.error(f"Unexpected error reading duration for {file_path}: {unexpected_err}")
        return None


def validate_mp3_320kbps(
    file_path: str,
    expected_duration_ms: Optional[int] = None,
    duration_tolerance_ms: int = DEFAULT_DURATION_TOLERANCE_MS,
) -> bool:
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
    # Input validation
    if not isinstance(file_path, str) or not file_path:
        logger.warning("Validation failed: file_path must be a non-empty string.")
        return False
    if not os.path.exists(file_path):
        logger.warning(f"Validation failed: File {file_path} does not exist.")
        return False

    info = _safe_get_mediainfo(file_path)
    if not info:
        logger.error(f"Validation failed: could not read media info for {file_path}.")
        return False

    file_format = str(info.get("format_name", "")).lower()
    bit_rate_str = info.get("bit_rate", "0")

    is_mp3 = "mp3" in file_format

    bit_rate = _parse_bitrate(bit_rate_str)
    # Allowing a small tolerance around 320kbps (in bits per second)
    is_320kbps = 315000 <= bit_rate <= 325000

    if not (is_mp3 and is_320kbps):
        logger.warning(
            f"Validation failed for {file_path}: Format={file_format}, Bitrate={bit_rate}bps. Expected MP3 and ~320kbps."
        )
        return False

    # Duration Check (if expected_duration_ms is provided)
    if expected_duration_ms is not None:
        actual_duration_ms = _get_duration_ms(file_path)
        if actual_duration_ms is None:
            # Fail validation if duration can't be read
            logger.error(f"Error getting duration for {file_path}: duration could not be determined.")
            return False

        lower_bound = expected_duration_ms - duration_tolerance_ms
        upper_bound = expected_duration_ms + duration_tolerance_ms

        if not (lower_bound <= actual_duration_ms <= upper_bound):
            logger.warning(
                f"Validation failed for {file_path}: Duration mismatch. Expected {expected_duration_ms}ms, "
                f"got {actual_duration_ms}ms (Tolerance: {duration_tolerance_ms}ms)."
            )
            return False

        logger.info(
            f"Duration validation successful for {file_path}: Expected {expected_duration_ms}ms, got {actual_duration_ms}ms."
        )

    logger.info(f"Validation successful for {file_path}: Format={file_format}, Bitrate={bit_rate}bps.")
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
        print(f"\n--- Testing Audio Conversion (with extended metadata) ---")
        # Create a dummy cover image for testing
        dummy_cover_path = "temp_audio/dummy_cover.jpg"
        try:
            from PIL import Image  # PIL/Pillow is a common dependency, pydub might use it or similar internally

            img = Image.new("RGB", (60, 30), color="red")
            img.save(dummy_cover_path)
            print(f"Created dummy cover image: {dummy_cover_path}")
        except ImportError:
            print("Pillow library not found, skipping dummy cover image creation for test.")
            dummy_cover_path = None  # No cover for test
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

            print(f"\n--- Testing Audio Validation (with duration) ---")
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