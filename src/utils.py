"""Utility functions for the Music Ripper application."""

import logging
import os
import re

# Configure basic logging (can be expanded)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def sanitize_filename(filename: str) -> str:
    """Return a filesystem-safe version of `filename`.

    This function removes or replaces characters that are invalid or problematic
    in filenames across common platforms (for example: < > : " / \ | ? *),
    collapses runs of whitespace and underscores into a single underscore, and
    trims leading/trailing underscores.

    Args:
        filename: The raw filename string to sanitize.

    Returns:
        A sanitized filename safe for use on most filesystems.
    """
    # Remove invalid characters (e.g., < > : " / \ | ? *)
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', filename)
    # Replace multiple spaces/underscores with a single underscore
    sanitized = re.sub(r'[\s_]+', '_', sanitized)
    # Remove leading/trailing underscores or spaces
    sanitized = sanitized.strip('_')
    return sanitized


def _directory_needs_creation(dir_path: str) -> bool:
    """Return True if the directory at `dir_path` does not exist.

    This helper isolates the existence check so it can be tested without
    performing creation side effects.

    Args:
        dir_path: Path to the directory to check.

    Returns:
        True if the directory does not exist and therefore needs creation,
        otherwise False.
    """
    return not os.path.exists(dir_path)


def _create_directory(dir_path: str) -> None:
    """Create the directory at `dir_path`, logging actions and errors.

    This internal helper performs the filesystem side-effect of creating the
    directory. It raises the underlying OSError on failure so callers can
    handle it or propagate it.

    Args:
        dir_path: Path to the directory to create.

    Raises:
        OSError: If directory creation fails.
    """
    try:
        os.makedirs(dir_path)
        logging.info(f"Created directory: {dir_path}")
    except OSError as e:
        logging.error(f"Error creating directory {dir_path}: {e}")
        raise


def is_directory_present(dir_path: str) -> bool:
    """Return True if `dir_path` exists and is a directory.

    This small wrapper is provided as a test hook to verify directory presence
    without performing any creation side effects.

    Args:
        dir_path: Path to check.

    Returns:
        True if the path exists and is a directory, otherwise False.
    """
    return os.path.isdir(dir_path)


def ensure_dir_exists(dir_path: str) -> None:
    """Ensure that a directory exists, creating it if necessary.

    This function delegates the existence check and the actual creation to
    small, well-documented helpers to improve testability and clarity. It will
    create the directory if it does not exist, and propagate any OSError
    raised during creation.

    Args:
        dir_path: Path to the directory to ensure exists.

    Raises:
        OSError: If directory creation fails.
    """
    if _directory_needs_creation(dir_path):
        _create_directory(dir_path)


# More utility functions will be added here, e.g.:
# - validate_mp3_320kbps (using pydub)
# - get_file_size
# - etc.