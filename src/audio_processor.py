# src/audio_processor.py
"""Handles audio processing tasks like conversion and validation."""

import os
import logging
from pydub import AudioSegment
from pydub.utils import mediainfo

from .config import DEFAULT_AUDIO_FORMAT, DEFAULT_AUDIO_BITRATE
from .utils import sanitize_filename

logger = logging.getLogger(__name__)

# Default tolerance for duration check in milliseconds (e.g., 5 seconds)
DEFAULT_DURATION_TOLERANCE_MS = 5000

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
        logger.info(f"Attempting to convert {input_path} to MP3 320kbps with extended metadata.")
        audio = AudioSegment.from_file(input_path)
        
        tags = {
            "artist": artist,
            "title": title,
        }
        if album:
            tags["album"] = album
        if track_number:
            tags["tracknumber"] = track_number # pydub/ffmpeg usually expect 'tracknumber'
        if year:
            tags["date"] = year # pydub/ffmpeg usually expect 'date' for year
        
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        export_params = {
            "format": DEFAULT_AUDIO_FORMAT,
            "bitrate": DEFAULT_AUDIO_BITRATE,
            "tags": tags
        }

        if cover_image_path and os.path.exists(cover_image_path):
            export_params["cover"] = cover_image_path
            logger.info(f"Embedding cover art from: {cover_image_path}")
        elif cover_image_path:
            logger.warning(f"Cover image path provided ({cover_image_path}) but file not found. Skipping cover art.")

        audio.export(output_path, **export_params)
        logger.info(f"Successfully converted {input_path} to {output_path} at {DEFAULT_AUDIO_BITRATE} with extended tags.")
        return True
    except Exception as e:
        logger.error(f"Error converting {input_path} to MP3: {e}")
        # If output_path was created despite error, remove it
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except OSError as rm_e:
                logger.error(f"Could not remove partially created/failed output file {output_path}: {rm_e}")
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
    if not os.path.exists(file_path):
        logger.warning(f"Validation failed: File {file_path} does not exist.")
        return False

    try:
        info = mediainfo(file_path)
        # print(f"Media Info for {file_path}: {info}") # For debugging
        
        file_format = info.get("format_name", "").lower()
        bit_rate_str = info.get("bit_rate", "0")
        
        is_mp3 = "mp3" in file_format
        
        # Bitrate can sometimes be slightly off, e.g., 320000 vs 319999
        # We check if it's close to 320000 (320 kbps)
        bit_rate = int(bit_rate_str)
        is_320kbps = (315000 <= bit_rate <= 325000) # Allowing a small tolerance

        if not (is_mp3 and is_320kbps):
            logger.warning(f"Validation failed for {file_path}: Format={file_format}, Bitrate={bit_rate}bps. Expected MP3 and ~320kbps.")
            return False
        
        # Duration Check (if expected_duration_ms is provided)
        if expected_duration_ms is not None:
            try:
                audio = AudioSegment.from_file(file_path)
                actual_duration_ms = int(audio.duration_seconds * 1000)
                lower_bound = expected_duration_ms - duration_tolerance_ms
                upper_bound = expected_duration_ms + duration_tolerance_ms

                if not (lower_bound <= actual_duration_ms <= upper_bound):
                    logger.warning(f"Validation failed for {file_path}: Duration mismatch. Expected {expected_duration_ms}ms, got {actual_duration_ms}ms (Tolerance: {duration_tolerance_ms}ms).")
                    return False
                logger.info(f"Duration validation successful for {file_path}: Expected {expected_duration_ms}ms, got {actual_duration_ms}ms.")
            except Exception as e:
                logger.error(f"Error getting duration for {file_path}: {e}")
                return False # Fail validation if duration can't be read

        logger.info(f"Validation successful for {file_path}: Format={file_format}, Bitrate={bit_rate}bps.")
        return True
    except Exception as e:
        logger.error(f"Error validating {file_path}: {e}")
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