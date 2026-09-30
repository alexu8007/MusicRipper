# src/audio_processor.py
"""Handles audio processing tasks like conversion and validation."""

import os
import json
import logging
import subprocess
from dataclasses import dataclass

from .external_tools import configure_ffmpeg

# Must run before pydub is imported: pydub looks for ffmpeg on PATH at import time.
FFMPEG_TOOLS = configure_ffmpeg()

from pydub import AudioSegment  # noqa: E402
from pydub.exceptions import CouldntDecodeError, CouldntEncodeError  # noqa: E402

if FFMPEG_TOOLS.ffmpeg:
    AudioSegment.converter = FFMPEG_TOOLS.ffmpeg

from .config import DEFAULT_AUDIO_FORMAT, MAX_OUTPUT_BITRATE_KBPS  # noqa: E402
from .utils import format_duration  # noqa: E402

logger = logging.getLogger(__name__)

# Default tolerance for duration check in milliseconds (e.g., 5 seconds)
DEFAULT_DURATION_TOLERANCE_MS = 5000
# CBR encodes land on their target; this only absorbs rounding in what ffprobe reports.
BITRATE_TOLERANCE = 0.03
STANDARD_MP3_BITRATES_KBPS = (32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320)
# Sites report approximate bitrates (e.g. 129.5 kbps for a 128 kbps stream); treat those as equal.
SOURCE_BITRATE_SLACK = 1.05
MISSING_FFMPEG_HINT = "see README, 'Install FFmpeg and FFprobe', or set FFMPEG_PATH in .env"


class AudioProcessingError(Exception):
    """Probing, conversion or validation failed; the message says why."""


@dataclass
class AudioInfo:
    format_name: str
    codec: str | None
    bitrate_kbps: float | None
    duration_ms: int | None


def choose_output_bitrate_kbps(source_kbps: float | None, max_kbps: int = MAX_OUTPUT_BITRATE_KBPS) -> int:
    """Picks the MP3 bitrate for a (usually lossy) source.

    Re-encoding can't restore detail the source never had, so the output is never
    encoded above the source bitrate: a 128 kbps source becomes a 128 kbps MP3, not
    a 320 kbps file that merely looks better. If the source bitrate is unknown we
    use max_kbps so nothing is lost, and the quality label says it is unknown.
    """
    if not source_kbps:
        return max_kbps
    allowed = [rate for rate in STANDARD_MP3_BITRATES_KBPS
               if rate <= max_kbps and rate <= source_kbps * SOURCE_BITRATE_SLACK]
    return allowed[-1] if allowed else STANDARD_MP3_BITRATES_KBPS[0]


def describe_quality(output_kbps: int, source_kbps: float | None, source_codec: str | None = None) -> str:
    """Quality label that reports the source, e.g. 'MP3 128 kbps (source: opus ~130 kbps)'."""
    if source_kbps:
        source = f"{source_codec + ' ' if source_codec else ''}~{round(source_kbps)} kbps"
    else:
        source = f"{source_codec + ', ' if source_codec else ''}bitrate unknown"
    return f"MP3 {output_kbps} kbps (source: {source})"


def _ffmpeg_reason(error: Exception) -> str:
    """pydub errors embed FFmpeg's whole stderr; the last meaningful line is the actual cause."""
    lines = [line.strip() for line in str(error).splitlines() if line.strip()]
    lines = [line for line in lines if line != "Conversion failed!"]
    return lines[-1] if lines else type(error).__name__


def _remove_partial(path: str) -> None:
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError as e:
            logger.error(f"Could not remove partially created/failed output file {path}: {e}")


def probe_audio(file_path: str) -> AudioInfo:
    """Reads format, codec, bitrate and duration of the first audio stream with ffprobe."""
    name = os.path.basename(file_path)
    command = [FFMPEG_TOOLS.ffprobe or "ffprobe", "-v", "error", "-print_format", "json",
               "-show_format", "-show_streams", "-select_streams", "a:0", file_path]
    try:
        completed = subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace", timeout=60)
    except FileNotFoundError as e:
        raise AudioProcessingError(f"ffprobe was not found ({MISSING_FFMPEG_HINT})") from e
    except subprocess.TimeoutExpired as e:
        raise AudioProcessingError(f"ffprobe timed out while reading {name}") from e
    if completed.returncode != 0:
        details = completed.stderr.strip().splitlines()
        raise AudioProcessingError(f"ffprobe could not read {name}: {details[-1] if details else 'unknown error'}")

    data = json.loads(completed.stdout or "{}")
    streams = data.get("streams") or []
    if not streams:
        raise AudioProcessingError(f"{name} contains no audio stream")
    stream, container = streams[0], data.get("format", {})
    # The container bitrate also counts embedded cover art, so prefer the stream's own value.
    bit_rate = stream.get("bit_rate") or container.get("bit_rate")
    duration = stream.get("duration") or container.get("duration")
    return AudioInfo(
        format_name=container.get("format_name", ""),
        codec=stream.get("codec_name"),
        bitrate_kbps=int(bit_rate) / 1000 if bit_rate and str(bit_rate).isdigit() else None,
        duration_ms=int(float(duration) * 1000) if duration not in (None, "N/A") else None,
    )


