# Music Ripper

A command-line application to download songs from a Spotify playlist.

## Features

-   Reads every song in a Spotify playlist you own or collaborate on.
-   Finds each song on SoundCloud, then YouTube, and saves it as a tagged MP3 with cover art.
-   Honest quality: the MP3 is encoded at the source's bitrate (never above it) and the source quality is recorded (see [Audio quality](#audio-quality)).
-   Validates format, bitrate and length of every file against Spotify's metadata.
-   Checks your Python version, packages, FFmpeg and Spotify settings at startup and explains anything that's wrong.
-   Uses a rich console interface, and explains why each failed song failed.

## Disclaimer

This tool is for educational purposes. Please ensure you have the legal right to download the music you are accessing with this tool.

## Requirements

| What | Version / notes |
| --- | --- |
| Python | 3.10 – 3.14 |
| FFmpeg **and** FFprobe | Any recent release. Both programs are required (see [Install FFmpeg and FFprobe](#install-ffmpeg-and-ffprobe)) |
| Deno (recommended) | Needed by yt-dlp for reliable YouTube downloads (see [Install Deno](#install-deno-recommended-for-youtube)) |
| Spotify account | The account that creates the Spotify app needs **Premium** (a Spotify requirement for apps in Development Mode) |

Python packages are pinned in `requirements.txt` (spotipy 2.26.0, yt-dlp 2026.8.19, Pillow 12.3.0, and so on). On Python 3.13 and newer, `audioop-lts` is installed as well, because pydub needs the `audioop` module that Python 3.13 removed.

## Setup

1.  Clone the repository.
2.  Install Python 3.10 or newer (3.14 works).
3.  Create a virtual environment (recommended):
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    ```
4.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
5.  Install FFmpeg and FFprobe, and optionally Deno (see below).
6.  Set up your Spotify app and `.env` file (see [Spotify setup](#spotify-setup)).
7.  Check your setup:
    ```bash
    python -m src.dependency_check
    ```

### Install FFmpeg and FFprobe

pydub converts audio by running the `ffmpeg` and `ffprobe` programs, so **both** must be installed. They come together in every FFmpeg download.

-   **Windows**: run `winget install Gyan.FFmpeg`, or download a build from <https://www.gyan.dev/ffmpeg/builds/> and extract it so that you have `C:\ffmpeg\bin\ffmpeg.exe` and `C:\ffmpeg\bin\ffprobe.exe`. Adding `C:\ffmpeg\bin` to your `PATH` is recommended (open a **new** terminal afterwards), but not required.
-   **macOS**: `brew install ffmpeg`
-   **Debian/Ubuntu**: `sudo apt install ffmpeg` (other Linux distributions have an `ffmpeg` package too).

Check that both work:

```bash
ffmpeg -version
ffprobe -version
```

Music Ripper finds FFmpeg on your `PATH` and also in the usual install folders, even when they aren't on `PATH`: `C:\ffmpeg\bin`, `C:\ffmpeg*\bin` (e.g. an extracted `C:\ffmpeg-7.1-full_build\bin`), `C:\Program Files\ffmpeg\bin`, winget, Chocolatey and Scoop folders on Windows, and Homebrew/MacPorts folders on macOS. If yours is somewhere else, add this to `.env`:

```env
# The folder containing ffmpeg and ffprobe, or the ffmpeg executable itself.
# Use single quotes for Windows paths so the backslashes are kept as-is.
FFMPEG_PATH='D:\tools\ffmpeg\bin'
# Only needed if ffprobe lives somewhere else:
# FFPROBE_PATH='D:\other\ffprobe.exe'
```

The messages `Couldn't find ffmpeg or avconv` / `Couldn't find ffprobe or avprobe` mean FFmpeg wasn't found. Run `python -m src.dependency_check` to see where Music Ripper looked.

### Install Deno (recommended for YouTube)

YouTube now requires yt-dlp to run some JavaScript. Without a JavaScript runtime, YouTube downloads may fail or offer fewer formats. SoundCloud doesn't need one. [Deno](https://docs.deno.com/runtime/getting_started/installation/) is recommended:

-   **Windows**: `winget install DenoLand.Deno`
-   **macOS**: `brew install deno`
-   **Linux/macOS**: `curl -fsSL https://deno.land/install.sh | sh`

Node.js, Bun and QuickJS also work, and Music Ripper uses whichever is installed. The yt-dlp companion package `yt-dlp-ejs` is installed automatically by `requirements.txt`.

## Spotify setup

Spotify now requires you to log in as a user to read a playlist's songs; the old app-only credentials get `401 Valid user authentication required`. So you need a Spotify app with a **redirect URL**, which is where Spotify sends your browser after you log in.

1.  Go to the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) and log in. The account that creates the app needs Spotify Premium.
2.  Click **Create app** and fill in a name and description.
3.  Under **Redirect URIs**, enter exactly the following and click **Add**:
    ```
    http://127.0.0.1:8888/callback
    ```
    -   Use `127.0.0.1`, **not** `localhost`: Spotify no longer accepts `localhost` redirect URIs. Plain `http` is only allowed for loopback addresses like this one.
    -   The URI must match `SPOTIPY_REDIRECT_URI` character for character (no trailing slash). You can pick another free port, e.g. `http://127.0.0.1:9090/callback`, as long as you use the same URI in both places.
4.  Under **Which API/SDKs are you planning to use?**, tick **Web API**, accept the terms and click **Save**.
5.  Open the app's **Settings**, and copy the **Client ID** and the **Client secret** (click *View client secret*).
6.  If someone other than the app's creator will use Music Ripper, add their name and Spotify e-mail under **User Management** (Development Mode apps allow up to 5 users).
7.  Create a `.env` file in the root of the project:
    ```env
    SPOTIPY_CLIENT_ID='YOUR_CLIENT_ID'
    SPOTIPY_CLIENT_SECRET='YOUR_CLIENT_SECRET'
    SPOTIPY_REDIRECT_URI='http://127.0.0.1:8888/callback'
    ```
    `SPOTIPY_REDIRECT_URI` is optional and defaults to the value above.

### Logging in

The first time you run Music Ripper, it opens your browser at Spotify's login page. After you click **Agree**, Spotify redirects to `http://127.0.0.1:8888/callback`, where Music Ripper catches the login and continues. Your login is saved in `.spotify_token_cache` in the project folder, so later runs don't ask again. Delete that file to log out or switch accounts. It holds a long-lived login token, so never share or commit it (it is already in `.gitignore`).

On a machine without a browser (for example over SSH), add `--no-browser`. Music Ripper prints the login URL. Open it on any device, and after approving, copy the address your browser was redirected to (the page itself will fail to load, which is expected) and paste it into the terminal.

### Which playlists can be downloaded?

Since Spotify's February 2026 API changes, apps in Development Mode can only read the songs of playlists that **the logged-in account owns or collaborates on**. Other playlists fail with `403 Forbidden`. To download someone else's playlist, open it in Spotify, choose **… › Add to other playlist › New playlist**, and use the link of your copy. Playlists made by Spotify itself (editorial playlists and "Made For You" mixes, whose IDs start with `37i9dQZF`) aren't available to third-party apps at all; copy their songs into your own playlist the same way.

## Usage

```bash
python src/main.py <spotify_playlist_link> [download_folder] [--no-browser]
```

-   `<spotify_playlist_link>`: The URL of the Spotify playlist, for example `https://open.spotify.com/playlist/<id>`. `spotify:playlist:<id>` URIs and bare IDs also work.
-   `[download_folder]`: (Optional) The folder where songs will be downloaded. Defaults to `Downloads` in the current directory.
-   `--no-browser`: (Optional) Log in by pasting the redirect URL instead of opening a browser.

Songs that are already downloaded and valid are skipped, so you can re-run the same command to retry failures or pick up new songs. For every song that fails, the summary lists each source and search result that was tried and why it was rejected. `music_ripper.log` has the full details.

## Audio quality

Downloaded audio comes from SoundCloud and YouTube, which serve lossy streams, typically 128–160 kbps (MP3, AAC or Opus). Converting such a stream to a higher bitrate makes the file bigger but can't bring back detail the source never had, so Music Ripper doesn't pretend it can:

-   Search results whose best audio stream is below **128 kbps** are skipped (`MIN_SOURCE_BITRATE_KBPS` in `src/config.py`).
-   The MP3 is encoded at the standard bitrate that matches the source, never above it, with a ceiling of 320 kbps (`MAX_OUTPUT_BITRATE_KBPS`). A 128 kbps source becomes a 128 kbps MP3, not a 320 kbps one. If a site doesn't report the bitrate, Music Ripper measures the downloaded file; if it still can't tell, it encodes at 320 kbps and labels the source quality as unknown.
-   The quality is shown in the summary, for example `MP3 128 kbps (source: mp3 ~128 kbps)`. It is also stored in each song's `.json` file (`source_bitrate_kbps`, `output_bitrate_kbps`, `source_url`) and in the MP3's comment tag.
-   SoundCloud results that only offer a 30-second preview (SoundCloud Go+ tracks), and results whose length doesn't match Spotify's, are skipped.

## Optional settings (`.env`)

| Variable | Purpose |
| --- | --- |
| `SPOTIPY_REDIRECT_URI` | Redirect URI registered in your Spotify app (default `http://127.0.0.1:8888/callback`) |
| `FFMPEG_PATH`, `FFPROBE_PATH` | Location of FFmpeg/FFprobe if they aren't found automatically |
| `YTDLP_COOKIES_FROM_BROWSER` | Browser whose YouTube cookies yt-dlp may use, e.g. `firefox`, `chrome` or `chrome:Profile 1`. Helps when YouTube says *"Sign in to confirm you're not a bot"* |
| `YTDLP_COOKIES_FILE` | Path to a `cookies.txt` file to use instead |

Set the environment variable `MUSICRIPPER_SKIP_CHECKS=1` to skip the startup checks.

## Troubleshooting

Run `python -m src.dependency_check` first. It lists what was found and what needs fixing.

| Problem | Fix |
| --- | --- |
| `401 Valid user authentication required` | Old versions of Music Ripper used app-only credentials, which Spotify no longer accepts for playlists. Update, and log in when the browser opens. If a 401 persists, delete `.spotify_token_cache` and log in again. |
| Browser shows `INVALID_CLIENT: Invalid redirect URI` | Add the exact `SPOTIPY_REDIRECT_URI` (default `http://127.0.0.1:8888/callback`) under *Redirect URIs* in your app's settings. |
| `403 Forbidden` when reading a playlist | You don't own or collaborate on the playlist. Copy it into a playlist of your own (see [Which playlists can be downloaded?](#which-playlists-can-be-downloaded)). Also check that the app owner has Premium and that your account is listed under *User Management*. |
| `404` for a playlist | The link is wrong, or it's a Spotify-made playlist (`37i9dQZF…`), which apps can't read. |
| `Couldn't find ffmpeg` / `ffprobe` | See [Install FFmpeg and FFprobe](#install-ffmpeg-and-ffprobe), or set `FFMPEG_PATH`. |
| YouTube: `Sign in to confirm you're not a bot` | Set `YTDLP_COOKIES_FROM_BROWSER` in `.env`. |
| YouTube/SoundCloud: `No suitable extractor`, `HTTP Error 403`, `Requested format is not available` | Sites change often and old yt-dlp releases stop working. Update it with `pip install -U "yt-dlp[default]"` and install Deno. The startup check warns when your yt-dlp is more than 90 days old. |
| `No module named 'pyaudioop'` / `audioop` | You're on Python 3.13+ without `audioop-lts`: `pip install -r requirements.txt`. |
| Pillow fails to install on Python 3.14 | Old Pillow versions have no Python 3.14 builds. `requirements.txt` now pins Pillow 12.3.0. |

## Running the tests

```bash
python -m unittest
```

The tests that convert audio are skipped when FFmpeg isn't installed.
