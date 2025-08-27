# src/audio_processor.py
"""Handles audio processing tasks like conversion and validation."""

import os
import logging
from typing import Optional, Dict, Any

from pydub import AudioSegment
from pydub.utils import mediainfo
from pydub.exceptions import CouldntDecodeError, CouldntEncodeError

from .config import DEFAULT_AUDIO_FORMAT, DEFAULT_AUDIO_BITRATE
from .utils import sanitize_filename

logger = logging.getLogger(__name__)

# Default tolerance for duration check in milliseconds (e.g., 5 seconds)
DEFAULT_DURATION_TOLERANCE_MS = 5000


def _ensure_output_directory(output_path: str) -> None:
    """Create the output directory if it does not exist. Safe no-op for empty dirname."""
    dirname = os.path.dirname(output_path)
    if dirname:
        try:
            os.makedirs(dirname, exist_ok=True)
        except OSError as e:
            logger.error(f"Could not create output directory '{dirname}': {e}")
            raise


def _build_tags(artist: str, title: str, album: Optional[str], track_number: Optional[str], year: Optional[str]) -> Dict[str, str]:
    """
    Build ID3/FFmpeg tag dictionary for exporting audio.
    
    Artist and title are always included. Optional fields are added when provided:
    - album -> "album"
    - track_number -> "tracknumber" (FFmpeg expects 'tracknumber')
    - year -> "date" (FFmpeg expects 'date')
    
    Returns:
        dict: Mapping of tag names to string values suitable for passing as `tags` to pydub/ffmpeg export.
    """
    tags: Dict[str, str] = {"artist": artist, "title": title}
    if album:
        tags["album"] = album
    if track_number:
        tags["tracknumber"] = track_number  # pydub/ffmpeg usually expect 'tracknumber'
    if year:
        tags["date"] = year  # pydub/ffmpeg usually expect 'date' for year
    return tags


def _prepare_export_params(tags: Dict[str, str], cover_image_path: Optional[str]) -> Dict[str, Any]:
    """
    Prepare the parameter dictionary for AudioSegment.export, including format, bitrate, tags, and optional cover art.
    
    If cover_image_path is provided and the file exists, the returned dict will include a "cover" key pointing to that path; if the path is provided but missing, cover art is omitted.
    
    Parameters:
        tags (Dict[str, str]): ID3-style tags to attach to the exported file (must include at least artist/title).
        cover_image_path (Optional[str]): Path to an image file to embed as cover art. If None or the file does not exist, no cover is embedded.
    
    Returns:
        Dict[str, Any]: Parameters suitable for passing to AudioSegment.export (keys include "format", "bitrate", "tags", and optionally "cover").
    """
    export_params: Dict[str, Any] = {
        "format": DEFAULT_AUDIO_FORMAT,
        "bitrate": DEFAULT_AUDIO_BITRATE,
        "tags": tags,
    }
    if cover_image_path:
        if os.path.exists(cover_image_path):
            export_params["cover"] = cover_image_path
            logger.info(f"Embedding cover art from: {cover_image_path}")
        else:
            logger.warning(f"Cover image path provided ({cover_image_path}) but file not found. Skipping cover art.")
    return export_params


def _remove_partial_file(path: str) -> None:
    """
    Remove a partially written file at the given path if it exists, suppressing exceptions.
    
    This is a best-effort cleanup: if the file at `path` exists the function attempts to unlink it and logs an error on failure but does not raise.
    
    Parameters:
        path (str): Filesystem path to the file to remove.
    """
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError as rm_e:
            logger.error(f"Could not remove partially created/failed output file {path}: {rm_e}")


