"""Shared Spotify client utilities for CLI scripts."""

import os
import re

import spotipy
from dotenv import load_dotenv
from spotipy.oauth2 import SpotifyOAuth

load_dotenv()

SCOPE = "playlist-read-private playlist-read-collaborative"


def get_spotify_client():
    """Create an authenticated Spotify client from .env credentials."""
    client_id = os.getenv("CLIENT_ID")
    client_secret = os.getenv("CLIENT_SECRET")
    redirect_uri = os.getenv("REDIRECT_URI")

    if not client_id or not client_secret:
        raise RuntimeError(
            "Missing Spotify credentials. Set CLIENT_ID and CLIENT_SECRET in your .env file."
        )

    return spotipy.Spotify(
        auth_manager=SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope=SCOPE,
        )
    )


def extract_playlist_id(input_str):
    """Extract a Spotify playlist ID from a URL or raw ID string."""
    # Match URLs like https://open.spotify.com/playlist/3cXFWPgBhhMy3k2z8HXama?si=...
    match = re.search(r"playlist/([a-zA-Z0-9]+)", input_str)
    if match:
        return match.group(1)
    # Assume it's already a raw playlist ID
    return input_str.strip()


def fetch_playlist_tracks(sp, playlist_id):
    """Fetch all tracks from a Spotify playlist with pagination.

    Returns:
        tuple: (playlist_name, tracks_list)
    """
    playlist = sp.playlist(playlist_id, fields="name")
    playlist_name = playlist["name"]

    tracks = []
    limit = 100
    offset = 0

    print("Fetching playlist tracks...")
    while True:
        results = sp.playlist_items(playlist_id, limit=limit, offset=offset)
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
        if offset % 200 == 0:
            print(f"Fetched {offset} playlist songs so far...")

    print(f"Fetched {len(tracks)} playlist songs.")
    return playlist_name, tracks