def convert_to_mp3(input_path: str, output_path: str,
                   bitrate_kbps: int,
                   artist: str = "Unknown Artist",
                   title: str = "Unknown Title",
                   album: str | None = None,
                   track_number: str | None = None,
                   year: str | None = None,
                   cover_image_path: str | None = None,
                   comment: str | None = None) -> None:
    """
    Converts an audio file to MP3 at the given bitrate (see choose_output_bitrate_kbps).
    Adds ID3 tags for artist, title, album, track number, year, comment, and cover art.

    Args:
        input_path: Path to the input audio file.
        output_path: Path to save the converted MP3 file.
        bitrate_kbps: Target constant bitrate in kbps.
        artist: Song artist for ID3 tag.
        title: Song title for ID3 tag.
        album: Album name for ID3 tag.
        track_number: Track number for ID3 tag.
        year: Release year for ID3 tag.
        cover_image_path: Path to the cover image file.
        comment: Free text for the ID3 comment tag (we record the source and its quality).

    Raises:
        AudioProcessingError: with the reason FFmpeg failed.
    """
    name = os.path.basename(input_path)
    if not os.path.exists(input_path):
        raise AudioProcessingError(f"downloaded file {input_path} is missing")

    logger.info(f"Attempting to convert {input_path} to MP3 {bitrate_kbps}kbps with extended metadata.")
    try:
        audio = AudioSegment.from_file(input_path)
    except CouldntDecodeError as e:
        raise AudioProcessingError(f"FFmpeg could not decode the downloaded file {name}: {_ffmpeg_reason(e)}") from e
    except FileNotFoundError as e:
        raise AudioProcessingError(f"FFmpeg/FFprobe was not found ({MISSING_FFMPEG_HINT})") from e

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
    if comment:
        tags["comment"] = comment

    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    export_params = {
        "format": DEFAULT_AUDIO_FORMAT,
        "bitrate": f"{bitrate_kbps}k",
        "tags": tags
    }

    if cover_image_path and os.path.exists(cover_image_path):
        export_params["cover"] = cover_image_path
        logger.info(f"Embedding cover art from: {cover_image_path}")
    elif cover_image_path:
        logger.warning(f"Cover image path provided ({cover_image_path}) but file not found. Skipping cover art.")

    try:
        # export() returns the open output file; close it so it can be moved/deleted (Windows).
        audio.export(output_path, **export_params).close()
    except CouldntEncodeError as e:
        _remove_partial(output_path)
        raise AudioProcessingError(f"FFmpeg could not encode the MP3: {_ffmpeg_reason(e)}") from e
    except FileNotFoundError as e:
        _remove_partial(output_path)
        raise AudioProcessingError(f"FFmpeg was not found ({MISSING_FFMPEG_HINT})") from e
    except OSError as e:
        _remove_partial(output_path)
        raise AudioProcessingError(f"could not write {output_path}: {e}") from e
    logger.info(f"Successfully converted {input_path} to {output_path} at {bitrate_kbps}kbps with extended tags.")


