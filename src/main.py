# src/main.py
"""Main entry point for the Music Ripper CLI application."""

import argparse
import os
import logging
import sys

# Adjust path to import from sibling directories
# This is a common pattern for structuring Python projects.
# It ensures that when main.py is run, it can find other modules in the src package.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.dependency_check import ensure_dependencies

if __name__ == "__main__":
    # Runs before the third-party imports below, so an outdated or missing
    # dependency is explained clearly instead of failing with an ImportError.
    STARTUP_CHECK = ensure_dependencies()

from rich.console import Console  # noqa: E402
from rich.markup import escape  # noqa: E402
from rich.table import Table  # noqa: E402
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn, TimeRemainingColumn  # noqa: E402
from rich.panel import Panel  # noqa: E402
from rich.text import Text  # noqa: E402

from src.spotify_downloader import SpotifyDownloader, DownloadResult, PlaylistFetchError, parse_playlist_id  # noqa: E402
from src.config import DEFAULT_DOWNLOAD_DIR, SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET, SPOTIPY_REDIRECT_URI, SPOTIFY_TOKEN_CACHE  # noqa: E402
from src.utils import ensure_dir_exists  # noqa: E402

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

    # Names and error messages come from Spotify/yt-dlp and may contain [brackets], which Rich would treat as markup.
    for song in downloaded_songs:
        summary_table.add_row("[green]Success[/green]", escape(song['name']), escape(song['artist']), escape(song.get('source', 'N/A')),
                              escape(f"{song['quality']}, saved to {song['path']}"))

    for song_info in failed_songs:
        summary_table.add_row("[red]Failed[/red]", escape(song_info['name']), escape(song_info['artist']), "-",
                              f"{len(song_info['failures'])} attempt(s) failed, see below")

    console.print(summary_table)
    console.print(f"\nAll processing finished. Files are in: [cyan]{escape(os.path.abspath(download_folder))}[/cyan]")
    if failed_songs:
        console.print(f"\n[bold yellow]Why {len(failed_songs)} song(s) could not be downloaded:[/bold yellow]")
        for song_info in failed_songs:
            console.print(f"[bold]{escape(song_info['artist'])} - {escape(song_info['name'])}[/bold]")
            for failure in song_info['failures'] or ["no sources were tried"]:
                console.print(f"  - {escape(failure)}")
        console.print("[dim]Full details are in music_ripper.log.[/dim]")


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
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Don't open a browser for the Spotify login; print the login URL and ask for the redirected URL instead (for SSH/headless use)."
    )

    args = parser.parse_args()
    console = create_ui_elements()

    console.print(Panel(Text("Spotify Music Ripper Initializing...", justify="center", style="bold blue")))

    if not SPOTIPY_CLIENT_ID or not SPOTIPY_CLIENT_SECRET:
        console.print("[bold red]Error: Spotify API credentials (SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET) not found.[/bold red]")
        console.print("Please set them in a .env file in the project root as per the README.md.")
        return 1

    try:
        parse_playlist_id(args.playlist_url) # Reject album/track links before asking the user to log in
    except PlaylistFetchError as e:
        console.print(f"[bold red]Error:[/bold red] {escape(str(e))}")
        return 1

    try:
        downloader = SpotifyDownloader(open_browser=not args.no_browser)
    except ValueError as e:
        console.print(f"[bold red]Error initializing Spotify Downloader: {escape(str(e))}[/bold red]")
        return 1
    except Exception as e:
        console.print(f"[bold red]An unexpected error occurred during initialization: {escape(str(e))}[/bold red]")
        logger.error(f"Initialization failed: {e}", exc_info=True)
        return 1

    if not downloader.has_cached_login():
        console.print(Panel(
            f"Log in to Spotify to continue. {'Open the URL printed below' if args.no_browser else 'A browser window will open'}, "
            f"approve access, and you'll be sent back to [cyan]{escape(SPOTIPY_REDIRECT_URI)}[/cyan].\n"
            "If Spotify shows [bold]INVALID_CLIENT: Invalid redirect URI[/bold], add exactly that URI under "
            "'Redirect URIs' in your app's settings on the Spotify Developer Dashboard (see README) and run again.\n"
            f"Your login is saved to {escape(SPOTIFY_TOKEN_CACHE)}; delete that file to log out.",
            title="Spotify login", border_style="cyan"))

    console.print(f"Fetching track list from playlist: [link={args.playlist_url}]{escape(args.playlist_url)}[/link]")
    try:
        tracks = downloader.get_playlist_tracks(args.playlist_url)
    except PlaylistFetchError as e:
        console.print(f"[bold red]Could not read the playlist:[/bold red] {escape(str(e))}")
        return 1

    if not tracks:
        console.print("[yellow]The playlist has no downloadable tracks (it is empty or only contains podcast episodes). Exiting.[/yellow]")
        return 0

    console.print(f"Found {len(tracks)} tracks. Preparing to download to: [cyan]{escape(os.path.abspath(args.download_folder))}[/cyan]")
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
            progress.update(task_download, description=f"Processing: {escape(track_info['artist'])} - {escape(track_info['name'])}")
            
            # Attempt to download the song
            try:
                result = downloader.download_song(track_info, args.download_folder)
            except Exception as e: # Don't let one song's unexpected error abort the whole playlist
                logger.error(f"Unexpected error processing {track_info['artist']} - {track_info['name']}: {e}", exc_info=True)
                result = DownloadResult(failures=[f"unexpected error: {type(e).__name__}: {e}"])
            
            if result.path:
                downloaded_songs.append({
                    "name": track_info["name"], 
                    "artist": track_info["artist"], 
                    "path": result.path,
                    "source": result.source or "Unknown", # Store the source
                    "quality": result.quality or "quality unknown",
                })
                logger.info(f"Successfully processed: {track_info['artist']} - {track_info['name']} from {result.source} ({result.quality})")
            else:
                failed_songs.append({**track_info, "failures": result.failures})
                logger.warning(f"Failed to process: {track_info['artist']} - {track_info['name']}")
                last_reason = result.failures[-1] if result.failures else "no sources were tried"
                progress.console.print(f"[red]Failed:[/red] {escape(track_info['artist'])} - {escape(track_info['name'])} [dim]({escape(last_reason)})[/dim]")
            
            progress.advance(task_download)
        
        # Ensure progress bar finishes if transient=False is not fully effective or if you want a final message within it.
        progress.update(task_download, description="[bold green]All tracks processed![/bold green]")

    display_summary(console, downloaded_songs, failed_songs, args.download_folder)
    return 0

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
    for warning in STARTUP_CHECK.warnings:
        logger.warning(f"Startup check: {warning}")
    exit_code = 1
    try:
        exit_code = main()
    except KeyboardInterrupt:
        Console().print("\n[yellow]Cancelled.[/yellow]")
    except Exception as e:
        # Catch any unhandled exceptions from main and log them
        logger.critical(f"Unhandled exception in main: {e}", exc_info=True)
        console = Console()
        console.print(f"[bold red]A critical error occurred: {type(e).__name__}: {escape(str(e))}[/bold red]")
        console.print("Please check the log file (music_ripper.log) for more details.")
    logger.info("Application finished.")
    sys.exit(exit_code) 