"""Utility functions for the Music Ripper application."""

import logging
import os
import re

__all__ = ["sanitize_filename", "ensure_dir_exists"]

# Configure basic logging (can be expanded)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def sanitize_filename(input_filename: str) -> str:
    """
    Return a sanitized version of the provided filename suitable for use
    on most filesystems.

    This function removes or replaces characters that are typically invalid
    in filenames (for example: < > : " / \ | ? *). It also condenses
    multiple whitespace or underscore characters into a single underscore,
    and trims leading/trailing underscores.

    Parameters:
    - input_filename: The original filename string to sanitize.

    Returns:
    - A sanitized filename string.
    """
    # Remove invalid characters (e.g., < > : " / \ | ? *)
    sanitized_filename = re.sub(r'[<>:"/\\|?*]', "_", input_filename)
    # Replace multiple spaces/underscores with a single underscore
    sanitized_filename = re.sub(r"[\s_]+", "_", sanitized_filename)
    # Remove leading/trailing underscores or spaces
    sanitized_filename = sanitized_filename.strip("_")
    return sanitized_filename


def ensure_dir_exists(directory_path: str) -> bool:
    """
    Ensure that the directory at `directory_path` exists.

    If the directory does not exist, this function will attempt to create it.
    The function logs the creation action and any errors encountered.

    Parameters:
    - directory_path: Path to the directory to ensure exists.

    Returns:
    - True if the directory was created by this call.
    - False if the directory already existed.

    Raises:
    - OSError: Propagates any OS-related errors encountered while creating
      the directory.
    """
    if not os.path.exists(directory_path):
        try:
            os.makedirs(directory_path)
            logging.info("Created directory: %s", directory_path)
            return True
        except OSError as error:
            logging.error("Error creating directory %s: %s", directory_path, error)
            raise
    return False