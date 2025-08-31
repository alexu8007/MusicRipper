# src/audio_processor.py
"""Handles audio processing tasks like conversion and validation."""

import os
import logging
from typing import Callable, Dict, Optional

from pydub import AudioSegment
from pydub.utils import mediainfo

from .config import DEFAULT_AUDIO_FORMAT, DEFAULT_AUDIO_BITRATE
from .utils import sanitize_filename

logger = logging.getLogger(__name__)

# Default tolerance for duration check in milliseconds (e.g., 5 seconds)
DEFAULT_DURATION_TOLERANCE_MS = 5000

# Adapter/wrapper functions for external dependencies.
# Tests can replace these with mocks by calling set_audio_adapters.
_audio_from_file: Callable[[str], AudioSegment] = AudioSegment.from_file
_audio_export: Callable[[AudioSegment, str], None] = lambda audio, path, **kwargs: audio.export(path, **kwargs)
_get_mediainfo: Callable[[str], Dict[str, str]] = mediainfo


def set_audio_adapters(
    from_file: Optional[Callable[[str], AudioSegment]] = None,
    export: Optional[Callable[[AudioSegment, str], None]] = None,
    mediainfo_func: Optional[Callable[[str], Dict[str, str]]] = None,
) -> None:
    """
    Allows injection of alternative implementations for audio handling functions.
    Useful for tests to avoid calling ffmpeg/pydub.

    Args:
        from_file: Callable that loads audio from a path and returns an AudioSegment.
        export: Callable that exports an AudioSegment to a path with kwargs.
        mediainfo_func: Callable that returns media info dict for a file path.
    """
    global _audio_from_file, _audio_export, _get_mediainfo
    if from_file is not None:
        _audio_from_file = from_file
    if export is not None:
        _audio_export = export
    if mediainfo_func is not None:
        _get_mediainfo = mediainfo_func


def _ensure_output_directory(output_path: str) -> None:
    """Create output directory if it does not exist."""
    dir_name = os.path.dirname(output_path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)


def _build_export_tags(
    artist: str,
    title: str,
    album: Optional[str],
    track_number: Optional[str],
    year: Optional[str],
) -> Dict[str, str]:
    """Construct ID3 tags dictionary used by pydub/ffmpeg during export."""
    tags: Dict[str, str] = {"artist": artist, "title": title}
    if album:
        tags["album"] = album
    if track_number:
        tags["tracknumber"] = track_number  # pydub/ffmpeg usually expect 'tracknumber'
    if year:
        tags["date"] = year  # pydub/ffmpeg usually expect 'date' for year
    return tags


def _embed_cover_if_present(export_params: Dict, cover_image_path: Optional[str]) -> None:
    """Add cover image to export params if file exists; otherwise log and skip."""
    if not cover_image_path:
        return
    if os.path.exists(cover_image_path):
        export_params["cover"] = cover_image_path
        logger.info("Embedding cover art from: %s", cover_image_path)
    else:
        logger.warning(
            "Cover image path provided (%s) but file not found. Skipping cover art.", cover_image_path
        )


def _safe_remove_file(path: str) -> None:
    """Attempt to remove a file, logging any errors."""
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError as rm_e:
        logger.error("Could not remove partially created/failed output file %s: %s", path, rm_e)


def _parse_bitrate(info: Dict[str, str]) -> int:
    """Parse bitrate from mediainfo dict safely, defaulting to 0 on failure."""
    bit_rate_str = info.get("bit_rate", "0")
    try:
        return int(bit_rate_str)
    except (ValueError, TypeError):
        logger.debug("Could not parse bit_rate '%s' from mediainfo; defaulting to 0", bit_rate_str)
        return 0


