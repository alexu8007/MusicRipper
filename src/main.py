# src/main.py
"""Main entry point for the Music Ripper CLI application."""

import argparse
import os
import logging
import sys
from typing import Any, Dict, List, Optional, Tuple

from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn, TimeRemainingColumn
from rich.panel import Panel
from rich.text import Text

# Adjust path to import from sibling directories
# This is a common pattern for structuring Python projects.
# It ensures that when main.py is run, it can find other modules in the src package.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.spotify_downloader import SpotifyDownloader
from src.config import DEFAULT_DOWNLOAD_DIR, SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET
from src.utils import ensure_dir_exists, sanitize_filename  # For logging configuration in utils

# Configure logging (ensure utils.py logging setup is respected or overridden here if needed)
# The basicConfig in utils.py would have already set up root logger.
# If more specific setup for main is needed, it can be done here.
logger = logging.getLogger(__name__)  # Get a logger specific to this module


def create_ui_elements() -> Console:
    """
    Create and return the Rich Console instance used for UI output.

    Returns:
        Console: A Rich Console instance for printing styled output.
    """
    console = Console()
    return console


def display_summary(console: Console, downloaded_songs: List[Dict[str, Any]], failed_songs: List[Dict[str, Any]], download_folder: str) -> None:
    """
    Print a formatted summary table of successful and failed track downloads to the given Rich console.
    
    Detailed behavior:
    - Renders a Rich Table listing each downloaded track with status "Success", track name, artist, source (if provided), and the saved file path.
    - Lists failed tracks with status "Failed", track name/artist (uses '-' when missing), and a generic failure detail.
    - Prints the absolute download folder path and, if any failures occurred, a yellow notice with the count.
    
    Expected data shapes:
    - downloaded_songs: iterable of dicts with required keys 'name', 'artist', 'path' and optional 'source'.
    - failed_songs: iterable of dict-like objects that may contain 'name' and 'artist'.
    """
    summary_table = Table(title=Text("Download Summary", style="bold magenta"), show_header=True, header_style="bold blue")
    summary_table.add_column("Status", style="dim", width=12)
    summary_table.add_column("Track Name")
    summary_table.add_column("Artist")
    summary_table.add_column("Source", width=10)
    summary_table.add_column("Details")

    for song in downloaded_songs:
        summary_table.add_row("[green]Success[/green]", song['name'], song['artist'], song.get('source', 'N/A'), f"Saved to {song['path']}")

    for song_info in failed_songs:
        summary_table.add_row("[red]Failed[/red]", song_info.get('name', '-'), song_info.get('artist', '-'), "-", "Could not download/process")

    console.print(summary_table)
    console.print(f"\nAll processing finished. Files are in: [cyan]{os.path.abspath(download_folder)}[/cyan]")
    if failed_songs:
        console.print(f"[yellow]{len(failed_songs)} song(s) could not be processed. Check logs for details.[/yellow]")


