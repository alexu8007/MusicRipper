import os
import stat
import tempfile
import unittest

from src.external_tools import candidate_dirs, configure_ffmpeg, find_tool, locate_ffmpeg


def make_executable(folder, name):
    path = os.path.join(folder, name)
    with open(path, "w") as f:
        f.write("#!/bin/sh\n")
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
    return path


class FFmpegLocatorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.bin = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_ffmpeg_path_can_be_a_folder(self):
        ffmpeg = make_executable(self.bin, "ffmpeg")
        ffprobe = make_executable(self.bin, "ffprobe")
        tools = locate_ffmpeg(env={"PATH": "", "FFMPEG_PATH": self.bin}, platform="linux")
        self.assertEqual((tools.ffmpeg, tools.ffprobe), (ffmpeg, ffprobe))
        self.assertTrue(tools.ok)

    def test_ffprobe_is_found_next_to_ffmpeg_path_file(self):
        ffmpeg = make_executable(self.bin, "ffmpeg")
        ffprobe = make_executable(self.bin, "ffprobe")
        tools = locate_ffmpeg(env={"PATH": "", "FFMPEG_PATH": ffmpeg}, platform="linux")
        self.assertEqual(tools.ffprobe, ffprobe)

    def test_invalid_override_is_reported(self):
        tools = locate_ffmpeg(env={"PATH": "", "FFMPEG_PATH": os.path.join(self.bin, "missing")}, platform="linux")
        self.assertIsNone(tools.ffmpeg)
        self.assertIn("FFMPEG_PATH is set to", tools.problems[0])

    def test_windows_exe_found_in_install_folder_not_on_path(self):
        # Mirrors C:\ffmpeg\bin\ffmpeg.exe with nothing on PATH.
        expected = make_executable(self.bin, "ffmpeg.exe")
        self.assertEqual(find_tool("ffmpeg", extra_dirs=[self.bin], platform="win32", env={"PATH": ""}), expected)

    def test_windows_candidates_include_common_install_locations(self):
        env = {"LOCALAPPDATA": r"C:\Users\me\AppData\Local", "USERPROFILE": r"C:\Users\me"}
        dirs = candidate_dirs("win32", env)
        self.assertIn(r"C:\ffmpeg\bin", dirs)
        self.assertIn(r"C:\Users\me\AppData\Local\Microsoft\WinGet\Links", dirs)
        self.assertIn(r"C:\Users\me\scoop\shims", dirs)

    def test_configure_prepends_folder_to_path_for_pydub(self):
        make_executable(self.bin, "ffmpeg")
        make_executable(self.bin, "ffprobe")
        env = {"PATH": "/some/where", "FFMPEG_PATH": self.bin}
        configure_ffmpeg(env=env, platform="linux")
        self.assertEqual(env["PATH"].split(os.pathsep)[0], self.bin)
        configure_ffmpeg(env=env, platform="linux")  # idempotent
        self.assertEqual(env["PATH"].split(os.pathsep).count(self.bin), 1)


if __name__ == "__main__":
    unittest.main()
