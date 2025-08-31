# src/audio_processor.py
"""Handles audio processing tasks like conversion and validation."""

import os
import logging
from typing import Callable, Optional, Dict, Any

from pydub import AudioSegment
from pydub.utils import mediainfo

from .config import DEFAULT_AUDIO_FORMAT, DEFAULT_AUDIO_BITRATE
from .utils import sanitize_filename

logger = logging.getLogger(__name__)

# Default tolerance for duration check in milliseconds (e.g., 5 seconds)
DEFAULT_DURATION_TOLERANCE_MS: int = 5000


def _build_id3_tags(artist: str,
                    title: str,
                    album: Optional[str] = None,
                    track_number: Optional[str] = None,
                    year: Optional[str] = None) -> Dict[str, str]:
    """
    Build a tags dictionary suitable for pydub/ffmpeg export.

    Args:
        artist: Artist name.
        title: Track title.
        album: Optional album name.
        track_number: Optional track number string.
        year: Optional release year string.

    Returns:
        A dict with tag keys/values.
    """
    tags: Dict[str, str] = {
        "artist": artist,
        "title": title,
    }
    if album:
        tags["album"] = album
    if track_number:
        # pydub/ffmpeg usually expect 'tracknumber'
        tags["tracknumber"] = track_number
    if year:
        # pydub/ffmpeg usually expect 'date' for year
        tags["date"] = year
    return tags


def _ensure_directory_for_file(file_path: str) -> None:
    """
    Ensure the parent directory for a given file path exists.

    Args:
        file_path: Path to a file for which the parent directory will be created.

    Raises:
        OSError: If the directory cannot be created.
    """
    dir_name = os.path.dirname(file_path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)


def _remove_file_safely(file_path: str) -> None:
    """
    Attempt to remove a file and log failures without raising.

    Args:
        file_path: Path to the file to remove.
    """
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
    except OSError as rm_e:
        logger.error("Could not remove partially created/failed output file %s: %s", file_path, rm_e)


def _safe_parse_bitrate(bit_rate_str: str) -> int:
    """
    Parse bitrate string into an integer number of bits per second.

    Args:
        bit_rate_str: Bitrate string from mediainfo.

    Returns:
        Parsed bitrate as int or 0 if parsing fails.
    """
    try:
        return int(bit_rate_str)
    except (ValueError, TypeError):
        logger.debug("Could not parse bitrate string '%s'; defaulting to 0", bit_rate_str)
        return 0


