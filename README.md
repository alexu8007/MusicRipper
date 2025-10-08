# Music Ripper 🎵

A powerful command-line application to download songs from Spotify playlists with high-quality audio output and automatic format validation.

## ✨ Features

- **Playlist Support**: Download entire Spotify playlists with a single command
- **High-Quality Audio**: Saves songs as MP3 files at 320Kbps bitrate
- **Format Validation**: Automatically validates downloaded audio format and quality
- **Rich UI**: Interactive console interface with real-time progress tracking
- **Flexible Output**: Configure custom download directories
- **Error Handling**: Robust error handling with detailed logging

## ⚠️ Disclaimer

This tool is intended for **educational purposes only**. Users are responsible for ensuring they have the legal right to download and use any music accessed through this tool. Please respect copyright laws and artist rights.

## 📋 Prerequisites

- Python 3.8 or higher
- Spotify Developer account (free)
- Internet connection

## 🚀 Installation

### 1. Clone the Repository

```bash
git clone <repository-url>
cd music-ripper
```

### 2. Set Up Virtual Environment

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Linux/MacOS:
source venv/bin/activate

# On Windows:
venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

## 🔧 Configuration

### Setting Up Spotify API Credentials

1. Navigate to the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard/)
2. Log in or create a free Spotify Developer account
3. Click **"Create an App"**
4. Fill in the app details:
   - **App Name**: Choose any name (e.g., "Music Ripper")
   - **App Description**: Brief description
   - Accept the terms and create
5. Once created, you'll see your **Client ID** and **Client Secret**

### Configure Environment Variables

Create a `.env` file in the project root directory:

```bash
touch .env
```

Add your Spotify credentials to the `.env` file:

```env
SPOTIPY_CLIENT_ID='your_client_id_here'
SPOTIPY_CLIENT_SECRET='your_client_secret_here'
```

**Important**: Never commit your `.env` file to version control. It's already included in `.gitignore`.

## 💻 Usage

### Basic Usage

```bash
python src/main.py <spotify_playlist_link>
```

### Custom Download Directory

```bash
python src/main.py <spotify_playlist_link> /path/to/download/folder
```

### Examples

**Download to default directory:**
```bash
python src/main.py https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M
```

**Download to custom directory:**
```bash
python src/main.py https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M ~/Music/MyPlaylists
```

### Getting Spotify Playlist Links

1. Open Spotify (web or desktop app)
2. Navigate to the playlist you want to download
3. Click the **"..."** menu
4. Select **"Share"** → **"Copy link to playlist"**
5. Use this link with the Music Ripper

## 📁 Project Structure

```
music-ripper/
├── src/
│   ├── main.py              # Entry point and CLI interface
│   ├── spotify_downloader.py  # Spotify API integration
│   ├── audio_processor.py   # Audio download and processing
│   ├── config.py            # Configuration management
│   └── utils.py             # Utility functions
├── requirements.txt         # Python dependencies
├── .env                     # Environment variables (create this)
└── README.md               # This file
```

## 🔍 Troubleshooting

### "Module not found" Error

Make sure you've activated your virtual environment and installed dependencies:
```bash
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
```

### Authentication Error

Verify your `.env` file contains valid Spotify credentials:
- Check for typos in your Client ID and Client Secret
- Ensure there are no extra spaces or quotes
- Confirm the app is active in your Spotify Developer Dashboard

### Download Failures

- Check your internet connection
- Verify the playlist link is valid and publicly accessible
- Ensure you have write permissions for the download directory
- Some tracks may be region-locked or unavailable

### Permission Denied

If you encounter permission errors when writing files:
```bash
# On Linux/MacOS:
chmod -R 755 Downloads/

# Or specify a directory where you have write access
python src/main.py <playlist_link> ~/Music
```

## 🤝 Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

## 📄 License

This project is provided as-is for educational purposes. Users are responsible for complying with all applicable laws and terms of service.

## 🙏 Acknowledgments

- Built with [Spotipy](https://spotipy.readthedocs.io/) - Python library for the Spotify Web API
- Uses [Rich](https://rich.readthedocs.io/) for beautiful terminal output 





