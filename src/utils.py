"""Utility functions for the Music Ripper application."""

import logging
import os
import re

# Configure basic logging (can be expanded)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def sanitize_filename(filename: str) -> str:
    """
    Return a sanitized version of the given filename suitable for use on most filesystems.

    The function replaces characters that are invalid in filenames (for example: < > : " / \ | ? *) with
    underscores, collapses runs of whitespace and underscores into a single underscore, and strips
    leading/trailing underscores.

    Args:
        filename: The original filename string to sanitize.

    Returns:
        A sanitized filename string.

    Raises:
        TypeError: If the provided filename is not a string.
        ValueError: If the provided filename is an empty string or only whitespace.
    """
    if not isinstance(filename, str):
        raise TypeError("filename must be a string")
    if filename.strip() == "":
        raise ValueError("filename must not be empty or only whitespace")

    # Remove invalid characters (e.g., < > : " / \ | ? *)
    sanitized_filename = re.sub(r'[<>:"/\\|?*]', "_", filename)
    # Replace multiple spaces/underscores with a single underscore
    sanitized_filename = re.sub(r"[\s_]+", "_", sanitized_filename)
    # Remove leading/trailing underscores or spaces
    sanitized_filename = sanitized_filename.strip("_")

    return sanitized_filename


def ensure_dir_exists(directory_path: str) -> bool:
    """
    Ensure that the specified directory exists on the filesystem.

    If the directory does not exist it will be created. Function logs actions and raises OSError on
    failure to create the directory.

    Args:
        directory_path: Path to the directory to ensure exists.

    Returns:
        True if the directory was created by this call, False if the directory already existed.

    Raises:
        TypeError: If directory_path is not a string.
        ValueError: If directory_path is empty or only whitespace.
        OSError: If the directory cannot be created due to an OS-level error.
    """
    if not isinstance(directory_path, str):
        raise TypeError("directory_path must be a string")
    if directory_path.strip() == "":
        raise ValueError("directory_path must not be empty or only whitespace")

    normalized_path = os.path.normpath(directory_path)

    if os.path.isdir(normalized_path):
        logging.info("Directory already exists: %s", normalized_path)
        return False

    try:
        os.makedirs(normalized_path, exist_ok=True)
        logging.info("Created directory: %s", normalized_path)
        return True
    except OSError as exc:
        logging.error("Error creating directory %s: %s", normalized_path, exc)
        raise