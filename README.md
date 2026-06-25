# Navidrome Import Tools

A collection of scripts for importing Spotify playlists and liked songs into Navidrome via M3U playlists, with optional Lidarr integration.

Features an optional web interface with real-time progress tracking and playlist selection.

## Features

<table> <tr> <td> <img width="100%" height="auto" alt="Spotify playlist import screenshot 1" src="https://github.com/user-attachments/assets/71ff5a98-d05e-4012-9642-558ab349f0cf" /> </td> <td> <img width="100%" height="auto" alt="Spotify playlist import screenshot 3" src="https://github.com/user-attachments/assets/5b21d6f8-d497-4fa6-b7f5-3feb8ec97509" /> </td><td> <img width="100%" height="auto" alt="Spotify playlist import screenshot 2" src="https://github.com/user-attachments/assets/1aa60389-2305-4500-a0e1-080b4052d08f" /> </td>  </tr> </table>

- **Spotify Authentication**: Secure OAuth integration with session management
- **Playlist Management**: Fetch and export any Spotify playlist
- **Liked Songs Export**: Export your entire liked songs collection
- **M3U Generation**: Create playlist files compatible with Navidrome and other media players
- **Send to Navidrome**: Create a playlist directly in Navidrome via the Subsonic API (no manual M3U import)
- **Lidarr Integration**: Automatically add albums to your Lidarr instance
- **Playlist Splitting**: Split large collections into manageable playlists
- **Real-time Progress**: Live updates during processing via WebSocket
- **Docker Support**: Full Docker and Docker Compose support with multi-architecture builds
- **Responsive Design**: Works on desktop and mobile devices

## Quick Start

### Docker (Recommended)

The easiest way to get started is with Docker. The image is available on Docker Hub with multi-architecture support (AMD64/ARM64).

#### Using Docker Compose

1. **Create environment file**:

   ```bash
   cp .env.example .env
   ```

2. **Edit `.env` with your Spotify credentials**:

   ```env
   CLIENT_ID="your_spotify_client_id"
   CLIENT_SECRET="your_spotify_client_secret"
   REDIRECT_URI="http://localhost:8888/callback"
   ```

3. **Create data directory and copy Navidrome database**:

   ```bash
   mkdir -p data
   cp /path/to/your/navidrome.db data/
   ```

4. **Start the application**:

   ```bash
   docker-compose up
   ```

5. **Access**: Open http://localhost:8888 in your browser

#### Using Docker Run

```bash
docker pull ethanbarclay/navidrome-import-tools:latest

docker run -d \
  --name navidrome-import-tools \
  -p 8888:8888 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/output:/app/output \
  --env-file .env \
  ethanbarclay/navidrome-import-tools:latest
```

#### Docker Environment Variables

| Variable        | Description                          | Default                          |
| --------------- | ------------------------------------ | -------------------------------- |
| `CLIENT_ID`     | Spotify Client ID                    | Required                         |
| `CLIENT_SECRET` | Spotify Client Secret                | Required                         |
| `REDIRECT_URI`  | OAuth redirect URI                   | `http://localhost:8888/callback` |
| `DATABASE_PATH` | Path to Navidrome database           | `/app/data/navidrome.db`         |
| `OUTPUT_DIR`    | Output directory for generated files | `/app/output`                    |
| `LIDARR_URL`    | Lidarr API URL                       | Optional                         |
| `API_KEY`       | Lidarr API Key                       | Optional                         |

### Manual Installation

If you prefer to run without Docker:

1. **Clone the repository**:

   ```bash
   git clone <repository-url>
   cd navidrome-import-tools
   ```

2. **Install dependencies**:

   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables**:

   ```bash
   cp .env.example .env
   ```

   Edit `.env` with your credentials:

   ```env
   CLIENT_ID="your_spotify_client_id"
   CLIENT_SECRET="your_spotify_client_secret"
   REDIRECT_URI="http://localhost:8888/callback"
   DATABASE_PATH="/data/navidrome.db"  # Path to your Navidrome database
   OUTPUT_DIR="./output"  # Where M3U files will be saved
   ```