def _get_mediainfo_safe(file_path: str) -> Optional[Dict[str, Any]]:
    """
    Safely obtain mediainfo metadata for a file, returning a dict on success or None on failure.
    
    This function calls pydub.utils.mediainfo(file_path) and normalizes failure modes so callers do not need to handle common filesystem or probing errors. If mediainfo returns a non-dict result or if an OSError/ValueError/other exception occurs, the function logs the problem and returns None instead of raising.
    Returns:
        Optional[Dict[str, Any]]: Parsed mediainfo dictionary on success, otherwise None.
    """
    try:
        info = mediainfo(file_path)
        if not isinstance(info, dict):
            logger.warning(f"mediainfo returned non-dict for {file_path}: {info}")
            return None
        return info
    except (OSError, ValueError) as e:
        logger.error(f"Error running mediainfo for {file_path}: {e}")
        return None
    except Exception as e:
        # Final fallback: log unexpected mediainfo errors and return None so callers can decide
        logger.exception(f"Unexpected error running mediainfo for {file_path}: {e}")
        return None


def _is_format_mp3(info: Dict[str, Any]) -> bool:
    """Check if mediainfo format indicates MP3."""
    file_format = str(info.get("format_name", "")).lower()
    return "mp3" in file_format


def _is_approx_320kbps(info: Dict[str, Any]) -> bool:
    """
    Return True if the given mediainfo dict indicates a bitrate of approximately 320 kbps.
    
    Expects a mediainfo-like mapping that may contain the keys "bit_rate" or "bitrate" whose value is an integer or numeric string denoting bitrate in bits per second. Values between 315000 and 325000 (±5 kbps around 320000 bps) are considered approximately 320 kbps. If the bitrate cannot be parsed, the function returns False.
        
    Parameters:
        info (Dict[str, Any]): Mediainfo dictionary (from pydub.utils.mediainfo) containing bitrate fields.
    
    Returns:
        bool: True when bitrate is within the 315000–325000 bps range, otherwise False.
    """
    bit_rate_str = info.get("bit_rate") or info.get("bitrate") or "0"
    try:
        bit_rate = int(bit_rate_str)
    except (TypeError, ValueError):
        logger.warning(f"Could not parse bitrate from mediainfo: {bit_rate_str}")
        return False
    # Allow ±5 kbps tolerance around 320 kbps (320000 bps)
    return 315000 <= bit_rate <= 325000


def _get_duration_ms_from_info(info: Dict[str, Any]) -> Optional[int]:
    """
    Extract duration from mediainfo and return it in milliseconds.
    
    This function looks for "duration_ms" or "duration" keys in the provided mediainfo-like dict and attempts to normalize the value to an integer number of milliseconds. Accepted input forms include:
    - numeric milliseconds (int/float > 1000),
    - numeric seconds (int/float < 1000; interpreted as seconds and converted to ms),
    - string representations of seconds or milliseconds (e.g., "3.5", "3500").
    
    Returns:
        int | None: Duration in milliseconds on successful parse, otherwise None if the value is missing or cannot be parsed.
    """
    duration_ms = None
    # Some mediainfo returns 'duration' in seconds as a string, sometimes with decimals.
    duration_value = info.get("duration_ms") or info.get("duration")
    if duration_value is not None:
        try:
            if isinstance(duration_value, (int, float)):
                duration_ms = int(float(duration_value) if duration_value >= 1 else duration_value * 1000)
            else:
                # String representation; try to parse float seconds first
                parsed = float(str(duration_value))
                # If parsed value looks like seconds (e.g., 3.5) assume seconds; if very large assume ms
                if parsed > 1000:
                    duration_ms = int(parsed)  # already ms
                else:
                    duration_ms = int(parsed * 1000)
        except (TypeError, ValueError) as e:
            logger.debug(f"Could not parse duration from mediainfo value '{duration_value}': {e}")
            duration_ms = None
    return duration_ms


