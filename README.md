# Music Ripper

A powerful command-line application to download songs from Spotify playlists with high-quality MP3 output, rich console interface, and comprehensive audio processing.

## Features

-   **Spotify Integration**: Downloads all songs from any public Spotify playlist using the official Spotify API
-   **High-Quality Audio**: Saves songs as MP3 files at 320Kbps with automatic quality validation
-   **Multiple Sources**: Intelligently searches across YouTube and SoundCloud for the best audio quality
-   **Rich UI**: Beautiful console interface with progress bars, colored output, and detailed status information
-   **Audio Processing**: Automatic conversion, bitrate validation, and metadata embedding
-   **Robust Error Handling**: Comprehensive logging and graceful failure recovery
-   **Batch Processing**: Efficiently processes entire playlists with detailed summary reports

## Disclaimer

This tool is for educational purposes only. Please ensure you have the legal right to download the music you are accessing with this tool. Respect copyright laws and the terms of service of the platforms being used.

## Requirements

- Python 3.8 or higher
- FFmpeg (for audio processing)
- Active internet connection
- Spotify Developer API credentials

## Setup

### 1. Clone the Repository
```bash
git clone <repository-url>
cd music-ripper
```

### 2. Install Python Dependencies
Create a virtual environment (recommended):
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

Install required packages:
```bash
pip install -r requirements.txt
```

### 3. Install FFmpeg
FFmpeg is required for audio processing:

**Windows:**
- Download from [https://ffmpeg.org/download.html](https://ffmpeg.org/download.html)
- Add to your system PATH

**macOS:**
```bash
brew install ffmpeg
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt update
sudo apt install ffmpeg
```

### 4. Set up Spotify API Credentials
1.  Go to the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard/)
2.  Log in with your Spotify account
3.  Click "Create App"
4.  Fill in the app details:
    - **App Name**: Music Ripper (or any name you prefer)
    - **App Description**: Personal music downloader
    - **Website**: You can leave this blank or use a placeholder
    - **Redirect URI**: Not needed for this application
5.  Accept the terms and click "Create"
6.  Copy your `Client ID` and `Client Secret`

### 5. Configure Environment Variables
Create a `.env` file in the project root:
```env
SPOTIPY_CLIENT_ID='your_client_id_here'
SPOTIPY_CLIENT_SECRET='your_client_secret_here'
```

**Example `.env` file:**
```env
SPOTIPY_CLIENT_ID='a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6'
SPOTIPY_CLIENT_SECRET='x1y2z3a4b5c6d7e8f9g0h1i2j3k4l5m6n7o8p9q0'
```

## Usage

### Basic Usage
```bash
python src/main.py <spotify_playlist_url> [download_folder]
```

### Parameters
- `<spotify_playlist_url>`: The full URL of the Spotify playlist to download
- `[download_folder]`: (Optional) Destination folder for downloaded files. Defaults to `Downloads/`

### Examples

**Download to default folder:**
```bash
python src/main.py https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M
```

**Download to custom folder:**
```bash
python src/main.py https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M ./MyMusic
```

**Download with full path:**
```bash
python src/main.py "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M?si=abc123" "/Users/username/Music/Playlists"
```

### Sample Output
```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃                Spotify Music Ripper Initializing...                ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

Fetching track list from playlist: https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M
Found 50 tracks. Preparing to download to: /path/to/Downloads

⠋ Processing: Artist Name - Song Title ████████████████████ 100% 0:02:30 0:00:00

┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃                          Download Summary                           ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
┃ Status  ┃ Track Name        ┃ Artist       ┃ Source   ┃ Details           ┃
┡━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━┩
│ Success │ Song Title        │ Artist Name  │ YouTube  │ Saved to song.mp3 │
└─────────┴───────────────────┴──────────────┴──────────┴───────────────────┘

All processing finished. Files are in: /absolute/path/to/Downloads
```

## Troubleshooting

### Common Issues

**"Spotify API credentials not found"**
- Ensure your `.env` file exists in the project root
- Check that `SPOTIPY_CLIENT_ID` and `SPOTIPY_CLIENT_SECRET` are correctly set
- Verify your credentials are valid on the Spotify Developer Dashboard

**"No tracks found in the playlist"**
- Check if the playlist URL is correct
- Ensure the playlist is public (private playlists require additional OAuth setup)
- Try copying the URL again from Spotify

**"FFmpeg not found"**
- Install FFmpeg using the instructions in the Setup section
- Ensure FFmpeg is in your system PATH
- On Windows, restart your command prompt after installation

**"Failed to download songs"**
- Check your internet connection
- Some songs may not be available on YouTube or SoundCloud
- Check the log file (`music_ripper.log`) for detailed error information

**Permission Errors**
- Ensure you have write permissions to the download directory
- Try running with a different download folder
- On Unix systems, check file permissions: `ls -la Downloads/`

### Logging

The application creates detailed logs in `music_ripper.log`. Check this file for:
- Detailed error messages
- Download progress information
- API interaction logs
- Audio processing details

### Performance Tips

- Use SSD storage for faster audio processing
- Close other bandwidth-intensive applications during downloads
- For large playlists (100+ songs), consider running overnight
- The application automatically retries failed downloads

## Project Structure

```
music-ripper/
├── src/
│   ├── main.py              # CLI entry point and user interface
│   ├── spotify_downloader.py # Spotify API integration and download orchestration
│   ├── audio_processor.py   # Audio conversion and quality validation
│   ├── config.py           # Configuration settings and constants
│   └── utils.py            # Utility functions and helpers
├── requirements.txt        # Python dependencies
├── .env                   # Environment variables (create this)
├── music_ripper.log      # Application logs (auto-generated)
└── Downloads/            # Default download directory (auto-generated)
```

## Dependencies

- **spotipy**: Spotify Web API integration
- **yt-dlp**: YouTube and SoundCloud downloading
- **pydub**: Audio processing and conversion
- **rich**: Beautiful console output and progress bars
- **requests**: HTTP requests for cover art and metadata
- **python-dotenv**: Environment variable management
- **Pillow**: Image processing for cover art

## License

This project is for educational purposes only. Please ensure compliance with all applicable laws and terms of service. 