4. **Run the application**:

   ```bash
   python app.py
   ```

5. **Access**: Open http://localhost:8888 in your browser

### Spotify App Setup

1. Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Create a new app
3. Add your redirect URI (see below)
4. Copy Client ID and Client Secret to your `.env` file

> **Important:** Spotify requires HTTPS for redirect URIs, with an exception for loopback addresses (`localhost` / `127.0.0.1`). If you're accessing the app locally, use `http://localhost:8888/callback` or `http://127.0.0.1:8888/callback`. If you're accessing it over your network (e.g. `http://192.168.x.x:8888/callback`), you'll need to set up HTTPS or use a reverse proxy with a valid SSL certificate.

## How It Works

### Workflow

1. **Authenticate**: Click "Login with Spotify" to connect your Spotify account
2. **Fetch Playlists or Liked Songs**:
   - Navigate to "Playlists" to select and fetch any of your Spotify playlists
   - Navigate to "Liked Songs" to export your entire library
3. **Generate M3U Playlists**:
   - The tool queries your Navidrome database to match Spotify tracks with your local music files
   - Matches are made using intelligent fuzzy matching on track titles and artists
   - **In-memory mode** (default): Loads entire library into RAM for ~10x faster processing
   - **Direct query mode**: Uses optimized SQL queries for lower memory usage
4. **Import to Navidrome**:
   - Copy generated M3U files to your Navidrome playlists directory
   - Navidrome will automatically detect and import them
5. **(Optional) Send to Lidarr**:
   - Automatically search for and add missing albums to Lidarr for downloading

### Configuration

Configure the application via the Settings page:

- **Navidrome Settings**: Database path (default: `/data/navidrome.db`) and music folder prefix
- **Lidarr Settings**: API URL, API key, quality profile, and root folder
- **Performance**: Toggle in-memory database mode on/off (in-memory mode provides ~10x speed improvement)

## CLI Usage

The scripts in `scripts/` can be run directly using parameters.

### Environment Setup

Copy and configure the example environment file:

```bash
cp .env.example .env
```

Edit `.env` with your credentials. See `.env.example` for all available variables.

### Typical Workflow

```bash
# 1a. Generate M3U directly from a Spotify playlist URL (recommended)
python scripts/spoti_playlist_to_m3u.py generate --spotify "https://open.spotify.com/playlist/ID" my_playlist.m3u

# 1b. Or fetch first, then generate from JSON
python scripts/fetch_spotify_playlist.py
python scripts/spoti_playlist_to_m3u.py generate --json playlist_tracks.json "My Playlist" my_playlist.m3u

# 2. Scan MusicBrainz for album IDs (needed for Lidarr)
python scripts/process_spotify_mb.py

# 3. Send albums to Lidarr
python scripts/mb_lidarr_sync.py output/lidarr_mb_releasegroups.json
```

### Script Reference

#### `fetch_spotify_playlist.py`

Fetches all tracks from a Spotify playlist and exports them as JSON and CSV.

```bash
python scripts/fetch_spotify_playlist.py
```

**Requires:** `CLIENT_ID`, `CLIENT_SECRET`, `REDIRECT_URI`

**Outputs:** `playlist_tracks.json`, `playlist_tracks.csv`

**Note:** The playlist ID is currently configured within the script (`PLAYLIST_ID` variable). Edit this before running.

#### `fetch_spotify_liked.py`

Fetches all of a user's liked/saved songs from Spotify.

```bash
python scripts/fetch_spotify_liked.py
```

**Requires:** `CLIENT_ID`, `CLIENT_SECRET`, `REDIRECT_URI`

**Outputs:** `liked_tracks.json`, `liked_tracks.csv`

#### `spoti_playlist_to_m3u.py`

Generates M3U playlists by matching Spotify tracks against your Navidrome database. Supports fetching directly from the Spotify API or using a pre-fetched JSON file.

