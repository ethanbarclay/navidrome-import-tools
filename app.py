import hashlib
import json
import os
import secrets
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta

import spotipy
from dotenv import load_dotenv
from flask import (
    Flask,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from flask_socketio import SocketIO, emit
from spotipy.oauth2 import SpotifyOAuth

# Add scripts directory to path to import existing scripts
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts"))

load_dotenv()

app = Flask(__name__)


# Secure session configuration
def get_secret_key():
    """Get or generate a persistent secret key"""
    secret_key_file = os.path.join(os.path.dirname(__file__), ".secret_key")

    if os.path.exists(secret_key_file):
        with open(secret_key_file, "rb") as f:
            return f.read()
    else:
        # Generate a new secret key
        secret_key = secrets.token_bytes(32)
        with open(secret_key_file, "wb") as f:
            f.write(secret_key)
        # Set restrictive permissions
        os.chmod(secret_key_file, 0o600)
        return secret_key


app.config["SECRET_KEY"] = get_secret_key()

# Session security configuration
app.config["SESSION_COOKIE_SECURE"] = (
    os.getenv("FLASK_ENV") == "production"
)  # HTTPS only in production
app.config["SESSION_COOKIE_HTTPONLY"] = True  # Prevent XSS access to cookies
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"  # CSRF protection
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=2)  # 2-hour session timeout

socketio = SocketIO(app, cors_allowed_origins="*")

# Spotify OAuth configuration
SPOTIFY_CLIENT_ID = os.getenv("CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("CLIENT_SECRET")
SPOTIFY_REDIRECT_URI = os.getenv("REDIRECT_URI", "http://localhost:8888/callback")

# Update redirect URI for web app
os.environ["REDIRECT_URI"] = SPOTIFY_REDIRECT_URI

# Database configuration
DATABASE_PATH = os.getenv("DATABASE_PATH", "navidrome.db")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", ".")
DATA_DIR = os.getenv("DATA_DIR", "data")

# Settings file for runtime configuration
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")

# Ensure directories exist
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)


def load_settings():
    """Load settings from JSON file"""
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return {}


def save_settings(settings):
    """Save settings to JSON file"""
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=2)


def get_spotify_oauth():
    return SpotifyOAuth(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET,
        redirect_uri=SPOTIFY_REDIRECT_URI,
        scope="playlist-read-private playlist-read-collaborative user-library-read playlist-modify-private playlist-modify-public",
    )


def is_session_valid():
    """Enhanced session validation with security checks"""
    if "token_info" not in session:
        return False

    # Check session timeout
    if "session_created" in session:
        session_age = datetime.now() - datetime.fromisoformat(
            session["session_created"]
        )
        if session_age > app.config["PERMANENT_SESSION_LIFETIME"]:
            session.clear()
            return False

    # Check if session has required security markers
    if "session_id" not in session:
        return False

    return True


def create_secure_session(token_info):
    """Create a secure session with additional security markers"""
    session.clear()
    session["token_info"] = token_info
    session["session_created"] = datetime.now().isoformat()
    session["session_id"] = secrets.token_hex(16)
    session["user_agent_hash"] = hashlib.sha256(
        request.headers.get("User-Agent", "").encode()
    ).hexdigest()[:16]
    session.permanent = True


def validate_session_security():
    """Validate session security markers"""
    if not is_session_valid():
        return False

    # Check user agent consistency (basic fingerprinting)
    current_ua_hash = hashlib.sha256(
        request.headers.get("User-Agent", "").encode()
    ).hexdigest()[:16]

    if session.get("user_agent_hash") != current_ua_hash:
        # User agent changed - potential session hijacking
        session.clear()
        return False

    return True


def get_spotify_client():
    if not validate_session_security():
        return None

    token_info = session.get("token_info")
    if not token_info:
        return None

    sp_oauth = get_spotify_oauth()
    if sp_oauth.is_token_expired(token_info):
        try:
            token_info = sp_oauth.refresh_access_token(token_info["refresh_token"])
            session["token_info"] = token_info
        except Exception:
            # Token refresh failed, clear session
            session.clear()
            return None

    return spotipy.Spotify(auth=token_info["access_token"])


def require_auth(f):
    """Decorator for routes that require authentication"""
    from functools import wraps

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not validate_session_security():
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return decorated_function


@app.route("/")
def dashboard():
    return render_template("dashboard.html", authenticated=validate_session_security())


