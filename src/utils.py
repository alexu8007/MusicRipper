"""Utility functions for the Music Ripper application."""

import os
import re
import logging

# Configure basic logging (can be expanded)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def sanitize_filename(filename: str) -> str:
    """Removes or replaces characters that are invalid in filenames."""
    # Remove invalid characters (e.g., < > : " / \ | ? *)
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', filename)
    # Replace multiple spaces/underscores with a single underscore
    sanitized = re.sub(r'[\s_]+', '_', sanitized)
    # Remove leading/trailing underscores or spaces
    sanitized = sanitized.strip('_')
    return sanitized

def ensure_dir_exists(dir_path: str):
    """Ensures that a directory exists, creates it if not."""
    if not os.path.exists(dir_path):
        try:
            os.makedirs(dir_path)
            logging.info(f"Created directory: {dir_path}")
        except OSError as e:
            logging.error(f"Error creating directory {dir_path}: {e}")
            raise

def format_duration(milliseconds: float) -> str:
    """12345 -> '0:12'."""
    seconds = round(milliseconds / 1000)
    return f"{seconds // 60}:{seconds % 60:02d}"


_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")

# (text in a yt-dlp error, what to do about it in this app)
YTDLP_ERROR_HINTS = (
    ("Sign in to confirm", "YouTube is asking for a signed-in session (bot check). Set "
     "YTDLP_COOKIES_FROM_BROWSER=firefox (or chrome, edge, ...) in .env so yt-dlp can use your "
     "browser's YouTube cookies."),
    ("No suitable extractor", 'yt-dlp doesn\'t understand the site\'s current format. Update it: '
     'pip install -U "yt-dlp[default]"'),
    ("Requested format is not available", 'No downloadable audio stream was offered. Update yt-dlp '
     '(pip install -U "yt-dlp[default]") and install Deno so YouTube formats can be unlocked.'),
    ("HTTP Error 403", 'The site refused the download. Updating yt-dlp usually fixes this: '
     'pip install -U "yt-dlp[default]"'),
    ("HTTP Error 429", "The site is rate-limiting you. Wait a while, or set YTDLP_COOKIES_FROM_BROWSER in .env."),
    ("ffmpeg not found", "See README, 'Install FFmpeg and FFprobe', or set FFMPEG_PATH in .env."),
)


def describe_ytdlp_error(error) -> str:
    """Turns a yt-dlp exception into a one-line reason plus a hint on how to fix it."""
    message = _ANSI_ESCAPE.sub("", str(error)).strip()
    message = message.splitlines()[0] if message else type(error).__name__
    message = re.sub(r"^ERROR:\s*", "", message)
    # Drop yt-dlp's command-line advice (--cookies ..., see <url>); it doesn't apply to this app.
    message = re.split(r"\s+(?:Use --|See\s+https?://|Please report this issue)", message,
                       maxsplit=1, flags=re.IGNORECASE)[0].rstrip(" .;")
    for needle, hint in YTDLP_ERROR_HINTS:
        if needle.lower() in message.lower():
            return f"{message}. {hint}"
    return message
