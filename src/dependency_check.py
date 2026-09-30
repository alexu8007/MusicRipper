# src/dependency_check.py
"""Startup checks for the Python version, package versions, FFmpeg/FFprobe,
yt-dlp's YouTube helpers and the Spotify settings in .env.

Only uses the standard library at import time, so it can explain what is wrong
before a missing or outdated package fails with an ImportError traceback.

Run `python -m src.dependency_check` from the project root for a full report.
Set the environment variable MUSICRIPPER_SKIP_CHECKS=1 to bypass the checks.
"""

import datetime
import importlib.metadata
import importlib.util
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from urllib.parse import urlparse

from .external_tools import configure_ffmpeg, find_js_runtimes

MIN_PYTHON = (3, 10)
YTDLP_MAX_AGE_DAYS = 90
INSTALL_HINT = "pip install -r requirements.txt"
YTDLP_UPDATE_HINT = 'pip install -U "yt-dlp[default]"'
LOOPBACK_HOSTS = ("127.0.0.1", "::1")


@dataclass(frozen=True)
class Requirement:
    name: str          # distribution name on PyPI
    min_version: str   # oldest version known to work
    why: str
    optional: bool = False


REQUIREMENTS = (
    Requirement("spotipy", "2.26.0",
                "older versions call Spotify's removed /playlists/{id}/tracks endpoint and get HTTP 403"),
    Requirement("yt-dlp", "2026.8.19",
                "older versions can no longer search or download from YouTube and SoundCloud"),
    Requirement("pydub", "0.25.1", "needed to convert audio"),
    Requirement("requests", "2.32.3", "needed to download cover art"),
    Requirement("python-dotenv", "1.1.0", "needed to read .env"),
    Requirement("rich", "14.0.0", "needed for the console interface"),
    Requirement("Pillow", "11.3.0",
                "optional, only used by the audio_processor self-test; 11.3.0 is the first release "
                "that installs on Python 3.14", optional=True),
)


@dataclass
class CheckResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    found: list[str] = field(default_factory=list)  # what was detected, for the full report


def parse_version(text: str) -> tuple[int, ...]:
    """'2026.08.19' -> (2026, 8, 19); ignores suffixes like '.dev0' or 'rc1'."""
    match = re.match(r"\d+(?:\.\d+)*", text.strip())
    return tuple(int(part) for part in match.group(0).split(".")) if match else ()


def installed_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def check_python(result: CheckResult, version_info=sys.version_info) -> None:
    current = ".".join(str(part) for part in version_info[:3])
    result.found.append(f"Python {current}")
    if tuple(version_info[:2]) < MIN_PYTHON:
        result.errors.append(
            f"Python {current} is too old. Music Ripper needs Python "
            f"{MIN_PYTHON[0]}.{MIN_PYTHON[1]} or newer (yt-dlp and other dependencies require it).")
    elif tuple(version_info[:2]) >= (3, 13) and importlib.util.find_spec("audioop") is None:
        result.errors.append(
            f"Python {current} no longer includes the 'audioop' module that pydub needs. "
            f"Fix: pip install audioop-lts (or {INSTALL_HINT}).")


def check_packages(result: CheckResult, get_version=installed_version) -> None:
    for req in REQUIREMENTS:
        installed = get_version(req.name)
        problems = result.warnings if req.optional else result.errors
        if installed is None:
            problems.append(f"{req.name} is not installed ({req.why}). Fix: {INSTALL_HINT}")
        elif parse_version(installed) < parse_version(req.min_version):
            problems.append(
                f"{req.name} {installed} is too old; version {req.min_version} or newer is required "
                f"({req.why}). Fix: {INSTALL_HINT}")
        else:
            result.found.append(f"{req.name} {installed}")


def check_ytdlp_freshness(result: CheckResult, version: str | None, today: datetime.date | None = None) -> None:
    """yt-dlp versions are release dates; old releases break as sites change."""
    parts = parse_version(version or "")
    if len(parts) < 3:
        return
    try:
        released = datetime.date(*parts[:3])
    except ValueError:
        return
    age_days = ((today or datetime.date.today()) - released).days
    if age_days > YTDLP_MAX_AGE_DAYS:
        result.warnings.append(
            f"yt-dlp {version} is {age_days} days old. YouTube and SoundCloud change often and old "
            f"yt-dlp releases stop working; if downloads fail, update it: {YTDLP_UPDATE_HINT}")


def check_youtube_support(result: CheckResult, runtimes: dict | None = None) -> None:
    runtimes = find_js_runtimes() if runtimes is None else runtimes
    if runtimes:
        result.found.append("JavaScript runtime for YouTube: " + ", ".join(runtimes))
    else:
        result.warnings.append(
            "No JavaScript runtime (Deno, Node.js, Bun or QuickJS) was found. yt-dlp needs one for full "
            "YouTube support; without it YouTube downloads may fail or offer fewer formats. "
            "Install Deno: https://docs.deno.com/runtime/getting_started/installation/")
    if installed_version("yt-dlp") and importlib.util.find_spec("yt_dlp_ejs") is None:
        result.warnings.append(
            f"yt-dlp-ejs is not installed, so yt-dlp can't solve YouTube's JavaScript challenges. "
            f"Fix: {YTDLP_UPDATE_HINT}")


