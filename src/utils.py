"""Utility functions for the Music Ripper application."""

import logging
import os
import re

# Configure basic logging (can be expanded)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def sanitize_filename(filename: str) -> str:
    """Sanitize a string to be safe for use as a filesystem filename.

    This removes characters that are typically invalid in filenames on
    common platforms and collapses runs of whitespace and underscores
    into a single underscore. Leading and trailing underscores are
    trimmed.

    Parameters
    ----------
    filename : str
        The candidate filename to sanitize.

    Returns
    -------
    str
        A sanitized filename safe for most filesystems.

    Raises
    ------
    TypeError
        If `filename` is not a string.
    ValueError
        If `filename` is an empty string after stripping whitespace.
    """
    if not isinstance(filename, str):
        raise TypeError("filename must be a str")
    # Remove invalid characters (e.g., < > : " / \ | ? *)
    sanitized = re.sub(r'[<>:"/\\|?*]', "_", filename)
    # Replace multiple spaces/underscores with a single underscore
    sanitized = re.sub(r"[\s_]+", "_", sanitized)
    # Remove leading/trailing underscores
    sanitized = sanitized.strip("_")
    if sanitized == "":
        raise ValueError("filename cannot be empty or contain only invalid characters")
    return sanitized


def ensure_dir_exists(dir_path: str) -> None:
    """Ensure a directory exists, creating it if necessary.

    This function is idempotent: if the directory already exists it will
    do nothing. It validates input to make unit testing and error cases
    explicit.

    Parameters
    ----------
    dir_path : str
        Path to the directory that should exist.

    Raises
    ------
    TypeError
        If `dir_path` is not a string.
    ValueError
        If `dir_path` is an empty string.
    OSError
        If directory creation fails due to an OS-related error.
    """
    if not isinstance(dir_path, str):
        raise TypeError("dir_path must be a str")
    if dir_path == "":
        raise ValueError("dir_path must be a non-empty string")

    if not os.path.exists(dir_path):
        try:
            os.makedirs(dir_path)
            logging.info(f"Created directory: {dir_path}")
        except OSError as e:
            logging.error(f"Error creating directory {dir_path}: {e}")
            raise