```bash
# List sample songs from your Navidrome database
python scripts/spoti_playlist_to_m3u.py list

# Generate from a Spotify playlist URL (fetches tracks automatically)
python scripts/spoti_playlist_to_m3u.py generate --spotify "https://open.spotify.com/playlist/ID" output.m3u

# Generate from a pre-fetched JSON file
python scripts/spoti_playlist_to_m3u.py generate --json playlist_tracks.json "Playlist Name" output.m3u

# Use direct database queries instead of in-memory search (lower memory usage)
python scripts/spoti_playlist_to_m3u.py generate --spotify "https://open.spotify.com/playlist/ID" output.m3u --no-memory

# Create the playlist directly in Navidrome (Subsonic API) instead of an M3U file
python scripts/spoti_playlist_to_m3u.py send-navidrome --spotify "https://open.spotify.com/playlist/ID" --name "My Playlist"
```

`--spotify` and `--json` are mutually exclusive (one is required). When using `--spotify`, the playlist name is auto-fetched from the Spotify API. An optional `playlist_name` argument can override it.

**Requires:** `DATABASE_PATH`, `OUTPUT_DIR`. Additionally `CLIENT_ID`, `CLIENT_SECRET`, `REDIRECT_URI` when using `--spotify`.

**Outputs:** `{name}.m3u` playlist file, `{name}_failed_matches.json` for unmatched tracks

##### `send-navidrome` subcommand

Matches tracks against `DATABASE_PATH` and creates the playlist in Navidrome via the Subsonic API — only tracks found in your library are added.

**Requires:** `DATABASE_PATH` and `NAVIDROME_URL` / `NAVIDROME_USER` / `NAVIDROME_PASSWORD` (or the `--navidrome-url/-user/-password` flags). With `--json`, `--name` is required.

#### `process_spotify_mb.py`

Scans Spotify tracks and looks up their albums on MusicBrainz to get release group IDs (needed for Lidarr import).

```bash
python scripts/process_spotify_mb.py
```

**Configuration:** `INPUT_FILE`, `OUTPUT_FILE`, `FAILED_MATCHES_FILE`, and `MAX_ALBUMS` are configured within the script.

**Outputs:** `lidarr_mb_releasegroups.json`, `failed_matches.json`

**Note:** Respects MusicBrainz rate limits (1 request/second). Large libraries may take a while.

#### `mb_lidarr_sync.py`

Adds albums to Lidarr from a MusicBrainz release groups file. Performs two passes: first adding artists, then adding and searching for albums.

```bash
python scripts/mb_lidarr_sync.py lidarr_mb_releasegroups.json
```

**Requires:** `LIDARR_URL`, `API_KEY`, `ROOT_FOLDER_PATH`, `QUALITY_PROFILE_ID`, `METADATA_PROFILE_ID`

**Note:** Tests Lidarr connectivity before processing. Skips albums already in Lidarr.

#### `spotify_liked_chopper.py`