def convert_to_mp3_320kbps(input_path: str, output_path: str, 
                           artist: str = "Unknown Artist", 
                           title: str = "Unknown Title", 
                           album: str | None = None, 
                           track_number: str | None = None, 
                           year: str | None = None, 
                           cover_image_path: str | None = None) -> bool:
    """
                           Convert an input audio file to MP3 at ~320 kbps, embedding ID3 tags and optional cover art.
                           
                           Attempts to load the input via pydub, ensures the output directory exists, and exports an MP3 file using the module's default format and bitrate. Optional metadata (artist, title, album, track number, year) is written into the file; a provided cover_image_path will be embedded only if the file exists. On export failure the function will remove any partially written output file.
                           
                           Returns:
                               bool: True if conversion and export completed successfully; False on any read, encode, or unexpected error (no file written or partial files cleaned up).
                           """
    try:
        logger.info(f"Attempting to convert {input_path} to MP3 320kbps with extended metadata.")
        # Load input audio - pydub will use ffmpeg/avlib under the hood; this step can raise decode errors.
        try:
            audio = AudioSegment.from_file(input_path)
        except (FileNotFoundError, CouldntDecodeError, OSError) as e:
            logger.error(f"Could not read input file '{input_path}': {e}")
            return False

        tags = _build_tags(artist, title, album, track_number, year)

        # Ensure output directory exists
        try:
            _ensure_output_directory(output_path)
        except OSError:
            # _ensure_output_directory already logged details
            return False

        export_params = _prepare_export_params(tags, cover_image_path)

        # Exporting through pydub delegates to ffmpeg which streams to the output path;
        # pydub handles writing in a stream-like manner so we avoid additional buffering here.
        try:
            audio.export(output_path, **export_params)
            logger.info(f"Successfully converted {input_path} to {output_path} at {DEFAULT_AUDIO_BITRATE} with extended tags.")
            return True
        except (CouldntEncodeError, OSError) as e:
            logger.error(f"Error exporting audio to '{output_path}': {e}")
            _remove_partial_file(output_path)
            return False
    except Exception as e:
        # Unexpected error: log full exception and perform safe cleanup then return False.
        logger.exception(f"Unexpected error converting {input_path} to MP3: {e}")
        _remove_partial_file(output_path)
        return False


def validate_mp3_320kbps(file_path: str, expected_duration_ms: int | None = None, duration_tolerance_ms: int = DEFAULT_DURATION_TOLERANCE_MS) -> bool:
    """
    Validate that a file is an MP3 encoded at approximately 320 kbps and, optionally, that its duration matches an expected value within a tolerance.
    
    Performs non-destructive checks using mediainfo for format, bitrate, and (preferably) duration. If mediainfo does not provide a reliable duration and a duration check is requested, the function falls back to loading the file with pydub to compute duration. Duration comparison uses a symmetric tolerance in milliseconds.
    
    Parameters:
        file_path (str): Path to the file to validate.
        expected_duration_ms (int | None): If provided, the expected duration in milliseconds; when None no duration check is performed.
        duration_tolerance_ms (int): Allowed deviation (±) in milliseconds for the duration check (default: DEFAULT_DURATION_TOLERANCE_MS).
    
    Returns:
        bool: True if the file is MP3, has an approximate 320 kbps bitrate, and (when requested) its duration falls within the specified tolerance; otherwise False.
    """
    if not os.path.exists(file_path):
        logger.warning(f"Validation failed: File {file_path} does not exist.")
        return False

    info = _get_mediainfo_safe(file_path)
    if info is None:
        logger.error(f"Could not retrieve mediainfo for {file_path}; failing validation.")
        return False

    try:
        if not (_is_format_mp3(info) and _is_approx_320kbps(info)):
            file_format = info.get("format_name", "")
            bit_rate_str = info.get("bit_rate", "0")
            logger.warning(f"Validation failed for {file_path}: Format={file_format}, Bitrate={bit_rate_str}bps. Expected MP3 and ~320kbps.")
            return False

        # Duration Check (if expected_duration_ms is provided). Prefer mediainfo value to avoid loading audio into memory.
        if expected_duration_ms is not None:
            actual_duration_ms = _get_duration_ms_from_info(info)
            if actual_duration_ms is None:
                # Fallback: load file to compute duration if mediainfo lacks reliable info.
                try:
                    audio = AudioSegment.from_file(file_path)
                    actual_duration_ms = int(audio.duration_seconds * 1000)
                except (FileNotFoundError, CouldntDecodeError, OSError) as e:
                    logger.error(f"Error getting duration for {file_path} via pydub: {e}")
                    return False
                except Exception as e:
                    logger.exception(f"Unexpected error getting duration for {file_path}: {e}")
                    return False

            lower_bound = expected_duration_ms - duration_tolerance_ms
            upper_bound = expected_duration_ms + duration_tolerance_ms

            if not (lower_bound <= actual_duration_ms <= upper_bound):
                logger.warning(
                    f"Validation failed for {file_path}: Duration mismatch. "
                    f"Expected {expected_duration_ms}ms, got {actual_duration_ms}ms (Tolerance: {duration_tolerance_ms}ms)."
                )
                return False
            logger.info(f"Duration validation successful for {file_path}: Expected {expected_duration_ms}ms, got {actual_duration_ms}ms.")

        logger.info(f"Validation successful for {file_path}: Format={info.get('format_name')}, Bitrate={info.get('bit_rate')}.")
        return True
    except Exception as e:
        # Catch-all to preserve previous behavior of returning False on unexpected errors,
        # while ensuring the error is logged with full context.
        logger.exception(f"Error validating {file_path}: {e}")
        return False