def parse_arguments(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """
    Parse CLI arguments for the application.

    Parameters:
        argv (Optional[List[str]]): Optional list of arguments (for testing). Defaults to None which uses sys.argv.

    Returns:
        argparse.Namespace: Parsed arguments with attributes 'playlist_url' and 'download_folder'.
    """
    parser = argparse.ArgumentParser(description=Text("Spotify Playlist Downloader", style="bold green"))
    parser.add_argument("playlist_url", help="The URL of the Spotify playlist to download.")
    parser.add_argument(
        "download_folder",
        nargs='?',
        default=DEFAULT_DOWNLOAD_DIR,
        help=f"The folder where songs will be downloaded. Defaults to '{DEFAULT_DOWNLOAD_DIR}' in the current directory."
    )
    return parser.parse_args(argv)


def initialize_downloader(downloader_cls=SpotifyDownloader):
    """
    Instantiate and return the provided downloader class.
    
    Attempts to create an instance of `downloader_cls` (defaults to `SpotifyDownloader`) and returns it.
    Initialization errors raised by the underlying downloader constructor (e.g., ValueError, ImportError, RuntimeError)
    are logged and re-raised.
    
    Parameters:
        downloader_cls: Callable/Type that constructs a downloader instance. Defaults to `SpotifyDownloader`.
    
    Returns:
        An instance of the provided downloader class.
    
    Raises:
        ValueError: If credentials or configuration are invalid during initialization.
        ImportError: If required modules for the downloader are missing.
        RuntimeError: For other initialization issues raised by the downloader.
    """
    try:
        downloader = downloader_cls()
        return downloader
    except ValueError as exc:
        logger.error("ValueError during downloader initialization: %s", exc, exc_info=True)
        raise
    except ImportError as exc:
        logger.error("ImportError during downloader initialization: %s", exc, exc_info=True)
        raise
    except RuntimeError as exc:
        logger.error("RuntimeError during downloader initialization: %s", exc, exc_info=True)
        raise


def process_tracks(downloader, tracks: List[Dict[str, Any]], download_folder: str, console: Console) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Download and process a list of track dictionaries, returning successful and failed results.
    
    Processes each item in `tracks` using the provided downloader; failures for individual tracks are caught and do not stop the overall run.
    
    Parameters:
        tracks (List[Dict[str, Any]]): Iterable of track info dicts. Each entry must include at least the 'name' and 'artist' keys.
        download_folder (str): Destination directory path where downloaded files will be written.
    
    Returns:
        Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]: A tuple (downloaded_songs, failed_songs).
            - downloaded_songs: list of dicts with keys: 'name', 'artist', 'path' (local file path), and 'source' (string identifying the download source).
            - failed_songs: list of the original track dicts that failed to download or returned no file.
    """
    downloaded_songs: List[Dict[str, Any]] = []
    failed_songs: List[Dict[str, Any]] = []

    # Rich progress bar setup
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=False  # Keep progress bar visible after completion for a moment or until next print
    ) as progress:
        task_download = progress.add_task("[green]Downloading songs...", total=len(tracks))

        for i, track_info in enumerate(tracks):
            progress.update(task_download, description=f"Processing: {track_info.get('artist', 'Unknown')} - {track_info.get('name', 'Unknown')}")

            # Attempt to download the song; guard against unexpected exceptions per-track so a single failure doesn't stop the whole run.
            try:
                file_path, source_name = downloader.download_song(track_info, download_folder)
            except (OSError, RuntimeError) as exc:
                logger.exception("Failed to download/process track '%s' by '%s' due to system/runtime error.", track_info.get('name'), track_info.get('artist'))
                failed_songs.append(track_info)
            except Exception as exc:
                # Log unexpected exceptions with trace to aid debugging but continue processing remaining tracks.
                logger.exception("Unexpected error while processing track '%s' by '%s': %s", track_info.get('name'), track_info.get('artist'), exc)
                failed_songs.append(track_info)
            else:
                if file_path:
                    downloaded_songs.append({
                        "name": track_info["name"],
                        "artist": track_info["artist"],
                        "path": file_path,
                        "source": source_name or "Unknown"  # Store the source
                    })
                    logger.info("Successfully processed: %s - %s from %s", track_info["artist"], track_info["name"], source_name)
                else:
                    failed_songs.append(track_info)
                    logger.warning("Failed to process (no file returned): %s - %s", track_info.get("artist"), track_info.get("name"))

            progress.advance(task_download)

        # Ensure progress bar finishes with a final description.
        progress.update(task_download, description="[bold green]All tracks processed![/bold green]")

    return downloaded_songs, failed_songs


def main() -> None:
    """
    Main CLI entry point that orchestrates parsing arguments, initializing the UI and downloader, fetching playlist tracks, downloading them, and showing a final summary.
    
    This function performs the end-to-end CLI workflow:
    - Parse command-line arguments.
    - Create Rich UI elements.
    - Validate required Spotify credentials and exit early if missing.
    - Initialize the Spotify downloader.
    - Fetch playlist tracks (handles network and fetch errors).
    - Ensure the download directory exists.
    - Download tracks via process_tracks and then render a summary table.
    
    The function does not return a value; it prints user-facing messages and logs errors as needed.
    """
    # Parse CLI arguments (kept isolated for testability)
    args = parse_arguments()

    # Create console/UI elements
    console = create_ui_elements()
    console.print(Panel(Text("Spotify Music Ripper Initializing...", justify="center", style="bold blue")))

    # Validate environment/config values required for Spotify access
    if not SPOTIPY_CLIENT_ID or not SPOTIPY_CLIENT_SECRET:
        console.print("[bold red]Error: Spotify API credentials (SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET) not found.[/bold red]")
        console.print("Please set them in a .env file in the project root as per the README.md.")
        return

    # Initialize the downloader with dependency-injection-friendly initializer
    try:
        downloader = initialize_downloader()
    except (ValueError, ImportError, RuntimeError) as e:
        console.print(f"[bold red]Error initializing Spotify Downloader: {e}[/bold red]")
        return

    # Fetch track list from the provided playlist URL
    console.print(f"Fetching track list from playlist: [link={args.playlist_url}]{args.playlist_url}[/link]")
    try:
        tracks = downloader.get_playlist_tracks(args.playlist_url)
    except (RuntimeError, ConnectionError) as exc:
        logger.exception("Failed to fetch playlist tracks for URL %s", args.playlist_url)
        console.print(f"[bold red]Failed to fetch tracks: {exc}[/bold red]")
        return
    except Exception as exc:
        # Unexpected exceptions should be logged and surfaced to the user in a friendly manner.
        logger.exception("Unexpected error fetching playlist tracks: %s", exc)
        console.print(f"[bold red]An unexpected error occurred while fetching tracks: {exc}[/bold red]")
        return

    if not tracks:
        console.print("[yellow]No tracks found in the playlist or could not fetch tracks. Exiting.[/yellow]")
        return

    console.print(f"Found {len(tracks)} tracks. Preparing to download to: [cyan]{os.path.abspath(args.download_folder)}[/cyan]")
    try:
        ensure_dir_exists(args.download_folder)
    except OSError as exc:
        logger.exception("Failed to ensure download directory exists: %s", args.download_folder)
        console.print(f"[bold red]Failed to prepare download directory: {exc}[/bold red]")
        return

    # Process tracks (download loop encapsulated for clarity and testability)
    downloaded_songs, failed_songs = process_tracks(downloader, tracks, args.download_folder, console)

    # Display final summary
    display_summary(console, downloaded_songs, failed_songs, args.download_folder)


def setup_logging(log_file_path: str = "music_ripper.log") -> None:
    """
    Configure root logging for the application and write logs to a file.
    
    Removes any existing root handlers (to avoid duplicate entries when the module is reloaded) and configures logging.basicConfig with level INFO, a timestamped format, and a FileHandler that appends to the given log file.
    
    Parameters:
        log_file_path (str): Path to the log file where messages will be appended (default: "music_ripper.log").
    """
    # Remove old handlers to avoid duplicate logs if script is re-run in same session (e.g. in an IDE)
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file_path, mode='a'),  # Append mode
            # logging.StreamHandler() # Already handled by Rich for console, but could be added if needed
        ]
    )


if __name__ == "__main__":
    # Set up global logging to a file, in addition to console output handled by Rich.
    setup_logging()
    logger.info("Application started.")
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Application interrupted by user (KeyboardInterrupt).")
        console = Console()
        console.print("[bold yellow]Interrupted by user. Exiting.[/bold yellow]")
    except Exception as e:
        # Catch any unhandled exceptions from main, log them with traceback and display friendly message.
        logger.critical("Unhandled exception in main: %s", e, exc_info=True)
        console = Console()
        console.print(f"[bold red]A critical error occurred: {e}[/bold red]")
        console.print("Please check the log file (music_ripper.log) for more details.")
    logger.info("Application finished.")