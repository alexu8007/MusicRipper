"""Main entry point for the Music Ripper CLI application.

Provides a simple CLI to download tracks from a Spotify playlist. This module
exposes a main() entry point intended to be used as a script entry and can be
imported for testing. Side effects (like configuring logging and running the
CLI) are guarded under if __name__ == '__main__' so importing this module
does not execute the application automatically.
"""

import argparse
import os
import logging
import sys
from typing import Any, Dict, List, Optional

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
from src.utils import ensure_dir_exists, sanitize_filename, sanitize_basename # For logging configuration in utils

logger = logging.getLogger(__name__)


def create_ui_elements() -> Console:
    """Create and return the Rich Console used by the application.

    Returns:
        Console: A configured Rich Console instance.
    """
    console = Console()
    return console


def display_summary(console: Console, downloaded_songs: List[Dict[str, Any]], failed_songs: List[Dict[str, Any]], download_folder: str) -> None:
    """Display a summary table of successful and failed downloads.

    Args:
        console: Rich Console instance to print to.
        downloaded_songs: List of dicts describing successfully downloaded songs.
        failed_songs: List of dicts describing songs that failed.
        download_folder: Path to the folder where files were saved.
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
        summary_table.add_row("[red]Failed[/red]", song_info.get('name', 'Unknown'), song_info.get('artist', 'Unknown'), "-", "Could not download/process")

    console.print(summary_table)
    console.print(f"\nAll processing finished. Files are in: [cyan]{os.path.abspath(download_folder)}[/cyan]")
    if failed_songs:
        console.print(f"[yellow]{len(failed_songs)} song(s) could not be processed. Check logs for details.[/yellow]")


def parse_arguments(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse and validate CLI arguments.

    Args:
        argv: Optional list of arguments (for testing). If None, uses sys.argv.

    Returns:
        argparse.Namespace: The parsed arguments namespace.
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


def setup_logging(log_file_path: str = "music_ripper.log") -> logging.Logger:
    """Configure application logging to file and return the module logger.

    Existing root handlers are removed to avoid duplicated log entries when
    the module is re-run in the same process.

    Args:
        log_file_path: Path to the log file to append logs to.

    Returns:
        logging.Logger: A module-level logger instance.
    """
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file_path, mode='a'),
        ]
    )
    return logging.getLogger(__name__)


def main() -> None:
    """Main function to parse arguments and start the download process.

    This function performs minimal orchestration and delegates complex logic to
    helper functions to improve testability.
    """
    args = parse_arguments()
    console = create_ui_elements()

    console.print(Panel(Text("Spotify Music Ripper Initializing...", justify="center", style="bold blue")))

    if not SPOTIPY_CLIENT_ID or not SPOTIPY_CLIENT_SECRET:
        console.print("[bold red]Error: Spotify API credentials (SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET) not found.[/bold red]")
        console.print("Please set them in a .env file in the project root as per the README.md.")
        logger.error("Missing Spotify API credentials: SPOTIPY_CLIENT_ID or SPOTIPY_CLIENT_SECRET not set.")
        return

    try:
        downloader = SpotifyDownloader()
    except ValueError as e:
        console.print(f"[bold red]Error initializing Spotify Downloader: {e}[/bold red]")
        logger.error(f"SpotifyDownloader initialization ValueError: {e}")
        return
    except Exception as e:
        console.print(f"[bold red]An unexpected error occurred during initialization: {e}[/bold red]")
        logger.exception("Initialization failed with unexpected exception.")
        return

    console.print(f"Fetching track list from playlist: [link={args.playlist_url}]{args.playlist_url}[/link]")
    try:
        tracks = downloader.get_playlist_tracks(args.playlist_url)
    except Exception as e:
        console.print(f"[bold red]Failed to fetch tracks from playlist: {e}[/bold red]")
        logger.exception("Failed to fetch playlist tracks.")
        return

    if not tracks:
        console.print("[yellow]No tracks found in the playlist or could not fetch tracks. Exiting.[/yellow]")
        logger.info("No tracks returned from playlist fetch; exiting.")
        return

    console.print(f"Found {len(tracks)} tracks. Preparing to download to: [cyan]{os.path.abspath(args.download_folder)}[/cyan]")
    try:
        ensure_dir_exists(args.download_folder)
    except Exception as e:
        console.print(f"[bold red]Failed to create or access download folder '{args.download_folder}': {e}[/bold red]")
        logger.exception("ensure_dir_exists failed.")
        return

    downloaded_songs: List[Dict[str, Any]] = []
    failed_songs: List[Dict[str, Any]] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=False
    ) as progress:
        task_download = progress.add_task("[green]Downloading songs...", total=len(tracks))

        for i, track_info in enumerate(tracks):
            progress.update(task_download, description=f"Processing: {track_info.get('artist', 'Unknown')} - {track_info.get('name', 'Unknown')}")
            try:
                file_path, source_name = downloader.download_song(track_info, args.download_folder)
            except Exception as e:
                logger.exception("Error downloading song: %s - %s", track_info.get("artist"), track_info.get("name"))
                failed_songs.append(track_info)
                progress.advance(task_download)
                continue

            if file_path:
                downloaded_songs.append({
                    "name": track_info.get("name", "Unknown"), 
                    "artist": track_info.get("artist", "Unknown"), 
                    "path": file_path,
                    "source": source_name or "Unknown"
                })
                logger.info("Successfully processed: %s - %s from %s", track_info.get("artist"), track_info.get("name"), source_name)
            else:
                failed_songs.append(track_info)
                logger.warning("Failed to process: %s - %s", track_info.get("artist"), track_info.get("name"))
            
            progress.advance(task_download)
        
        progress.update(task_download, description="[bold green]All tracks processed![/bold green]")

    display_summary(console, downloaded_songs, failed_songs, args.download_folder)


if __name__ == "__main__":
    log_file_path = "music_ripper.log"
    try:
        safe_basename = sanitize_basename(os.path.basename(log_file_path))
    except Exception as e:
        logging.warning("sanitize_basename failed for %s: %s. Falling back to basename.", log_file_path, e)
        safe_basename = os.path.basename(log_file_path)
    log_file_path = safe_basename
    logger = setup_logging(log_file_path)
    logger.info("Application started.")
    try:
        main()
    except Exception as e:
        logger.critical("Unhandled exception in main: %s", e, exc_info=True)
        console = Console()
        console.print(f"[bold red]An critical error occurred: {e}[/bold red]")
        console.print("Please check the log file (music_ripper.log) for more details.")
    logger.info("Application finished.")