import os
import tempfile
import unittest

from src.audio_processor import (
    FFMPEG_TOOLS, AudioProcessingError, choose_output_bitrate_kbps, convert_to_mp3, describe_quality,
    probe_audio, validate_mp3,
)


class ChooseOutputBitrateTests(unittest.TestCase):
    def test_never_encodes_above_the_source(self):
        self.assertEqual(choose_output_bitrate_kbps(128), 128)
        self.assertEqual(choose_output_bitrate_kbps(160), 160)
        self.assertEqual(choose_output_bitrate_kbps(165), 160)
        self.assertEqual(choose_output_bitrate_kbps(256), 256)

    def test_approximate_source_bitrates_round_to_the_matching_standard_rate(self):
        self.assertEqual(choose_output_bitrate_kbps(129.5), 128)  # e.g. YouTube m4a
        self.assertEqual(choose_output_bitrate_kbps(124), 128)

    def test_capped_at_maximum(self):
        self.assertEqual(choose_output_bitrate_kbps(1411), 320)  # lossless source
        self.assertEqual(choose_output_bitrate_kbps(256, max_kbps=192), 192)

    def test_unknown_source_uses_maximum(self):
        self.assertEqual(choose_output_bitrate_kbps(None), 320)

    def test_very_low_source_uses_lowest_rate(self):
        self.assertEqual(choose_output_bitrate_kbps(20), 32)


class DescribeQualityTests(unittest.TestCase):
    def test_reports_source_quality(self):
        label = describe_quality(choose_output_bitrate_kbps(128), 128, "mp3")
        self.assertEqual(label, "MP3 128 kbps (source: mp3 ~128 kbps)")
        self.assertNotIn("320", label)

    def test_unknown_source_is_labelled_unknown(self):
        self.assertEqual(describe_quality(320, None, "opus"), "MP3 320 kbps (source: opus, bitrate unknown)")


@unittest.skipUnless(FFMPEG_TOOLS.ffmpeg and FFMPEG_TOOLS.ffprobe, "needs ffmpeg and ffprobe")
class ConversionTests(unittest.TestCase):
    def setUp(self):
        from pydub.generators import Sine
        self.tmp = tempfile.TemporaryDirectory()
        self.source = os.path.join(self.tmp.name, "tone.wav")
        Sine(440).to_audio_segment(duration=3000).export(self.source, format="wav").close()

    def tearDown(self):
        self.tmp.cleanup()

    def test_convert_and_validate(self):
        output = os.path.join(self.tmp.name, "tone.mp3")
        convert_to_mp3(self.source, output, 128, artist="A", title="T", comment="Source: test")
        info = validate_mp3(output, expected_bitrate_kbps=128, expected_duration_ms=3000)
        self.assertEqual(info.codec, "mp3")
        self.assertAlmostEqual(info.bitrate_kbps, 128, delta=2)

    def test_validation_explains_duration_mismatch(self):
        output = os.path.join(self.tmp.name, "tone.mp3")
        convert_to_mp3(self.source, output, 128)
        with self.assertRaisesRegex(AudioProcessingError, "length is 0:03 but Spotify says 3:20"):
            validate_mp3(output, expected_duration_ms=200000)

    def test_validation_explains_bitrate_mismatch(self):
        output = os.path.join(self.tmp.name, "tone.mp3")
        convert_to_mp3(self.source, output, 128)
        with self.assertRaisesRegex(AudioProcessingError, "bitrate is 128 kbps, expected 320 kbps"):
            validate_mp3(output, expected_bitrate_kbps=320)

    def test_conversion_error_says_what_failed(self):
        broken = os.path.join(self.tmp.name, "broken.m4a")
        with open(broken, "wb") as f:
            f.write(b"not audio")
        with self.assertRaisesRegex(AudioProcessingError, "FFmpeg could not decode the downloaded file broken.m4a"):
            convert_to_mp3(broken, os.path.join(self.tmp.name, "out.mp3"), 128)
        with self.assertRaisesRegex(AudioProcessingError, "ffprobe could not read broken.m4a"):
            probe_audio(broken)


if __name__ == "__main__":
    unittest.main()
