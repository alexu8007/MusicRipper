"""Utility functions for the Music Ripper application."""

import logging
import os
import re

# Configure basic logging (can be expanded)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def sanitize_filename(filename: str) -> str:
    """
    Remove or replace characters that are invalid in filenames and normalize whitespace.

    Rules applied:
    - Replace characters forbidden on most filesystems (e.g., < > : " / \ | ? *) with underscores.
    - Collapse runs of whitespace and underscores into a single underscore.
    - Strip leading and trailing underscores.

    This function is pure: it does not perform any I/O or logging.

    Note:
        This function is intended for single filename components (not full paths).
        If you have a full path, extract the basename (e.g., with os.path.basename)
        and pass that basename to this function. Alternatively, use sanitize_basename
        which will safely handle extracting the basename for you.

    Args:
        filename: The original filename string to sanitize.

    Returns:
        A sanitized filename string safe for use on most filesystems.

    Raises:
        TypeError: If filename is not a string.
        ValueError: If filename is an empty string or contains only whitespace after trimming.
    """
    if not isinstance(filename, str):
        raise TypeError(f"filename must be a str, got {type(filename).__name__}")

    # Trim whitespace to detect empty/blank names early.
    trimmed = filename.strip()
    if not trimmed:
        raise ValueError("filename must be a non-empty string")

    # Replace invalid filesystem characters with an underscore.
    sanitized_name = re.sub(r'[<>:"/\\|?*]', '_', trimmed)

    # Collapse multiple whitespace or underscores into a single underscore to normalize.
    sanitized_name = re.sub(r'[\s_]+', '_', sanitized_name)

    # Remove leading/trailing underscores introduced by replacements.
    sanitized_name = sanitized_name.strip('_')

    # If the result is empty (e.g., input was all invalid chars), raise an error.
    if not sanitized_name:
        raise ValueError("filename contains no valid characters after sanitization")

    return sanitized_name


def sanitize_basename(name: str) -> str:
    """
    Extract the basename from a path-like input and return a sanitized filename.

    This helper extracts os.path.basename(name) and then calls sanitize_filename on
    the resulting basename. If sanitize_filename raises TypeError or ValueError for
    the basename, this function will catch the exception, log a warning, and return
    the original basename converted to str.

    Args:
        name: A path or filename from which to extract the basename.

    Returns:
        A sanitized filename string suitable for use on most filesystems, or the
        original basename as a str if sanitization fails.
    """
    basename = os.path.basename(name)
    try:
        return sanitize_filename(basename)
    except (TypeError, ValueError) as exc:
        logging.warning("Could not sanitize basename %r: %s. Returning original basename.", basename, exc)
        return str(basename)


def ensure_dir_exists(dir_path: str) -> None:
    """
    Ensure that a directory exists at the given path, creating it if necessary.

    This function performs I/O (filesystem) and logs creation events. It will raise
    explicit exceptions for invalid inputs or failed creation attempts.

    Args:
        dir_path: Path to the directory that must exist.

    Raises:
        TypeError: If dir_path is not a string.
        ValueError: If dir_path is an empty string.
        NotADirectoryError: If a non-directory file exists at dir_path.
        OSError: If the directory cannot be created due to an OS error.
    """
    if not isinstance(dir_path, str):
        raise TypeError(f"dir_path must be a str, got {type(dir_path).__name__}")

    dir_path_trimmed = dir_path.strip()
    if not dir_path_trimmed:
        raise ValueError("dir_path must be a non-empty string")

    # If the path exists but is not a directory, raise a specific error.
    if os.path.exists(dir_path_trimmed) and not os.path.isdir(dir_path_trimmed):
        raise NotADirectoryError(f"Path exists and is not a directory: {dir_path_trimmed}")

    # If the directory does not exist, attempt to create it (including parents).
    if not os.path.exists(dir_path_trimmed):
        try:
            os.makedirs(dir_path_trimmed)
            logging.info(f"Created directory: {dir_path_trimmed}")
        except OSError as exc:
            # Log the error and re-raise to allow callers to handle it explicitly.
            logging.error(f"Error creating directory {dir_path_trimmed}: {exc}")
            raise