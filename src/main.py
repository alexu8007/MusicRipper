# src/main.py
"""Main entry point for the Music Ripper CLI application."""

import argparse
import os
import logging
import sys
from typing import Any, Callable, Dict, List, Optional, Tuple, NamedTuple

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
# Example: if you want to set a different level for this module's logger:
# logger.setLevel(logging.DEBUG)


class AppConfig(NamedTuple):
    """Immutable application configuration values used by main.

    Attributes:
        default_download_dir: Default directory where downloads are saved.
        client_id: Spotify client ID (may be None or empty).
        client_secret: Spotify client secret (may be None or empty).
    """
    default_download_dir: str
    client_id: Optional[str]
    client_secret: Optional[str]


def get_config() -> AppConfig:
    """Read and return configuration values in a validated, read-only structure.

    Returns:
        AppConfig: Named tuple containing default_download_dir, client_id, client_secret.
    """
    return AppConfig(
        default_download_dir=DEFAULT_DOWNLOAD_DIR,
        client_id=SPOTIPY_CLIENT_ID,
        client_secret=SPOTIPY_CLIENT_SECRET,
    )


def create_ui_elements() -> Console:
    """Create and return a Rich Console instance for UI output.

    Returns:
        Console: A Rich Console object used for printing UI elements.
    """
    console = Console()
    return console


def display_summary(console: Console, downloaded_songs: List[Dict[str, Any]], failed_songs: List[Dict[str, Any]], download_folder: str) -> None:
    """Display a summary table of downloaded and failed songs.

    Args:
        console: Rich Console to print to.
        downloaded_songs: List of dictionaries representing successfully downloaded songs.
        failed_songs: List of dictionaries representing songs that failed to process.
        download_folder: Path to the download folder to show in summary.
    """
    summary_table = Table(title=Text("Download Summary", style="bold magenta"), show_header=True, header_style="bold blue")
    summary_table.add_column("Status", style="dim", width=12)
    summary_table.add_column("Track Name")
    summary_table.add_column("Artist")
    summary_table.add_column("Source", width=10)
    summary_table.add_column("Details")

    for song in downloaded_songs:
        summary_table.add_row("[green]Success[/green]", song["name"], song["artist"], song.get("source", "N/A"), f"Saved to {song['path']}")

    for song_info in failed_songs:
        summary_table.add_row("[red]Failed[/red]", song_info.get("name", "Unknown"), song_info.get("artist", "Unknown"), "-", "Could not download/process")

    console.print(summary_table)
    console.print(f"\nAll processing finished. Files are in: [cyan]{os.path.abspath(download_folder)}[/cyan]")
    if failed_songs:
        console.print(f"[yellow]{len(failed_songs)} song(s) could not be processed. Check logs for details.[/yellow]")


