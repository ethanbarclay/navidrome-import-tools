"""Subsonic API client for creating playlists in Navidrome.

Authenticates with the standard Subsonic salt+token scheme
(``t = md5(password + salt)``) and creates playlists via ``createPlaylist`` /
``updatePlaylist``. Large playlists are added in chunks so the request never
grows unbounded.
"""

import hashlib
import secrets

import requests

API_VERSION = "1.16.1"
CLIENT_NAME = "navidrome-import-tools"
# Max song ids per request. Liked-songs collections can be thousands of tracks;
# chunking keeps each POST body a sane size (and well under any URL limits).
ADD_CHUNK = 200


class NavidromeError(RuntimeError):
    """Raised when the Navidrome/Subsonic API returns an error or is unreachable."""


class NavidromeClient:
    def __init__(self, base_url, username, password, client_name=CLIENT_NAME):
        if not base_url or not username or not password:
            raise NavidromeError(
                "Navidrome URL, username and password are all required."
            )
        # Expect the server root (e.g. http://host:4533); tolerate a trailing
        # slash or an accidental /rest suffix.
        base = base_url.rstrip("/")
        if base.endswith("/rest"):
            base = base[: -len("/rest")]
        self.base_url = base
        self.username = username
        self._password = password
        self.client_name = client_name

    def _auth_params(self):
        salt = secrets.token_hex(8)
        token = hashlib.md5((self._password + salt).encode("utf-8")).hexdigest()
        return [
            ("u", self.username),
            ("t", token),
            ("s", salt),
            ("v", API_VERSION),
            ("c", self.client_name),
            ("f", "json"),
        ]

    def _post(self, endpoint, extra_params):
        url = f"{self.base_url}/rest/{endpoint}"
        data = self._auth_params() + list(extra_params)
        try:
            resp = requests.post(url, data=data, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as e:
            raise NavidromeError(f"Request to {endpoint} failed: {e}") from e

        try:
            payload = resp.json()["subsonic-response"]
        except (ValueError, KeyError) as e:
            raise NavidromeError(
                f"Unexpected response from {endpoint}: {e}"
            ) from e

        if payload.get("status") != "ok":
            err = payload.get("error", {})
            raise NavidromeError(
                f"Navidrome error {err.get('code', '?')}: "
                f"{err.get('message', 'unknown error')}"
            )
        return payload

    def ping(self):
        """Verify connectivity and credentials. Raises NavidromeError on failure."""
        self._post("ping", [])
        return True

    def create_playlist(self, name, song_ids, on_progress=None):
        """Create a playlist named ``name`` containing ``song_ids``.

        The playlist is created with the first chunk of songs; any remaining
        songs are appended via ``updatePlaylist`` in further chunks. ``on_progress``
        (if given) is called as ``on_progress(added, total)`` after each chunk.

        Returns the new playlist id.
        """
        if not song_ids:
            raise NavidromeError("No songs to add to the playlist.")

        total = len(song_ids)
        first, rest = song_ids[:ADD_CHUNK], song_ids[ADD_CHUNK:]

        params = [("name", name)] + [("songId", sid) for sid in first]
        payload = self._post("createPlaylist", params)
        playlist_id = payload.get("playlist", {}).get("id")
        if not playlist_id:
            raise NavidromeError("createPlaylist did not return a playlist id.")

        added = len(first)
        if on_progress:
            on_progress(added, total)

        for i in range(0, len(rest), ADD_CHUNK):
            batch = rest[i : i + ADD_CHUNK]
            params = [("playlistId", playlist_id)] + [
                ("songIdToAdd", sid) for sid in batch
            ]
            self._post("updatePlaylist", params)
            added += len(batch)
            if on_progress:
                on_progress(added, total)

        return playlist_id