def validate_mp3(file_path: str, expected_bitrate_kbps: int | None = None,
                 expected_duration_ms: int | None = None,
                 duration_tolerance_ms: int = DEFAULT_DURATION_TOLERANCE_MS) -> AudioInfo:
    """
    Validates that a file is an MP3, optionally encoded at the expected bitrate
    and matching an expected duration within a tolerance.

    Args:
        file_path: Path to the audio file.
        expected_bitrate_kbps: Bitrate the file was encoded at, if known.
        expected_duration_ms: Expected duration of the audio in milliseconds.
        duration_tolerance_ms: Tolerance for the duration check in milliseconds.

    Returns:
        The probed AudioInfo.

    Raises:
        AudioProcessingError: describing which check failed.
    """
    if not os.path.exists(file_path):
        raise AudioProcessingError(f"{file_path} does not exist")

    info = probe_audio(file_path)
    if "mp3" not in info.format_name.lower() and info.codec != "mp3":
        raise AudioProcessingError(f"{os.path.basename(file_path)} is not an MP3 (format: {info.format_name or 'unknown'})")

    if expected_bitrate_kbps:
        if info.bitrate_kbps is None:
            raise AudioProcessingError(f"could not read the bitrate of {os.path.basename(file_path)}")
        if abs(info.bitrate_kbps - expected_bitrate_kbps) > expected_bitrate_kbps * BITRATE_TOLERANCE:
            raise AudioProcessingError(
                f"MP3 bitrate is {info.bitrate_kbps:.0f} kbps, expected {expected_bitrate_kbps} kbps")

    # Duration Check (if expected_duration_ms is provided)
    if expected_duration_ms is not None:
        if info.duration_ms is None:
            raise AudioProcessingError(f"could not read the duration of {os.path.basename(file_path)}")
        if abs(info.duration_ms - expected_duration_ms) > duration_tolerance_ms:
            raise AudioProcessingError(
                f"length is {format_duration(info.duration_ms)} but Spotify says "
                f"{format_duration(expected_duration_ms)} (allowed difference: {duration_tolerance_ms // 1000}s)")
        logger.info(f"Duration validation successful for {file_path}: Expected {expected_duration_ms}ms, got {info.duration_ms}ms.")

    logger.info(f"Validation successful for {file_path}: Format={info.format_name}, Bitrate={info.bitrate_kbps}kbps.")
    return info

# Example usage (for testing this module directly):
if __name__ == "__main__":
    # This part requires ffmpeg to be installed.
    # Run from the project root with: python -m src.audio_processor

    # Create dummy directories and files for testing
    if not os.path.exists("temp_audio"):
        os.makedirs("temp_audio")

    input_dummy_file = "temp_audio/test_input.wav" # Replace with a real audio file for testing
    output_dummy_file = "temp_audio/test_output.mp3"

    # Create a simple dummy wav to test conversion if it doesn't exist
    if not os.path.exists(input_dummy_file):
        try:
            print(f"Creating dummy input file: {input_dummy_file}")
            # CD-quality stereo; pydub's default 11025 Hz mono can't reach normal MP3 bitrates.
            AudioSegment.silent(duration=1000, frame_rate=44100).set_channels(2).export(input_dummy_file, format="wav").close()
        except Exception as e:
            print(f"Could not create dummy input file for testing: {e}")
            print("Please ensure ffmpeg is installed and in your PATH, or set FFMPEG_PATH in .env.")
            print("Skipping direct test of audio_processor.py")


    if os.path.exists(input_dummy_file):
        print(f"\n--- Testing Audio Conversion (with extended metadata) ---")
        # Create a dummy cover image for testing
        dummy_cover_path = "temp_audio/dummy_cover.jpg"
        try:
            from PIL import Image # Optional; only used to make a test cover image
            img = Image.new('RGB', (60, 30), color = 'red')
            img.save(dummy_cover_path)
            print(f"Created dummy cover image: {dummy_cover_path}")
        except ImportError:
            print("Pillow library not found, skipping dummy cover image creation for test.")
            dummy_cover_path = None # No cover for test
        except Exception as e:
            print(f"Could not create dummy cover image: {e}")
            dummy_cover_path = None

        source_info = probe_audio(input_dummy_file)
        bitrate = choose_output_bitrate_kbps(source_info.bitrate_kbps)
        try:
            convert_to_mp3(input_dummy_file, output_dummy_file, bitrate,
                           artist="Test Artist", title="Test Title",
                           album="Test Album", track_number="1/10", year="2023",
                           cover_image_path=dummy_cover_path)
            print(f"Conversion test successful (output: {output_dummy_file}, "
                  f"{describe_quality(bitrate, source_info.bitrate_kbps, source_info.codec)})")

            print(f"\n--- Testing Audio Validation ---")
            # For this test, we don't have an original Spotify duration, so we skip that part of validation here
            try:
                validate_mp3(output_dummy_file, expected_bitrate_kbps=bitrate)
                print("Validation test successful (format, bitrate).")
            except AudioProcessingError as e:
                print(f"Validation test failed: {e}")

            # Clean up dummy output file
            if os.path.exists(output_dummy_file):
                os.remove(output_dummy_file)
        except AudioProcessingError as e:
            print(f"Conversion test failed: {e}")

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
