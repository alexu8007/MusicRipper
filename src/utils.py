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

# More utility functions will be added here, e.g.:
# - validate_mp3_320kbps (using pydub)
# - get_file_size
# - etc. 