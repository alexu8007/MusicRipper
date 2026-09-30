# src/external_tools.py
"""Locates the external programs Music Ripper relies on (FFmpeg, FFprobe, and a
JavaScript runtime for yt-dlp's YouTube support).

pydub only looks for ffmpeg/ffprobe on PATH, and ignores AudioSegment.ffprobe
entirely when probing files, so an install that isn't on PATH (for example
C:\\ffmpeg\\bin on Windows) is never found. configure_ffmpeg() searches the usual
install locations and prepends the folder to PATH so pydub picks it up.

Only uses the standard library: dependency_check imports it before any
third-party package is known to be importable.
"""

import glob
import os
import shutil
import sys
from dataclasses import dataclass, field

# yt-dlp runtime key -> executable name
JS_RUNTIMES = {"deno": "deno", "node": "node", "bun": "bun", "quickjs": "qjs"}


@dataclass
class FFmpegTools:
    ffmpeg: str | None = None
    ffprobe: str | None = None
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.ffmpeg and self.ffprobe) and not self.problems


def candidate_dirs(platform: str | None = None, env=None) -> list[str]:
    """Glob patterns for folders where FFmpeg is commonly installed."""
    platform = platform or sys.platform
    env = os.environ if env is None else env

    if platform.startswith("win"):
        program_files = [env.get("ProgramFiles", r"C:\Program Files"),
                         env.get("ProgramFiles(x86)", r"C:\Program Files (x86)")]
        patterns = [r"C:\ffmpeg\bin", r"C:\ffmpeg", r"C:\ffmpeg*\bin"]  # manual zip extracts
        for base in program_files:
            patterns += [base + r"\ffmpeg\bin", base + r"\ffmpeg*\bin"]
        if env.get("LOCALAPPDATA"):  # winget
            patterns += [env["LOCALAPPDATA"] + r"\Microsoft\WinGet\Links",
                         env["LOCALAPPDATA"] + r"\Microsoft\WinGet\Packages\Gyan.FFmpeg*\ffmpeg-*\bin"]
        patterns.append(env.get("ProgramData", r"C:\ProgramData") + r"\chocolatey\bin")
        if env.get("USERPROFILE"):  # scoop
            patterns += [env["USERPROFILE"] + r"\scoop\shims",
                         env["USERPROFILE"] + r"\scoop\apps\ffmpeg\current\bin"]
        return patterns

    if platform == "darwin":
        return ["/opt/homebrew/bin", "/usr/local/bin", "/opt/local/bin"]

    return ["/usr/bin", "/usr/local/bin", "/snap/bin", os.path.expanduser("~/.local/bin")]


def _executable_name(name: str, platform: str) -> str:
    return name + ".exe" if platform.startswith("win") else name


def _resolve_override(value: str, exe: str) -> str | None:
    """FFMPEG_PATH/FFPROBE_PATH may name the executable itself or its folder."""
    value = os.path.expanduser(value.strip().strip('"'))
    path = os.path.join(value, exe) if os.path.isdir(value) else value
    return os.path.abspath(path) if os.path.isfile(path) else None


def find_tool(name: str, extra_dirs=(), platform: str | None = None, env=None) -> str | None:
    """Finds an executable on PATH, then in extra_dirs, then in common install folders."""
    platform = platform or sys.platform
    env = os.environ if env is None else env
    exe = _executable_name(name, platform)

    found = shutil.which(exe, path=env.get("PATH"))
    if found:
        return os.path.abspath(found)

    for pattern in [*extra_dirs, *candidate_dirs(platform, env)]:
        for folder in sorted(glob.glob(pattern), reverse=True):  # newest versioned folder first
            path = os.path.join(folder, exe)
            if os.path.isfile(path):
                return os.path.abspath(path)
    return None


def _prepend_to_path(folder: str, env) -> None:
    entries = env.get("PATH", "").split(os.pathsep)
    normalized = {os.path.normcase(os.path.abspath(p)) for p in entries if p}
    if os.path.normcase(os.path.abspath(folder)) not in normalized:
        env["PATH"] = os.pathsep.join([folder, *[p for p in entries if p]])


def locate_ffmpeg(env=None, platform: str | None = None) -> FFmpegTools:
    env = os.environ if env is None else env
    platform = platform or sys.platform
    tools = FFmpegTools()

    for name, var in (("ffmpeg", "FFMPEG_PATH"), ("ffprobe", "FFPROBE_PATH")):
        override = env.get(var)
        if override:
            path = _resolve_override(override, _executable_name(name, platform))
            if not path:
                tools.problems.append(
                    f"{var} is set to '{override}', but no {_executable_name(name, platform)} was found there.")
        else:
            # ffprobe ships next to ffmpeg, so look beside it (and beside FFMPEG_PATH) first.
            extra = []
            if name == "ffprobe" and tools.ffmpeg:
                extra.append(os.path.dirname(tools.ffmpeg))
            path = find_tool(name, extra_dirs=extra, platform=platform, env=env)
        setattr(tools, name, path)
    return tools


def configure_ffmpeg(env=None, platform: str | None = None) -> FFmpegTools:
    """Locates FFmpeg/FFprobe and makes them visible to pydub (via PATH)."""
    env = os.environ if env is None else env
    tools = locate_ffmpeg(env, platform)
    for path in (tools.ffprobe, tools.ffmpeg):  # ffmpeg ends up first
        if path:
            _prepend_to_path(os.path.dirname(path), env)

    if "pydub" in sys.modules and tools.ffmpeg:
        from pydub import AudioSegment
        AudioSegment.converter = tools.ffmpeg
        if tools.ffprobe:
            AudioSegment.ffprobe = tools.ffprobe
    return tools


def find_js_runtimes(env=None) -> dict[str, dict]:
    """JavaScript runtimes available to yt-dlp, in its `js_runtimes` option format."""
    env = os.environ if env is None else env
    runtimes = {}
    for key, exe in JS_RUNTIMES.items():
        path = shutil.which(exe, path=env.get("PATH"))
        if path:
            runtimes[key] = {"path": path}
    return runtimes