def _get_duration_ms_from_mediainfo(info: Dict[str, str]) -> Optional[int]:
    """
    Attempt to get duration in milliseconds from mediainfo output.
    Returns None if duration is not present or cannot be parsed.
    """
    duration_str = info.get("duration")
    if not duration_str:
        return None
    try:
        # duration is in seconds (float) according to ffprobe/mediainfo output
        duration_seconds = float(duration_str)
        return int(duration_seconds * 1000)
    except (ValueError, TypeError) as e:
        logger.debug("Unable to parse duration '%s' from mediainfo: %s", duration_str, e)
        return None


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
    Converts an audio file to MP3 format at 320kbps and writes ID3 metadata.

    This function preserves the original observable behavior:
    - Returns True on success, False on any failure.
    - Attempts to remove any partially created output file on failure.

    Input validation is performed early to fail fast for obvious issues.

    Note on filename sanitization:
    - Only the basename (the filename component) of output_path is sanitized.
      Directory components are intentionally left intact to preserve output
      path semantics and avoid unintended directory renaming. If basename
      sanitization raises TypeError or ValueError, a warning is logged and the
      original basename is used as a fallback.

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
    logger.info("Attempting to convert %s to MP3 320kbps with extended metadata.", input_path)

    if not input_path or not output_path:
        logger.error("Input and output paths must be provided.")
        return False

    if not os.path.exists(input_path):
        logger.warning("Conversion failed: Input file %s does not exist.", input_path)
        return False

    # Sanitize only the basename (filename) component of the output_path.
    # Do not alter directory components. If sanitize_filename raises TypeError
    # or ValueError, fall back to the original basename to preserve path semantics.
    original_output_path = output_path
    output_dirname = os.path.dirname(original_output_path)
    basename = os.path.basename(original_output_path)

    try:
        sanitized_basename = sanitize_filename(basename)
    except (TypeError, ValueError) as e:
        logger.warning(
            "Basename sanitization failed for '%s': %s. Falling back to original basename.", basename, e
        )
        sanitized_basename = basename

    # Reconstruct the output path using the original directory and the (possibly) sanitized basename.
    if output_dirname:
        output_path = os.path.join(output_dirname, sanitized_basename)
    else:
        output_path = sanitized_basename

    # Ensure the original output directory exists. Do not pass a sanitized/underscored directory.
    _ensure_output_directory(original_output_path)

    tags = _build_export_tags(artist, title, album, track_number, year)

    export_params = {
        "format": DEFAULT_AUDIO_FORMAT,
        "bitrate": DEFAULT_AUDIO_BITRATE,
        "tags": tags,
    }

    _embed_cover_if_present(export_params, cover_image_path)

    try:
        # Use adapter to load audio. This may raise FileNotFoundError, OSError,
        # or pydub's decode errors; we catch common ones explicitly below.
        audio = _audio_from_file(input_path)
        # Export uses the injected adapter; use kwargs so tests can verify received params.
        _audio_export(audio, output_path, **export_params)
        logger.info(
            "Successfully converted %s to %s at %s with extended tags.",
            input_path,
            output_path,
            DEFAULT_AUDIO_BITRATE,
        )
        return True

    except FileNotFoundError as fnf:
        logger.error("Input file not found during conversion: %s", fnf)
        _safe_remove_file(output_path)
        return False

    except OSError as ose:
        # OSError can indicate IO problems (disk full, permission denied)
        logger.error("OS error during conversion of %s: %s", input_path, ose)
        _safe_remove_file(output_path)
        return False

    except Exception as e:
        # Last-resort catch to preserve original boolean-return semantics.
        # Log full exception stack trace for troubleshooting.
        logger.exception("Unexpected error converting %s to MP3: %s", input_path, e)
        _safe_remove_file(output_path)
        return False


