"""Shared Spotify client utilities for CLI scripts."""

import json
import os
import re

import requests
import spotipy
from dotenv import load_dotenv
from spotipy.exceptions import SpotifyException
from spotipy.oauth2 import SpotifyOAuth

load_dotenv()

SCOPE = "playlist-read-private playlist-read-collaborative"

# Spotify-owned algorithmic/editorial playlists (Daily Mix, Discover Weekly,
# Release Radar, the curated editorial lists, etc.) return 404 from the Web API
# for third-party apps. The embed page below still exposes their track list.
EMBED_URL = "https://open.spotify.com/embed/playlist/{}"
_EMBED_HEADERS = {"User-Agent": "Mozilla/5.0"}
_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S
)


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


def flatten_track_item(item):
    """Flatten a playlist or library item into our track dict, or None to skip.

    Handles both the new ``item`` key and the deprecated ``track`` key returned
    by Spotify's playlist endpoints, skips podcast episodes, and skips entries
    missing required artist/album metadata.
    """
    track = item.get("item") or item.get("track")
    if track is None:
        return None
    if track.get("type") != "track":
        return None
    if not track.get("artists") or not track.get("album"):
        return None
    return {
        "track_id": track["id"],
        "track_name": track["name"],
        "artist_name": ", ".join(artist["name"] for artist in track["artists"]),
        "artist_id": ", ".join(artist["id"] for artist in track["artists"]),
        "album_name": track["album"]["name"],
        "album_id": track["album"]["id"],
        "added_at": item.get("added_at", ""),
        "track_uri": track["uri"],
        "popularity": track.get("popularity", ""),
        "duration_ms": track.get("duration_ms", ""),
    }


def fetch_embed_entity(playlist_id):
    """Fetch a playlist's embed page and return its parsed entity dict.

    Used as a fallback for Spotify-owned algorithmic/editorial playlists that
    the Web API blocks with a 404. Raises RuntimeError if the page can't be
    parsed.
    """
    resp = requests.get(
        EMBED_URL.format(playlist_id), headers=_EMBED_HEADERS, timeout=15
    )
    resp.raise_for_status()
    match = _NEXT_DATA_RE.search(resp.text)
    if not match:
        raise RuntimeError("Could not parse Spotify embed page (no __NEXT_DATA__).")
    data = json.loads(match.group(1))
    return data["props"]["pageProps"]["state"]["data"]["entity"]


def fetch_playlist_via_embed(sp, playlist_id, on_name=None, on_progress=None):
    """Fetch tracks for an editorial/algorithmic playlist via the embed page.

    The embed page exposes track URIs even when the Web API returns 404. We
    enrich those IDs through the public ``/tracks`` endpoint (which is not
    blocked) so the resulting dicts match ``flatten_track_item`` exactly.

    Args:
        on_name: optional callable(playlist_name), invoked once the name is
            known (before enrichment).
        on_progress: optional callable(track_count), invoked after each batch.

    Returns:
        tuple: (playlist_name, tracks_list)
    """
    entity = fetch_embed_entity(playlist_id)
    playlist_name = entity.get("name") or entity.get("title") or "Spotify Playlist"
    track_list = entity.get("trackList") or []
    if on_name:
        on_name(playlist_name)

    track_ids = []
    for item in track_list:
        uri = item.get("uri") or ""
        if uri.startswith("spotify:track:"):
            track_ids.append(uri.rsplit(":", 1)[-1])

    tracks = []
    for i in range(0, len(track_ids), 50):
        batch = track_ids[i : i + 50]
        for full_track in sp.tracks(batch)["tracks"]:
            if full_track is None:
                continue
            flat = flatten_track_item({"track": full_track})
            if flat is not None:
                tracks.append(flat)
        if on_progress:
            on_progress(len(tracks))

    return playlist_name, tracks


def fetch_playlist_tracks(sp, playlist_id):
    """Fetch all tracks from a Spotify playlist with pagination.

    Falls back to the embed page for Spotify-owned algorithmic/editorial
    playlists, which the Web API returns 404 for.

    Returns:
        tuple: (playlist_name, tracks_list)
    """
    try:
        playlist = sp.playlist(playlist_id, fields="name")
    except SpotifyException as e:
        if e.http_status == 404:
            print(
                "Playlist not available via Web API (likely a Spotify-generated "
                "playlist); using embed fallback..."
            )
            name, tracks = fetch_playlist_via_embed(sp, playlist_id)
            print(f"Fetched {len(tracks)} playlist songs.")
            return name, tracks
        raise
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
            flat = flatten_track_item(item)
            if flat is None:
                continue
            tracks.append(flat)
        offset += len(items)
        if offset % 200 == 0:
            print(f"Fetched {offset} playlist songs so far...")

    print(f"Fetched {len(tracks)} playlist songs.")
    return playlist_name, tracks