Splits your liked songs into multiple Spotify playlists of 500 tracks each (useful for Spotify's playlist size limitations).

```bash
python scripts/spotify_liked_chopper.py
```

**Requires:** `CLIENT_ID`, `CLIENT_SECRET`, `REDIRECT_URI`

**Creates playlists:** "All My Liked Songs 1", "All My Liked Songs 2", etc.

## Project Structure

```
navidrome-import-tools/
├── app.py                    # Main Flask application with SocketIO
├── requirements.txt          # Python dependencies
├── Dockerfile               # Multi-stage Docker build
├── docker-compose.yml       # Docker Compose configuration
├── docker-entrypoint.sh     # Container entrypoint script
├── README.md                # This file
├── README-Docker.md         # Docker-specific documentation
├── .env.example             # Environment variables template
├── scripts/                 # Core processing scripts
│   ├── spotify_client.py            # Shared Spotify API client utilities
│   ├── fetch_spotify_playlist.py    # Fetch Spotify playlist data
│   ├── fetch_spotify_liked.py       # Fetch liked songs
│   ├── spoti_playlist_to_m3u.py     # M3U generation with in-memory DB
│   ├── process_spotify_mb.py        # MusicBrainz processing
│   ├── mb_lidarr_sync.py            # Lidarr synchronization
│   └── spotify_liked_chopper.py     # Split large playlists
├── templates/               # HTML templates (Jinja2)
│   ├── base.html           # Base template
│   ├── dashboard.html      # Main dashboard
│   ├── playlists.html      # Playlist management
│   ├── liked_songs.html    # Liked songs management
│   └── settings.html       # Configuration page
├── static/                  # Frontend assets
│   ├── css/
│   │   └── style.css       # Custom styles
│   └── js/
│       ├── main.js         # Core JavaScript & SocketIO
│       ├── playlists.js    # Playlist functionality
│       ├── liked_songs.js  # Liked songs functionality
│       └── settings.js     # Settings functionality
├── data/                    # Mounted volume for Navidrome DB (Docker)
├── output/                  # Generated M3U files and exports
└── temp/                    # Temporary processing files
```

## Architecture

### Backend (Flask + SocketIO)

- **Flask**: Web framework serving the UI and API endpoints
- **SocketIO**: Real-time progress updates during long-running operations
- **Session Management**: Secure OAuth token storage with timeout protection
- **Database Access**: Read-only access to Navidrome SQLite database

### Processing Pipeline

1. **Spotify API**: Fetch playlists/liked songs via Spotipy library
2. **Data Export**: Save track data as JSON for processing
3. **Database Matching**: Query Navidrome DB using in-memory indexing or direct SQL
4. **M3U Generation**: Create playlist files with matched track paths
5. **Optional Lidarr Sync**: Send unmatched albums to Lidarr for acquisition

## Troubleshooting

### Common Issues

1. **"Not authenticated" errors**:

   - Ensure you've logged in with Spotify
   - Check that your Spotify app credentials in `.env` are correct
   - Verify the redirect URI matches in both `.env` and Spotify Developer Dashboard

2. **M3U generation fails**:

   - Verify Navidrome database path is correct (default: `/data/navidrome.db` for Docker)
   - Ensure database file is readable
   - For Docker: Check that the database is mounted in the `data/` volume
   - Try disabling in-memory mode if experiencing memory issues

3. **Database not found (Docker)**:

   - Ensure Navidrome database is copied to `./data/navidrome.db`
   - Check volume mounts in `docker-compose.yml`
   - Verify file permissions allow the container to read the database
   - Check logs: `docker logs navidrome-import-tools`

4. **Poor match rates**:

   - Ensure your Navidrome library is properly tagged (especially artist and title metadata)
   - Check that music files have been scanned and indexed by Navidrome
   - Review the "failed matches" output file to see which tracks couldn't be matched

5. **Lidarr integration fails**:

   - Verify Lidarr URL and API key in Settings
   - Ensure Lidarr is accessible from the application (network connectivity)
   - Check Lidarr logs for any errors

6. **Session timeout**:
   - Sessions expire after 2 hours for security
   - Simply log in again with Spotify to continue

### Logs

- **Manual installation**: Check console output where `app.py` is running
- **Docker**: Use `docker logs navidrome-import-tools` or `docker-compose logs -f`

## Development

### Running Locally for Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
cp .env.example .env
# Edit .env with your credentials

# Run in development mode
python app.py
```

### Adding New Features

1. **Backend**: Add new routes and API endpoints in `app.py`
2. **Frontend**: Create or modify templates in `templates/`
3. **JavaScript**: Add functionality in `static/js/`
4. **Styles**: Modify `static/css/style.css`
5. **Processing**: Add new scripts in `scripts/` directory

### WebSocket Events

The application uses SocketIO for real-time updates:

- `progress` - Progress updates during processing (with percentage and status)
- `error` - Error messages
- `playlist_fetched` - Playlist data ready
- `liked_songs_fetched` - Liked songs data ready
- `m3u_generated` - M3U file generated (with download link)
- `lidarr_complete` - Lidarr processing complete

## Security Notes

- **Session Management**: 2-hour session timeout with secure cookie settings
- **OAuth Tokens**: Stored server-side in encrypted sessions
- **Secret Key**: Auto-generated and persisted in `.secret_key` file
- **Docker Security**: Runs as non-root user (`appuser`)
- **Environment Variables**: Sensitive credentials stored in `.env` file
- **Intended Use**: Local or private network deployment only

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

## License

This project is open source and available under the MIT License.