@app.route("/login")
def login():
    sp_oauth = get_spotify_oauth()
    auth_url = sp_oauth.get_authorize_url()
    return redirect(auth_url)


@app.route("/callback")
def callback():
    sp_oauth = get_spotify_oauth()
    code = request.args.get("code")
    if not code:
        return redirect(url_for("login"))

    try:
        token_info = sp_oauth.get_access_token(code)
        create_secure_session(token_info)
        return redirect(url_for("dashboard"))
    except Exception as e:
        # OAuth failed, redirect to login
        return redirect(url_for("login"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("dashboard"))


@app.route("/playlists")
@require_auth
def playlists():
    return render_template("playlists.html", authenticated=True)


@app.route("/liked-songs")
@require_auth
def liked_songs():
    return render_template("liked_songs.html", authenticated=True)


@app.route("/settings")
def settings():
    saved_settings = load_settings()
    lidarr_settings = saved_settings.get("lidarr", {})
    return render_template(
        "settings.html",
        authenticated=validate_session_security(),
        spotify_client_id=SPOTIFY_CLIENT_ID or "",
        redirect_uri=SPOTIFY_REDIRECT_URI,
        lidarr_url=lidarr_settings.get("url", os.getenv("LIDARR_URL", "")),
        lidarr_api_key=lidarr_settings.get("api_key", os.getenv("API_KEY", "")),
        database_path=DATABASE_PATH,
        database_exists=os.path.exists(DATABASE_PATH),
        output_dir=OUTPUT_DIR,
        output_dir_exists=os.path.isdir(OUTPUT_DIR),
    )


@app.route("/api/settings")
def get_settings():
    """Get current settings"""
    saved_settings = load_settings()
    return jsonify(
        {
            "lidarr": saved_settings.get(
                "lidarr",
                {
                    "url": os.getenv("LIDARR_URL", ""),
                    "api_key": os.getenv("API_KEY", ""),
                    "root_folder": "/music/",
                    "quality_profile_id": 1,
                    "metadata_profile_id": 1,
                },
            )
        }
    )


@app.route("/api/settings/lidarr", methods=["POST"])
def save_lidarr_settings():
    """Save Lidarr settings"""
    data = request.get_json()

    saved_settings = load_settings()
    saved_settings["lidarr"] = {
        "url": data.get("lidarr_url", ""),
        "api_key": data.get("api_key", ""),
        "root_folder": data.get("root_folder", "/music/"),
        "quality_profile_id": data.get("quality_profile_id", 1),
        "metadata_profile_id": data.get("metadata_profile_id", 1),
    }
    save_settings(saved_settings)

    return jsonify({"success": True, "message": "Lidarr settings saved"})


@app.route("/api/user-profile")
def get_user_profile():
    sp = get_spotify_client()
    if not sp:
        return jsonify({"error": "Not authenticated"}), 401

    try:
        user = sp.current_user()
        return jsonify(
            {
                "display_name": user.get("display_name") or user.get("id"),
                "id": user.get("id"),
                "followers": user.get("followers", {}).get("total", 0),
                "images": user.get("images", []),
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/user-playlists")
def get_user_playlists():
    sp = get_spotify_client()
    if not sp:
        return jsonify({"error": "Not authenticated"}), 401

    try:
        playlists = sp.current_user_playlists(limit=50)
        return jsonify(playlists)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/fetch-playlist", methods=["POST"])
def fetch_playlist():
    sp = get_spotify_client()
    if not sp:
        return jsonify({"error": "Not authenticated"}), 401

    data = request.get_json()
    playlist_id = data.get("playlist_id")

    if not playlist_id:
        return jsonify({"error": "Playlist ID required"}), 400

    # Extract playlist ID from URL if needed
    if "playlist/" in playlist_id:
        playlist_id = playlist_id.split("playlist/")[1].split("?")[0]

    def fetch_playlist_task():
        try:
            socketio.emit(
                "progress", {"message": "Starting playlist fetch...", "progress": 0}
            )

            # Get playlist info
            playlist = sp.playlist(playlist_id)
            socketio.emit(
                "progress",
                {
                    "message": f'Fetching tracks from "{playlist["name"]}"...',
                    "progress": 10,
                },
            )

            # Fetch all tracks
            tracks = []
            limit = 100
            offset = 0
            total = playlist.get("tracks", {}).get("total", 1) or 1

            while True:
                results = sp.playlist_items(playlist_id, limit=limit, offset=offset)
                items = results["items"]
                if not items:
                    break

                for item in items:
                    track = item.get("item") or item.get("track")
                    if track is None:
                        continue
                    if track.get("type") != "track":
                        continue
                    if not track.get("artists") or not track.get("album"):
                        continue
                    tracks.append(
                        {
                            "track_id": track["id"],
                            "track_name": track["name"],
                            "artist_name": ", ".join(
                                [artist["name"] for artist in track["artists"]]
                            ),
                            "artist_id": ", ".join(
                                [artist["id"] for artist in track["artists"]]
                            ),
                            "album_name": track["album"]["name"],
                            "album_id": track["album"]["id"],
                            "added_at": item.get("added_at", ""),
                            "track_uri": track["uri"],
                            "popularity": track.get("popularity", ""),
                            "duration_ms": track.get("duration_ms", ""),
                        }
                    )

                offset += len(items)
                progress = min(
                    90, int((offset / total) * 80) + 10
                )
                socketio.emit(
                    "progress",
                    {"message": f"Fetched {offset} tracks...", "progress": progress},
                )

            # Save to temporary file
            temp_file = tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False, encoding="utf-8"
            )
            json.dump(tracks, temp_file, ensure_ascii=False, indent=2)
            temp_file.close()

            socketio.emit(
                "progress",
                {
                    "message": f"Completed! Fetched {len(tracks)} tracks.",
                    "progress": 100,
                },
            )
            socketio.emit(
                "playlist_fetched",
                {
                    "playlist_name": playlist["name"],
                    "track_count": len(tracks),
                    "temp_file": temp_file.name,
                    "tracks": tracks,  # Send all tracks for pagination
                },
            )

        except Exception as e:
            socketio.emit("error", {"message": f"Error fetching playlist: {str(e)}"})

    thread = threading.Thread(target=fetch_playlist_task)
    thread.start()

    return jsonify({"message": "Playlist fetch started"})


@app.route("/api/fetch-liked-songs", methods=["POST"])
def fetch_liked_songs():
    sp = get_spotify_client()
    if not sp:
        return jsonify({"error": "Not authenticated"}), 401

    def fetch_liked_task():
        try:
            socketio.emit(
                "progress",
                {"message": "Getting total count of liked songs...", "progress": 0},
            )

            # First, get the total count by making a single request
            initial_results = sp.current_user_saved_tracks(limit=1, offset=0)
            total_tracks = initial_results["total"]

            socketio.emit(
                "progress",
                {
                    "message": f"Found {total_tracks} liked songs. Starting fetch...",
                    "progress": 5,
                },
            )

            tracks = []
            limit = 50
            offset = 0

            while True:
                results = sp.current_user_saved_tracks(limit=limit, offset=offset)
                items = results["items"]
                if not items:
                    break

                for item in items:
                    track = item.get("track")
                    if track is None:
                        continue
                    tracks.append(
                        {
                            "track_id": track["id"],
                            "track_name": track["name"],
                            "artist_name": ", ".join(
                                [artist["name"] for artist in track["artists"]]
                            ),
                            "artist_id": ", ".join(
                                [artist["id"] for artist in track["artists"]]
                            ),
                            "album_name": track["album"]["name"],
                            "album_id": track["album"]["id"],
                            "added_at": item.get("added_at", ""),
                            "track_uri": track["uri"],
                            "popularity": track.get("popularity", ""),
                            "duration_ms": track.get("duration_ms", ""),
                        }
                    )

                offset += len(items)
                # Calculate accurate progress: 5% for initial setup, 90% for fetching, 5% for saving
                progress = 5 + int((offset / total_tracks) * 90)
                socketio.emit(
                    "progress",
                    {
                        "message": f"Fetched {offset} of {total_tracks} liked songs...",
                        "progress": progress,
                    },
                )

            socketio.emit(
                "progress", {"message": "Saving data to file...", "progress": 95}
            )

            # Save to temporary file
            temp_file = tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False, encoding="utf-8"
            )
            json.dump(tracks, temp_file, ensure_ascii=False, indent=2)
            temp_file.close()

            socketio.emit(
                "progress",
                {
                    "message": f"Completed! Fetched {len(tracks)} liked songs.",
                    "progress": 100,
                },
            )
            socketio.emit(
                "liked_songs_fetched",
                {
                    "track_count": len(tracks),
                    "total_count": total_tracks,
                    "temp_file": temp_file.name,
                    "tracks": tracks[:10],  # Send first 10 for preview
                },
            )

        except Exception as e:
            socketio.emit("error", {"message": f"Error fetching liked songs: {str(e)}"})

    thread = threading.Thread(target=fetch_liked_task)
    thread.start()

    return jsonify({"message": "Liked songs fetch started"})


@app.route("/api/generate-m3u", methods=["POST"])
def generate_m3u():
    data = request.get_json()
    temp_file = data.get("temp_file")
    playlist_name = data.get("playlist_name", "spotify_playlist")

    if not temp_file or not os.path.exists(temp_file):
        return jsonify({"error": "Invalid temp file"}), 400

    def generate_m3u_task():
        try:
            socketio.emit(
                "progress", {"message": "Generating M3U playlist...", "progress": 0}
            )

            # Check if database exists before proceeding
            if not os.path.exists(DATABASE_PATH):
                socketio.emit(
                    "error",
                    {
                        "message": f"Navidrome database not found at {DATABASE_PATH}. Please ensure your database is mounted correctly."
                    },
                )
                return

            # Use the existing script logic - write to OUTPUT_DIR
            output_file = os.path.join(
                OUTPUT_DIR, f"{playlist_name.replace(' ', '_')}.m3u"
            )

            # Import and use the existing M3U generation function
            from spoti_playlist_to_m3u import generate_m3u_from_db

            socketio.emit(
                "progress",
                {
                    "message": "Processing tracks with Navidrome database...",
                    "progress": 50,
                },
            )
            generate_m3u_from_db(playlist_name, temp_file, output_file, test_mode=False)

            # Verify the file was actually created
            if not os.path.exists(output_file):
                socketio.emit(
                    "error",
                    {
                        "message": "M3U file was not created. Check server logs for details."
                    },
                )
                return

            socketio.emit(
                "progress",
                {"message": "M3U playlist generated successfully!", "progress": 100},
            )
            # Send just the filename, not the full path (download endpoint adds OUTPUT_DIR)
            socketio.emit("m3u_generated", {"file_path": os.path.basename(output_file)})

        except Exception as e:
            socketio.emit("error", {"message": f"Error generating M3U: {str(e)}"})

    thread = threading.Thread(target=generate_m3u_task)
    thread.start()

    return jsonify({"message": "M3U generation started"})


@app.route("/api/scan-mb-albums", methods=["POST"])
def scan_mb_albums():
    """Scan MusicBrainz for album IDs from a Spotify playlist"""
    data = request.get_json()
    temp_file = data.get("temp_file")
    playlist_name = data.get("playlist_name", "playlist")

    if not temp_file or not os.path.exists(temp_file):
        return jsonify({"error": "Invalid temp file"}), 400

    def scan_mb_task():
        try:
            socketio.emit(
                "progress",
                {"message": "Starting MusicBrainz album scan...", "progress": 0},
            )

            from process_spotify_mb import clean_string, query_mb_releasegroup

            # Load the playlist tracks
            with open(temp_file, encoding="utf-8") as f:
                playlist_tracks = json.load(f)

            # Extract unique albums
            albums = {}
            for entry in playlist_tracks:
                artist_raw = entry.get("artist_name") or entry.get("artist") or ""
                album_raw = entry.get("album_name") or entry.get("album") or ""
                if not album_raw or not artist_raw:
                    continue
                primary_artist = clean_string(artist_raw.split(",")[0])
                album = clean_string(album_raw)
                key = (primary_artist.lower(), album.lower())
                if key not in albums:
                    albums[key] = {
                        "artist": primary_artist,
                        "album": album,
                        "tracks": [],
                    }
                albums[key]["tracks"].append(entry)

            total_albums = len(albums)
            socketio.emit(
                "progress",
                {
                    "message": f"Found {total_albums} unique albums. Scanning MusicBrainz...",
                    "progress": 10,
                },
            )

            result = []
            failed_matches = []

            for idx, ((artist_key, album_key), info) in enumerate(albums.items()):
                artist = info["artist"]
                album = info["album"]
                progress = 10 + int((idx / total_albums) * 80)
                socketio.emit(
                    "progress",
                    {"message": f"Scanning: {artist} - {album}", "progress": progress},
                )

                mb_id = query_mb_releasegroup(artist, album)
                if not mb_id and artist:
                    mb_id = query_mb_releasegroup("", album)

                if mb_id:
                    result.append(
                        {"MusicBrainzId": mb_id, "artist": artist, "album": album}
                    )
                else:
                    failed_matches.append(
                        {"artist": artist, "album": album, "tracks": info["tracks"]}
                    )

                time.sleep(1.1)  # MusicBrainz rate limit

            # Save results to OUTPUT_DIR
            safe_name = playlist_name.replace(" ", "_")
            mb_output_file = os.path.join(OUTPUT_DIR, f"{safe_name}_mb_albums.json")
            failed_output_file = os.path.join(OUTPUT_DIR, f"{safe_name}_mb_failed.json")

            with open(mb_output_file, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)

            with open(failed_output_file, "w", encoding="utf-8") as f:
                json.dump(failed_matches, f, indent=2, ensure_ascii=False)

            socketio.emit(
                "progress", {"message": "MusicBrainz scan complete!", "progress": 100}
            )
            # Build list of found album keys for frontend matching
            found_albums = [
                {"artist": r["artist"].lower(), "album": r["album"].lower()}
                for r in result
            ]
            socketio.emit(
                "mb_scan_complete",
                {
                    "message": f"Found {len(result)} albums, {len(failed_matches)} failed",
                    "found": len(result),
                    "failed": len(failed_matches),
                    "mb_file": os.path.basename(mb_output_file),
                    "found_albums": found_albums,
                },
            )

        except Exception as e:
            socketio.emit("error", {"message": f"Error scanning MusicBrainz: {str(e)}"})

    thread = threading.Thread(target=scan_mb_task)
    thread.start()

    return jsonify({"message": "MusicBrainz scan started"})


@app.route("/api/send-to-lidarr", methods=["POST"])
def send_to_lidarr():
    """Send pre-scanned MusicBrainz albums to Lidarr"""
    data = request.get_json()
    mb_file = data.get("mb_file")

    if not mb_file:
        return jsonify(
            {"error": "No MusicBrainz file specified. Run Scan MB Albums first."}
        ), 400

    mb_file_path = os.path.join(OUTPUT_DIR, mb_file)
    if not os.path.exists(mb_file_path):
        return jsonify({"error": f"MusicBrainz file not found: {mb_file}"}), 400

    def send_to_lidarr_task():
        try:
            socketio.emit(
                "progress", {"message": "Loading MusicBrainz albums...", "progress": 0}
            )

            with open(mb_file_path, encoding="utf-8") as f:
                mb_albums = json.load(f)

            if not mb_albums:
                socketio.emit(
                    "error", {"message": "No albums found in MusicBrainz file"}
                )
                return

            # Load saved settings
            saved_settings = load_settings()
            lidarr_settings = saved_settings.get("lidarr", {})

            # Build environment with saved settings (fallback to env vars)
            env = os.environ.copy()
            env["LIDARR_URL"] = lidarr_settings.get("url") or os.getenv(
                "LIDARR_URL", ""
            )
            env["API_KEY"] = lidarr_settings.get("api_key") or os.getenv("API_KEY", "")
            env["ROOT_FOLDER_PATH"] = lidarr_settings.get("root_folder") or os.getenv(
                "ROOT_FOLDER_PATH", "/music/"
            )
            env["QUALITY_PROFILE_ID"] = str(
                lidarr_settings.get("quality_profile_id", 1)
            )
            env["METADATA_PROFILE_ID"] = str(
                lidarr_settings.get("metadata_profile_id", 1)
            )

            socketio.emit(
                "progress",
                {
                    "message": f"Adding {len(mb_albums)} albums to Lidarr...",
                    "progress": 20,
                },
            )

            # Run the Lidarr sync script with the MB file
            result = subprocess.run(
                ["python", "scripts/mb_lidarr_sync.py", mb_file_path],
                capture_output=True,
                text=True,
                cwd=".",
                env=env,
            )

            if result.returncode != 0:
                # Extract error message from output
                error_msg = (
                    result.stdout.strip() or result.stderr.strip() or "Unknown error"
                )
                # Look for ERROR: lines
                for line in (result.stdout + result.stderr).split("\n"):
                    if line.startswith("ERROR:"):
                        error_msg = line
                        break
                raise Exception(error_msg)

            socketio.emit(
                "progress", {"message": "Successfully sent to Lidarr!", "progress": 100}
            )
            socketio.emit(
                "lidarr_complete",
                {"message": f"{len(mb_albums)} albums processed by Lidarr"},
            )

        except Exception as e:
            socketio.emit("error", {"message": f"Error sending to Lidarr: {str(e)}"})

    thread = threading.Thread(target=send_to_lidarr_task)
    thread.start()

    return jsonify({"message": "Lidarr processing started"})


@app.route("/api/test-lidarr", methods=["POST"])
def test_lidarr():
    data = request.get_json()
    lidarr_url = data.get("lidarr_url")
    api_key = data.get("api_key")

    if not lidarr_url or not api_key:
        return jsonify({"error": "Lidarr URL and API key are required"}), 400

    try:
        import requests

        # Test connection by getting system status
        headers = {"X-Api-Key": api_key}
        response = requests.get(
            f"{lidarr_url}/system/status", headers=headers, timeout=10
        )

        if response.status_code == 200:
            status_data = response.json()
            return jsonify(
                {
                    "success": True,
                    "message": "Connection successful!",
                    "version": status_data.get("version", "Unknown"),
                    "app_name": status_data.get("appName", "Lidarr"),
                }
            )
        else:
            return jsonify(
                {
                    "success": False,
                    "message": f"HTTP {response.status_code}: {response.text}",
                }
            ), 400

    except requests.exceptions.RequestException as e:
        return jsonify(
            {"success": False, "message": f"Connection failed: {str(e)}"}
        ), 400
    except Exception as e:
        return jsonify({"success": False, "message": f"Error: {str(e)}"}), 500


@app.route("/api/test-navidrome", methods=["POST"])
def test_navidrome():
    data = request.get_json()
    db_path = data.get("db_path", DATABASE_PATH)

    try:
        import sqlite3

        # Use the configured database path if no specific path provided
        if not db_path:
            db_path = DATABASE_PATH

        # If path is relative, check in scripts directory first, then parent directory
        if not os.path.isabs(db_path):
            scripts_db_path = os.path.join("scripts", db_path)
            if os.path.exists(scripts_db_path):
                db_path = scripts_db_path
            else:
                parent_db_path = os.path.join("..", db_path)
                if os.path.exists(parent_db_path):
                    db_path = parent_db_path

        # Check if database file exists
        if not os.path.exists(db_path):
            return jsonify(
                {
                    "success": False,
                    "message": f"Database file not found: {db_path}. Current DATABASE_PATH: {DATABASE_PATH}",
                }
            ), 400

        # Try to connect and query the database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Test basic query
        cursor.execute("SELECT COUNT(*) FROM media_file")
        track_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM album")
        album_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM artist")
        artist_count = cursor.fetchone()[0]

        conn.close()

        return jsonify(
            {
                "success": True,
                "message": "Database connection successful!",
                "stats": {
                    "tracks": track_count,
                    "albums": album_count,
                    "artists": artist_count,
                },
            }
        )

    except sqlite3.Error as e:
        return jsonify({"success": False, "message": f"Database error: {str(e)}"}), 400
    except Exception as e:
        return jsonify({"success": False, "message": f"Error: {str(e)}"}), 500


@app.route("/api/download-json", methods=["POST"])
def download_json():
    data = request.get_json()
    temp_file = data.get("temp_file")
    filename = data.get("filename", "spotify_data")

    if not temp_file or not os.path.exists(temp_file):
        return jsonify({"error": "Invalid temp file"}), 400

    try:
        # Read the full data from the temporary file
        with open(temp_file, "r", encoding="utf-8") as f:
            full_data = json.load(f)

        return jsonify({"success": True, "data": full_data, "count": len(full_data)})

    except Exception as e:
        return jsonify({"error": f"Failed to read data: {str(e)}"}), 500


@app.route("/download/<filename>")
def download_file(filename):
    try:
        file_path = os.path.join(OUTPUT_DIR, filename)
        return send_file(file_path, as_attachment=True)
    except Exception as e:
        return jsonify({"error": str(e)}), 404


@app.route("/health")
def health_check():
    """Health check endpoint for Docker"""
    return jsonify(
        {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "database_path": DATABASE_PATH,
            "database_exists": os.path.exists(DATABASE_PATH),
        }
    )


if __name__ == "__main__":
    # Check if we're in production environment
    is_production = os.getenv("FLASK_ENV") == "production"

    if is_production:
        # Production mode - use allow_unsafe_werkzeug for simplicity
        # In a real production environment, you'd want to use gunicorn or similar
        socketio.run(
            app, debug=False, host="0.0.0.0", port=8888, allow_unsafe_werkzeug=True
        )
    else:
        # Development mode
        socketio.run(app, debug=True, host="0.0.0.0", port=8888)