def _tool_version(path: str) -> str:
    """Runs `<tool> -version` and returns the version token, raising on failure."""
    completed = subprocess.run([path, "-version"], capture_output=True, text=True, timeout=15)
    if completed.returncode != 0:
        output = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(output.splitlines()[-1] if output else f"exit code {completed.returncode}")
    first_line = completed.stdout.splitlines()[0] if completed.stdout else ""
    match = re.search(r"version\s+(\S+)", first_line)
    return match.group(1) if match else "unknown version"


def check_ffmpeg(result: CheckResult) -> None:
    tools = configure_ffmpeg()
    result.errors.extend(tools.problems)
    missing = []
    for name in ("ffmpeg", "ffprobe"):
        path = getattr(tools, name)
        if not path:
            if not any(name.upper() + "_PATH" in problem for problem in tools.problems):
                missing.append(name)
            continue
        try:
            result.found.append(f"{name} {_tool_version(path)} ({path})")
        except (OSError, subprocess.SubprocessError, RuntimeError) as e:
            result.errors.append(f"{name} was found at {path} but could not be run: {e}")
    if missing:
        result.errors.append(
            f"{' and '.join(missing)} {'were' if len(missing) > 1 else 'was'} not found. pydub needs both "
            f"ffmpeg and ffprobe to convert audio. Install FFmpeg (see README, 'Install FFmpeg and FFprobe'), "
            f"or set FFMPEG_PATH in .env to the folder that contains ffmpeg and ffprobe, "
            f"e.g. FFMPEG_PATH=C:\\ffmpeg\\bin")


def check_spotify_config(result: CheckResult, client_id: str | None, client_secret: str | None,
                         redirect_uri: str) -> None:
    if not client_id or not client_secret:
        result.errors.append(
            "Spotify credentials are missing. Set SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET in .env "
            "(see README, 'Spotify setup').")

    parsed = urlparse(redirect_uri)
    fix = ("Use http://127.0.0.1:8888/callback and add exactly the same URI under Redirect URIs in your "
           "Spotify app's settings.")
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        result.errors.append(f"SPOTIPY_REDIRECT_URI '{redirect_uri}' is not a valid URL. {fix}")
    elif parsed.hostname == "localhost":
        result.errors.append(
            f"SPOTIPY_REDIRECT_URI '{redirect_uri}' uses 'localhost', which Spotify no longer accepts. {fix}")
    elif parsed.scheme == "http" and parsed.hostname not in LOOPBACK_HOSTS:
        result.errors.append(
            f"SPOTIPY_REDIRECT_URI '{redirect_uri}' must use https unless it points to a loopback address. {fix}")
    elif parsed.hostname in LOOPBACK_HOSTS and not parsed.port:
        result.warnings.append(
            f"SPOTIPY_REDIRECT_URI '{redirect_uri}' has no port, so the Spotify login can't be captured "
            f"automatically and you'll be asked to paste the redirected URL. {fix}")
    else:
        result.found.append(f"Spotify redirect URI: {redirect_uri}")


def run_checks() -> CheckResult:
    result = CheckResult()
    check_python(result)
    check_packages(result)
    check_ytdlp_freshness(result, installed_version("yt-dlp"))
    try:
        from . import config  # also loads .env, which may set FFMPEG_PATH
    except ImportError:
        config = None  # python-dotenv is missing; already reported above
    if config:
        check_spotify_config(result, config.SPOTIPY_CLIENT_ID, config.SPOTIPY_CLIENT_SECRET,
                             config.SPOTIPY_REDIRECT_URI)
    check_ffmpeg(result)
    check_youtube_support(result)
    return result


def format_report(result: CheckResult, verbose: bool = False) -> str:
    lines = []
    if verbose and result.found:
        lines.append("Detected:")
        lines += [f"  OK      {item}" for item in result.found]
        lines.append("")
    if result.errors or result.warnings:
        lines.append("Music Ripper startup check found problems:")
        lines += [f"  ERROR   {message}" for message in result.errors]
        lines += [f"  WARNING {message}" for message in result.warnings]
        lines.append("")
    if result.errors:
        lines.append("Fix the errors above and run again. For a full report run: python -m src.dependency_check")
    elif verbose:
        lines.append("All required dependencies look good.")
    return "\n".join(lines)


def ensure_dependencies(stream=None) -> CheckResult:
    """Runs the checks, prints any problems, and exits if Music Ripper can't work."""
    stream = stream or sys.stderr
    if os.getenv("MUSICRIPPER_SKIP_CHECKS", "").strip() not in ("", "0"):
        return CheckResult()
    result = run_checks()
    if result.errors or result.warnings:
        print(format_report(result), file=stream)
    if result.errors:
        sys.exit(1)
    return result


if __name__ == "__main__":
    report = run_checks()
    print(format_report(report, verbose=True))
    sys.exit(1 if report.errors else 0)