def _read_mediainfo(file_path: str, mediainfo_fn: Callable[[str], Dict[str, Any]]) -> Dict[str, Any]:
    """
    Wrapper around pydub.utils.mediainfo to allow dependency injection and error handling.

    Args:
        file_path: Path to the media file.
        mediainfo_fn: Callable that returns media info dictionary.

    Returns:
        Media info dictionary.

    Raises:
        FileNotFoundError: If file does not exist.
        RuntimeError: If mediainfo_fn raises or returns invalid data.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File does not exist: {file_path}")
    try:
        info = mediainfo_fn(file_path)
        if not isinstance(info, dict):
            raise RuntimeError("mediainfo function returned unexpected type")
        return info
    except Exception as e:
        logger.error("Error reading media info for %s: %s", file_path, e)
        raise


def convert_to_mp3_320kbps(input_path: str,
                           output_path: str,
                           artist: str = "Unknown Artist",
                           title: str = "Unknown Title",
                           album: Optional[str] = None,
                           track_number: Optional[str] = None,
                           year: Optional[str] = None,
                           cover_image_path: Optional[str] = None,
                           audio_loader: Callable[[str], AudioSegment] = AudioSegment.from_file) -> bool:
    """
    Converts an audio file to MP3 format at configured bitrate (default 320kbps).
    Adds ID3 tags for artist, title, album, track number, year, and cover art.

    Dependency injection is supported via the `audio_loader` parameter to allow
    tests to mock audio loading behavior.

    Args:
        input_path: Path to the input audio file.
        output_path: Path to save the converted MP3 file.
        artist: Song artist for ID3 tag.
        title: Song title for ID3 tag.
        album: Album name for ID3 tag.
        track_number: Track number for ID3 tag.
        year: Release year for ID3 tag.
        cover_image_path: Path to the cover image file.
        audio_loader: Callable that loads audio and returns an AudioSegment.

    Returns:
        True if conversion was successful, False otherwise.
    """
    try:
        logger.info("Attempting to convert %s to MP3 %s with extended metadata.", input_path, DEFAULT_AUDIO_BITRATE)

        if not os.path.exists(input_path):
            logger.warning("Input file for conversion does not exist: %s", input_path)
            return False

        # Load audio (may load entire file into memory depending on backend)
        try:
            audio: AudioSegment = audio_loader(input_path)
        except FileNotFoundError:
            logger.error("Input file not found during load: %s", input_path)
            return False
        except Exception as e:
            logger.error("Error loading audio file %s: %s", input_path, e)
            return False

        tags = _build_id3_tags(artist=artist, title=title, album=album, track_number=track_number, year=year)

        # Ensure output directory exists
        try:
            _ensure_directory_for_file(output_path)
        except OSError as e:
            logger.error("Could not create output directory for %s: %s", output_path, e)
            return False

        export_params: Dict[str, Any] = {
            "format": DEFAULT_AUDIO_FORMAT,
            "bitrate": DEFAULT_AUDIO_BITRATE,
            "tags": tags
        }

        if cover_image_path:
            if os.path.exists(cover_image_path):
                export_params["cover"] = cover_image_path
                logger.info("Embedding cover art from: %s", cover_image_path)
            else:
                logger.warning("Cover image path provided (%s) but file not found. Skipping cover art.", cover_image_path)

        try:
            # Export may create the file; guard and clean up on failure
            audio.export(output_path, **export_params)
            logger.info("Successfully converted %s to %s at %s with extended tags.", input_path, output_path, DEFAULT_AUDIO_BITRATE)
            return True
        except Exception as e:
            logger.error("Error exporting audio to %s: %s", output_path, e)
            _remove_file_safely(output_path)
            return False
    except Exception as e:
        # Catch-all to prevent unexpected exceptions from propagating while logging detail.
        logger.error("Unexpected error during conversion of %s: %s", input_path, e)
        _remove_file_safely(output_path)
        return False


def validate_mp3_320kbps(file_path: str,
                         expected_duration_ms: Optional[int] = None,
                         duration_tolerance_ms: int = DEFAULT_DURATION_TOLERANCE_MS,
                         mediainfo_fn: Callable[[str], Dict[str, Any]] = mediainfo,
                         audio_loader: Callable[[str], AudioSegment] = AudioSegment.from_file) -> bool:
    """
    Validates if a file is an MP3 and has a bitrate close to 320kbps,
    and optionally matches an expected duration within a tolerance.

    Dependency injection is supported for `mediainfo_fn` and `audio_loader` to
    facilitate testing and mocking of external libraries.

    Args:
        file_path: Path to the audio file.
        expected_duration_ms: Expected duration of the audio in milliseconds.
        duration_tolerance_ms: Tolerance for the duration check in milliseconds.
        mediainfo_fn: Function used to obtain media info (defaults to pydub.utils.mediainfo).
        audio_loader: Callable used to load audio when duration validation is required.

    Returns:
        True if validation passes, False otherwise.
    """
    if not os.path.exists(file_path):
        logger.warning("Validation failed: File %s does not exist.", file_path)
        return False

    try:
        info = _read_mediainfo(file_path, mediainfo_fn)

        file_format = str(info.get("format_name", "")).lower()
        bit_rate_str = info.get("bit_rate", "0")

        is_mp3 = "mp3" in file_format

        bit_rate = _safe_parse_bitrate(bit_rate_str)
        # Allowing a small tolerance around 320000 bps
        is_320kbps = (315_000 <= bit_rate <= 325_000)

        if not (is_mp3 and is_320kbps):
            logger.warning(
                "Validation failed for %s: Format=%s, Bitrate=%sbps. Expected MP3 and ~320kbps.",
                file_path,
                file_format,
                bit_rate,
            )
            return False

        # Duration Check (if expected_duration_ms is provided)
        if expected_duration_ms is not None:
            try:
                # Loading audio to inspect duration; injected loader helps testing.
                audio = audio_loader(file_path)
                actual_duration_ms = int(audio.duration_seconds * 1000)
                lower_bound = expected_duration_ms - duration_tolerance_ms
                upper_bound = expected_duration_ms + duration_tolerance_ms

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
            except FileNotFoundError:
                logger.error("File not found while validating duration: %s", file_path)
                return False
            except Exception as e:
                logger.error("Error getting duration for %s: %s", file_path, e)
                return False  # Fail validation if duration can't be read

        logger.info("Validation successful for %s: Format=%s, Bitrate=%sbps.", file_path, file_format, bit_rate)
        return True
    except FileNotFoundError:
        logger.warning("Validation failed: File %s does not exist.", file_path)
        return False
    except Exception as e:
        logger.error("Error validating %s: %s", file_path, e)
        return False


# Example usage (for testing this module directly):
if __name__ == "__main__":
    # This part would require actual audio files and ffmpeg to be installed
    # For now, it serves as a placeholder for direct module testing.
    
    # Create dummy directories and files for testing
    if not os.path.exists("temp_audio"):
        os.makedirs("temp_audio")
    
    # Create a dummy input file (e.g., a silent WAV or an actual test file)
    # For this example, we'll assume a test.wav exists or is created by other means.
    # To truly test this, you would need a sample audio file.
    # e.g., AudioSegment.silent(duration=1000).export("temp_audio/test.wav", format="wav")

    input_dummy_file = "temp_audio/test_input.wav" # Replace with a real audio file for testing
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
            from PIL import Image # PIL/Pillow is a common dependency, pydub might use it or similar internally
            img = Image.new('RGB', (60, 30), color = 'red')
            img.save(dummy_cover_path)
            print(f"Created dummy cover image: {dummy_cover_path}")
        except ImportError:
            print("Pillow library not found, skipping dummy cover image creation for test.")
            dummy_cover_path = None # No cover for test
        except Exception as e:
            print(f"Could not create dummy cover image: {e}")
            dummy_cover_path = None

        if convert_to_mp3_320kbps(input_dummy_file, output_dummy_file, 
                                 artist="Test Artist", title="Test Title", 
                                 album="Test Album", track_number="1/10", year="2023",
                                 cover_image_path=dummy_cover_path):
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
                os.rmdir("temp_audio") # Only removes if empty
            except OSError:
                pass # Directory might not be empty if other files were created
    else:
        print(f"Skipping audio_processor tests as input file {input_dummy_file} was not available/creatable.")