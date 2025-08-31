# Music Ripper

A command-line application to download songs from a Spotify playlist.

## Features

-   Downloads all songs from a given Spotify playlist link.
-   Saves songs as MP3 files at 320Kbps.
-   Validates the downloaded audio format and quality.
-   Uses a rich console interface for user interaction and progress display.

## Disclaimer

This tool is for educational purposes. Please ensure you have the legal right to download the music you are accessing with this tool.

## Setup

1.  Clone the repository.
2.  Install Python 3.8+ if you haven't already.
3.  Create a virtual environment (recommended):
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    ```
4.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
5.  Set up Spotify API credentials (see Configuration section).

## Configuration

You will need to set up Spotify API credentials for this application to work.

1.  Go to the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard/) and log in or create an account.
2.  Create a new App.
3.  Note down the `Client ID` and `Client Secret`.
4.  Create a `.env` file in the root of the project and add your credentials:
    ```env
    SPOTIPY_CLIENT_ID='YOUR_CLIENT_ID'
    SPOTIPY_CLIENT_SECRET='YOUR_CLIENT_SECRET'
    ```

## Usage

```bash
python src/main.py <spotify_playlist_link> [download_folder]
```

-   `<spotify_playlist_link>`: The URL of the Spotify playlist.
-   `[download_folder]`: (Optional) The folder where songs will be downloaded. Defaults to `Downloads` in the project directory. 




