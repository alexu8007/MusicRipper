"""Utility functions for the Music Ripper application.

This module provides common utility functions used throughout the application,
including file system operations, string sanitization, and path management.
"""

import os
import re
import logging

# Configure basic logging (can be expanded)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def sanitize_filename(filename: str) -> str:
    """Sanitize a filename by removing or replacing invalid characters.
    
    This function ensures that the filename is safe to use across different
    operating systems by removing characters that are not allowed in filenames.
    
    Args:
        filename (str): The original filename to sanitize
        
    Returns:
        str: A sanitized filename safe for use on most file systems
        
    Example:
        >>> sanitize_filename("Song: Artist - Album/Version")
        "Song_Artist_Album_Version"
    """
    # Remove invalid characters (< > : " / \ | ? *)
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', filename)
    # Replace multiple spaces/underscores with a single underscore
    sanitized = re.sub(r'[\s_]+', '_', sanitized)
    # Remove leading/trailing underscores or spaces
    sanitized = sanitized.strip('_')
    # Ensure filename is not empty after sanitization
    if not sanitized:
        sanitized = "untitled"
    return sanitized


def ensure_dir_exists(dir_path: str) -> None:
    """Ensure that a directory exists, creating it if necessary.
    
    This function creates the directory and any necessary parent directories
    if they don't already exist. It handles permissions and provides
    appropriate error handling.
    
    Args:
        dir_path (str): Path to the directory to create
        
    Raises:
        OSError: If the directory cannot be created due to permissions or other issues
        
    Example:
        >>> ensure_dir_exists("./Downloads/MyPlaylist")
        # Creates the directory structure if it doesn't exist
    """
    if not os.path.exists(dir_path):
        try:
            os.makedirs(dir_path, exist_ok=True)
            logging.info(f"Created directory: {dir_path}")
        except OSError as e:
            logging.error(f"Error creating directory {dir_path}: {e}")
            raise


def format_file_size(size_bytes: int) -> str:
    """Format a file size in bytes to a human-readable string.
    
    Args:
        size_bytes (int): File size in bytes
        
    Returns:
        str: Formatted file size (e.g., "1.2 MB", "345 KB")
    """
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    
    return f"{size_bytes:.1f} {size_names[i]}"


def get_safe_path(base_path: str, filename: str) -> str:
    """Create a safe file path by joining base path with a sanitized filename.
    
    Args:
        base_path (str): The directory path where the file will be placed
        filename (str): The filename to sanitize and join
        
    Returns:
        str: A safe, absolute file path
    """
    safe_filename = sanitize_filename(filename)
    return os.path.join(os.path.abspath(base_path), safe_filename) 