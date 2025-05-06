# src/main.py
"""Main entry point for the Music Ripper CLI application."""

import argparse
import os
import logging
import sys

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
from src.utils import ensure_dir_exists, sanitize_filename # For logging configuration in utils

# Configure logging (ensure utils.py logging setup is respected or overridden here if needed)
# The basicConfig in utils.py would have already set up root logger.
# If more specific setup for main is needed, it can be done here.
logger = logging.getLogger(__name__) # Get a logger specific to this module
# Example: if you want to set a different level for this module's logger:
# logger.setLevel(logging.DEBUG) 


def create_ui_elements():
    """Creates Rich UI elements (console, tables, progress bars)."""
    console = Console()
    return console

def display_summary(console: Console, downloaded_songs: list, failed_songs: list, download_folder: str):
    """Displays a summary of the download process."""
    summary_table = Table(title=Text("Download Summary", style="bold magenta"), show_header=True, header_style="bold blue")
    summary_table.add_column("Status", style="dim", width=12)
    summary_table.add_column("Track Name")
    summary_table.add_column("Artist")
    summary_table.add_column("Source", width=10)
    summary_table.add_column("Details")

    for song in downloaded_songs:
        summary_table.add_row("[green]Success[/green]", song['name'], song['artist'], song.get('source', 'N/A'), f"Saved to {song['path']}")
    
    for song_info in failed_songs:
        summary_table.add_row("[red]Failed[/red]", song_info['name'], song_info['artist'], "-", "Could not download/process")

    console.print(summary_table)
    console.print(f"\nAll processing finished. Files are in: [cyan]{os.path.abspath(download_folder)}[/cyan]")
    if failed_songs:
        console.print(f"[yellow]{len(failed_songs)} song(s) could not be processed. Check logs for details.[/yellow]")


def main():
    """Main function to parse arguments and start the download process."""
    parser = argparse.ArgumentParser(description=Text("Spotify Playlist Downloader", style="bold green"))
    parser.add_argument("playlist_url", help="The URL of the Spotify playlist to download.")
    parser.add_argument(
        "download_folder", 
        nargs='?', 
        default=DEFAULT_DOWNLOAD_DIR, 
        help=f"The folder where songs will be downloaded. Defaults to '{DEFAULT_DOWNLOAD_DIR}' in the current directory."
    )

    args = parser.parse_args()
    console = create_ui_elements()

    console.print(Panel(Text("Spotify Music Ripper Initializing...", justify="center", style="bold blue")))

    if not SPOTIPY_CLIENT_ID or not SPOTIPY_CLIENT_SECRET:
        console.print("[bold red]Error: Spotify API credentials (SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET) not found.[/bold red]")
        console.print("Please set them in a .env file in the project root as per the README.md.")
        return

    try:
        downloader = SpotifyDownloader()
    except ValueError as e:
        console.print(f"[bold red]Error initializing Spotify Downloader: {e}[/bold red]")
        return
    except Exception as e:
        console.print(f"[bold red]An unexpected error occurred during initialization: {e}[/bold red]")
        logger.error(f"Initialization failed: {e}", exc_info=True)
        return

    console.print(f"Fetching track list from playlist: [link={args.playlist_url}]{args.playlist_url}[/link]")
    tracks = downloader.get_playlist_tracks(args.playlist_url)

    if not tracks:
        console.print("[yellow]No tracks found in the playlist or could not fetch tracks. Exiting.[/yellow]")
        return

    console.print(f"Found {len(tracks)} tracks. Preparing to download to: [cyan]{os.path.abspath(args.download_folder)}[/cyan]")
    ensure_dir_exists(args.download_folder)

    downloaded_songs = []
    failed_songs = []

    # Rich progress bar setup
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=False # Keep progress bar visible after completion for a moment or until next print
    ) as progress:
        task_download = progress.add_task("[green]Downloading songs...", total=len(tracks))

        for i, track_info in enumerate(tracks):
            progress.update(task_download, description=f"Processing: {track_info['artist']} - {track_info['name']}")
            
            # Attempt to download the song
            file_path, source_name = downloader.download_song(track_info, args.download_folder)
            
            if file_path:
                downloaded_songs.append({
                    "name": track_info["name"], 
                    "artist": track_info["artist"], 
                    "path": file_path,
                    "source": source_name or "Unknown" # Store the source
                })
                logger.info(f"Successfully processed: {track_info['artist']} - {track_info['name']} from {source_name}")
            else:
                failed_songs.append(track_info)
                logger.warning(f"Failed to process: {track_info['artist']} - {track_info['name']}")
            
            progress.advance(task_download)
        
        # Ensure progress bar finishes if transient=False is not fully effective or if you want a final message within it.
        progress.update(task_download, description="[bold green]All tracks processed![/bold green]")

    display_summary(console, downloaded_songs, failed_songs, args.download_folder)

if __name__ == "__main__":
    # Set up global logging to a file, in addition to console output handled by Rich.
    # This should be done once, preferably at the very start.
    log_file_path = "music_ripper.log"
    # Remove old handlers to avoid duplicate logs if script is re-run in same session (e.g. in an IDE)
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    
    logging.basicConfig(
        level=logging.INFO, 
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file_path, mode='a'), # Append mode
            # logging.StreamHandler() # Already handled by Rich for console, but could be added if needed
        ]
    )
    logger.info("Application started.")
    try:
        main()
    except Exception as e:
        # Catch any unhandled exceptions from main and log them
        logger.critical(f"Unhandled exception in main: {e}", exc_info=True)
        console = Console()
        console.print(f"[bold red]An critical error occurred: {e}[/bold red]")
        console.print("Please check the log file (music_ripper.log) for more details.")
    logger.info("Application finished.") 