def parse_arguments(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Optional list of argument strings to parse (for testing). If None, argparse will use sys.argv.

    Returns:
        argparse.Namespace: Parsed arguments.
    """
    parser = argparse.ArgumentParser(description=Text("Spotify Playlist Downloader", style="bold green"))
    parser.add_argument("playlist_url", help="The URL of the Spotify playlist to download.")
    parser.add_argument(
        "download_folder",
        nargs="?",
        default=DEFAULT_DOWNLOAD_DIR,
        help=f"The folder where songs will be downloaded. Defaults to '{DEFAULT_DOWNLOAD_DIR}' in the current directory.",
    )
    return parser.parse_args(argv)


def validate_credentials(config: AppConfig) -> None:
    """Validate that required Spotify credentials are present.

    Args:
        config: Application configuration.

    Raises:
        ValueError: If either client ID or client secret is missing.
    """
    if not config.client_id or not config.client_secret:
        raise ValueError("Spotify API credentials (SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET) not found.")


def init_downloader(downloader_factory: Callable[[], SpotifyDownloader]) -> SpotifyDownloader:
    """Initialize and return a SpotifyDownloader instance.

    Args:
        downloader_factory: Callable that returns a SpotifyDownloader when called.

    Returns:
        SpotifyDownloader: Initialized downloader.

    Raises:
        ValueError: Propagates ValueError raised by downloader initialization.
        Exception: Any unexpected exception during initialization is propagated after logging.
    """
    try:
        return downloader_factory()
    except ValueError:
        # Known initialization error (e.g. missing credentials), propagate unchanged for caller to handle.
        raise
    except Exception as exc:
        logger.error("Unexpected error initializing downloader", exc_info=True)
        raise


def process_tracks(
    downloader: SpotifyDownloader,
    tracks: List[Dict[str, Any]],
    download_folder: str,
    console: Console,
    ensure_dir_fn: Callable[[str], None] = ensure_dir_exists,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Download tracks using the provided downloader, returning lists of successes and failures.

    This function isolates the download loop so it can be tested independently.

    Args:
        downloader: SpotifyDownloader instance used to fetch/download songs.
        tracks: List of track metadata dictionaries to process.
        download_folder: Destination folder for downloads.
        console: Rich Console for progress output.
        ensure_dir_fn: Callable to ensure the download directory exists (injected for testability).

    Returns:
        Tuple containing (downloaded_songs, failed_songs).
    """
    ensure_dir_fn(download_folder)

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
        transient=False,
    ) as progress:
        task_download = progress.add_task("[green]Downloading songs...", total=len(tracks))

        for i, track_info in enumerate(tracks):
            try:
                progress.update(task_download, description=f"Processing: {track_info.get('artist', 'Unknown')} - {track_info.get('name', 'Unknown')}")
                file_path, source_name = downloader.download_song(track_info, download_folder)

                if file_path:
                    downloaded_songs.append(
                        {
                            "name": track_info.get("name", "Unknown"),
                            "artist": track_info.get("artist", "Unknown"),
                            "path": file_path,
                            "source": source_name or "Unknown",
                        }
                    )
                    logger.info(f"Successfully processed: {track_info.get('artist')} - {track_info.get('name')} from {source_name}")
                else:
                    failed_songs.append(track_info)
                    logger.warning(f"Failed to process: {track_info.get('artist')} - {track_info.get('name')}")
            except OSError as e:
                # Likely a filesystem-related error; log and mark as failed.
                logger.error(f"Filesystem error while processing {track_info.get('name')}: {e}", exc_info=True)
                failed_songs.append(track_info)
            except Exception as e:
                # Catch any other per-track errors, log them, and continue.
                logger.exception(f"Unexpected error while processing track {track_info.get('name')}: {e}")
                failed_songs.append(track_info)
            finally:
                progress.advance(task_download)

        # Final update for user clarity
        progress.update(task_download, description="[bold green]All tracks processed![/bold green]")

    return downloaded_songs, failed_songs


def main() -> None:
    """Main entry point function that orchestrates argument parsing, validation, downloader init, and processing.

    This function keeps the CLI/API of the module unchanged but delegates work to small helpers for readability and testability.
    """
    args = parse_arguments()
    console = create_ui_elements()
    console.print(Panel(Text("Spotify Music Ripper Initializing...", justify="center", style="bold blue")))

    config = get_config()
    try:
        validate_credentials(config)
    except ValueError as ve:
        console.print(f"[bold red]Error: {ve}[/bold red]")
        console.print("Please set them in a .env file in the project root as per the README.md.")
        return

    try:
        downloader = init_downloader(SpotifyDownloader)
    except ValueError as e:
        console.print(f"[bold red]Error initializing Spotify Downloader: {e}[/bold red]")
        return
    except Exception as e:
        console.print(f"[bold red]An unexpected error occurred during initialization: {e}[/bold red]")
        logger.error(f"Initialization failed: {e}", exc_info=True)
        return

    try:
        console.print(f"Fetching track list from playlist: [link={args.playlist_url}]{args.playlist_url}[/link]")
        tracks = downloader.get_playlist_tracks(args.playlist_url)
    except Exception as exc:
        logger.exception("Failed to fetch playlist tracks")
        console.print("[bold red]Failed to fetch playlist tracks. See logs for details.[/bold red]")
        return

    if not tracks:
        console.print("[yellow]No tracks found in the playlist or could not fetch tracks. Exiting.[/yellow]")
        return

    console.print(f"Found {len(tracks)} tracks. Preparing to download to: [cyan]{os.path.abspath(args.download_folder)}[/cyan]")

    downloaded_songs, failed_songs = process_tracks(downloader, tracks, args.download_folder, console, ensure_dir_fn=ensure_dir_exists)

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
            logging.FileHandler(log_file_path, mode="a"),  # Append mode
            # logging.StreamHandler() # Already handled by Rich for console, but could be added if needed
        ],
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