def validate_mp3_320kbps(
    file_path: str,
    expected_duration_ms: Optional[int] = None,
    duration_tolerance_ms: int = DEFAULT_DURATION_TOLERANCE_MS,
) -> bool:
    """
    Validates that a file is MP3 and approximately 320kbps and optionally
    matches an expected duration within a given tolerance.

    This function tries to be streaming-friendly by using mediainfo to
    read metadata (including duration) rather than loading the entire
    file into memory. If mediainfo lacks duration information, it falls
    back to loading the audio via the adapter.

    Args:
        file_path: Path to the audio file.
        expected_duration_ms: Expected duration of the audio in milliseconds.
        duration_tolerance_ms: Tolerance for duration check in milliseconds.

    Returns:
        True if validation passes, False otherwise.
    """
    if not file_path:
        logger.warning("Validation failed: No file path provided.")
        return False

    if not os.path.exists(file_path):
        logger.warning("Validation failed: File %s does not exist.", file_path)
        return False

    try:
        info = _get_mediainfo(file_path)
    except FileNotFoundError as fnf:
        logger.error("Mediainfo failed, file not found: %s", fnf)
        return False
    except OSError as ose:
        logger.error("Mediainfo encountered OS error for %s: %s", file_path, ose)
        return False
    except Exception as e:
        logger.exception("Unexpected error while obtaining mediainfo for %s: %s", file_path, e)
        return False

    file_format = info.get("format_name", "").lower()
    bit_rate = _parse_bitrate(info)

    is_mp3 = "mp3" in file_format
    # Allow small tolerance around 320kbps (in bits per second: 320000)
    is_320kbps = (315000 <= bit_rate <= 325000)

    if not (is_mp3 and is_320kbps):
        logger.warning(
            "Validation failed for %s: Format=%s, Bitrate=%sbps. Expected MP3 and ~320kbps.",
            file_path,
            file_format,
            bit_rate,
        )
        return False

    # Duration check: prefer mediainfo (streaming-friendly). Fallback to loading audio if needed.
    if expected_duration_ms is not None:
        actual_duration_ms = _get_duration_ms_from_mediainfo(info)

        if actual_duration_ms is None:
            # Fall back to loading audio if mediainfo did not provide duration
            try:
                audio = _audio_from_file(file_path)
                actual_duration_ms = int(audio.duration_seconds * 1000)
            except FileNotFoundError as fnf:
                logger.error("File not found when trying to read duration: %s", fnf)
                return False
            except OSError as ose:
                logger.error("OS error when trying to read duration of %s: %s", file_path, ose)
                return False
            except Exception as e:
                logger.exception("Unexpected error while reading duration of %s: %s", file_path, e)
                return False

        # Compute allowed range for duration
        lower_bound = expected_duration_ms - duration_tolerance_ms
        upper_bound = expected_duration_ms + duration_tolerance_ms

        # If outside tolerance, validation fails
        if not (lower_bound <= actual_duration_ms <= upper_bound):
            logger.warning(
                "Validation failed for %s: Duration mismatch. Expected %dms, got %dms (Tolerance: %dms).",
                file_path,
                expected_duration_ms,
                actual_duration_ms,
                duration_tolerance_ms,
            )
            return False

        logger.info(
            "Duration validation successful for %s: Expected %dms, got %dms.",
            file_path,
            expected_duration_ms,
            actual_duration_ms,
        )

    logger.info(
        "Validation successful for %s: Format=%s, Bitrate=%sbps.",
        file_path,
        file_format,
        bit_rate,
    )
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
            print("Creating dummy input file: %s" % input_dummy_file)
            AudioSegment.silent(duration=1000).export(input_dummy_file, format="wav")
        except Exception as e:
            print("Could not create dummy input file for testing: %s" % e)
            print("Please ensure ffmpeg is installed and in your PATH, or pydub is configured with its location.")
            print("Skipping direct test of audio_processor.py")

    if os.path.exists(input_dummy_file):
        print("\n--- Testing Audio Conversion (with extended metadata) ---")
        # Create a dummy cover image for testing
        dummy_cover_path = "temp_audio/dummy_cover.jpg"
        try:
            from PIL import Image  # PIL/Pillow is a common dependency, pydub might use it or similar internally

            img = Image.new("RGB", (60, 30), color="red")
            img.save(dummy_cover_path)
            print("Created dummy cover image: %s" % dummy_cover_path)
        except ImportError:
            print("Pillow library not found, skipping dummy cover image creation for test.")
            dummy_cover_path = None  # No cover for test
        except Exception as e:
            print("Could not create dummy cover image: %s" % e)
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
            print("Conversion test potentially successful (output: %s)" % output_dummy_file)

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
        print("Skipping audio_processor tests as input file %s was not available/creatable." % input_dummy_file)