# Example usage (for testing this module directly):
if __name__ == "__main__":
    # This part would require actual audio files and ffmpeg to be installed
    # For now, it serves as a placeholder for direct module testing.

    # Create dummy directories and files for testing
    if not os.path.exists("temp_audio"):
        try:
            os.makedirs("temp_audio")
        except OSError as e:
            print(f"Could not create temp_audio directory for testing: {e}")

    input_dummy_file = "temp_audio/test_input.wav"  # Replace with a real audio file for testing
    output_dummy_file = "temp_audio/test_output.mp3"

    # Create a simple dummy wav to test conversion if it doesn't exist
    if not os.path.exists(input_dummy_file):
        try:
            print(f"Creating dummy input file: {input_dummy_file}")
            AudioSegment.silent(duration=1000).export(input_dummy_file, format="wav")
        except (OSError, CouldntEncodeError) as e:
            print(f"Could not create dummy input file for testing: {e}")
            print("Please ensure ffmpeg is installed and in your PATH, or pydub is configured with its location.")
            print("Skipping direct test of audio_processor.py")
        except Exception as e:
            print(f"Could not create dummy input file for testing (unexpected error): {e}")
            print("Skipping direct test of audio_processor.py")

    if os.path.exists(input_dummy_file):
        print(f"\n--- Testing Audio Conversion (with extended metadata) ---")
        # Create a dummy cover image for testing
        dummy_cover_path = "temp_audio/dummy_cover.jpg"
        try:
            from PIL import Image  # PIL/Pillow is a common dependency, pydub might use it or similar internally
            img = Image.new('RGB', (60, 30), color='red')
            img.save(dummy_cover_path)
            print(f"Created dummy cover image: {dummy_cover_path}")
        except ImportError:
            print("Pillow library not found, skipping dummy cover image creation for test.")
            dummy_cover_path = None  # No cover for test
        except OSError as e:
            print(f"Could not create dummy cover image: {e}")
            dummy_cover_path = None
        except Exception as e:
            print(f"Could not create dummy cover image (unexpected error): {e}")
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
                try:
                    os.remove(output_dummy_file)
                except OSError:
                    pass
        else:
            print("Conversion test failed.")

        if dummy_cover_path and os.path.exists(dummy_cover_path):
            try:
                os.remove(dummy_cover_path)
            except OSError:
                pass
        # Clean up dummy input file
        if os.path.exists(input_dummy_file) and "test_input.wav" in input_dummy_file:
            try:
                os.remove(input_dummy_file)
            except OSError:
                pass
        if os.path.exists("temp_audio"):
            try:
                os.rmdir("temp_audio")  # Only removes if empty
            except OSError:
                pass
    else:
        print(f"Skipping audio_processor tests as input file {input_dummy_file} was not available/creatable.")