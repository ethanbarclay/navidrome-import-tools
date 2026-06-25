#!/usr/bin/env python3
"""Offline tests for the Navidrome send-to-playlist feature."""

import hashlib
import json
import os
import sqlite3
import sys

import pytest

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
)

import navidrome_client
from navidrome_client import NavidromeClient, NavidromeError
from spoti_playlist_to_m3u import collect_navidrome_song_ids


# --------------------------------------------------------------------------- #
# collect_navidrome_song_ids: match against a synthetic Navidrome library DB
# --------------------------------------------------------------------------- #
def _make_db(path):
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE media_file (id, path, title, artist, album_artist, album, duration)"
    )
    conn.executemany(
        "INSERT INTO media_file VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            ("id1", "a/coordinate.mp3", "Coordinate", "Young Dolph", "Young Dolph", "Dum and Dummer 2", 198),
            ("id2", "b/die_trying.mp3", "Die Trying", "Key Glock", "Key Glock", "PRE5L", 153),
        ],
    )
    conn.commit()
    conn.close()


def test_collect_matches_and_misses(tmp_path):
    db = tmp_path / "navidrome.db"
    _make_db(str(db))

    tracks = [
        {"track_name": "Coordinate", "artist_name": "Young Dolph"},     # matches id1
        {"track_name": "Die Trying", "artist_name": "Key Glock"},       # matches id2
        {"track_name": "Not In Library", "artist_name": "Nobody"},      # miss
    ]
    spotify_json = tmp_path / "tracks.json"
    spotify_json.write_text(json.dumps(tracks), encoding="utf-8")

    result = collect_navidrome_song_ids(str(spotify_json), db_path=str(db))

    assert result["matched_ids"] == ["id1", "id2"]
    assert result["matched"] == 2
    assert result["total"] == 3
    assert len(result["failed"]) == 1
    assert result["failed"][0]["track_name"] == "Not In Library"


# --------------------------------------------------------------------------- #
# NavidromeClient: auth params + chunked create_playlist + error handling
# --------------------------------------------------------------------------- #
class _FakeResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


@pytest.fixture
def captured_posts(monkeypatch):
    calls = []

    def fake_post(url, data=None, timeout=None):
        calls.append({"url": url, "data": list(data)})
        if url.endswith("/rest/createPlaylist"):
            payload = {"subsonic-response": {"status": "ok", "playlist": {"id": "PL123"}}}
        else:  # ping, updatePlaylist
            payload = {"subsonic-response": {"status": "ok"}}
        return _FakeResp(payload)

    monkeypatch.setattr(navidrome_client.requests, "post", fake_post)
    return calls


def test_auth_params_use_salt_token(captured_posts):
    client = NavidromeClient("http://nd:4533", "ethan", "secret")
    client.ping()

    data = dict(captured_posts[0]["data"])
    assert data["u"] == "ethan"
    assert data["f"] == "json"
    # token must be md5(password + salt)
    assert data["t"] == hashlib.md5(("secret" + data["s"]).encode()).hexdigest()
    assert captured_posts[0]["url"] == "http://nd:4533/rest/ping"


def test_create_playlist_chunks(captured_posts):
    client = NavidromeClient("http://nd:4533/", "ethan", "secret")
    song_ids = [f"s{i}" for i in range(450)]  # 200 + 200 + 50 -> create + 2 updates
    progress = []

    pid = client.create_playlist("My List", song_ids, on_progress=lambda a, t: progress.append((a, t)))

    assert pid == "PL123"
    endpoints = [c["url"].rsplit("/", 1)[-1] for c in captured_posts]
    assert endpoints == ["createPlaylist", "updatePlaylist", "updatePlaylist"]

    # first request: name + 200 songId
    first = captured_posts[0]["data"]
    assert ("name", "My List") in first
    assert sum(1 for k, _ in first if k == "songId") == 200
    # remaining added via songIdToAdd
    assert sum(1 for k, _ in captured_posts[1]["data"] if k == "songIdToAdd") == 200
    assert sum(1 for k, _ in captured_posts[2]["data"] if k == "songIdToAdd") == 50
    assert progress == [(200, 450), (400, 450), (450, 450)]


def test_create_playlist_empty_raises(captured_posts):
    client = NavidromeClient("http://nd:4533", "ethan", "secret")
    with pytest.raises(NavidromeError):
        client.create_playlist("Empty", [])


def test_subsonic_error_raises(monkeypatch):
    def fake_post(url, data=None, timeout=None):
        return _FakeResp(
            {"subsonic-response": {"status": "failed", "error": {"code": 40, "message": "Wrong username or password"}}}
        )

    monkeypatch.setattr(navidrome_client.requests, "post", fake_post)
    client = NavidromeClient("http://nd:4533", "ethan", "bad")
    with pytest.raises(NavidromeError) as exc:
        client.ping()
    assert "Wrong username or password" in str(exc.value)


def test_base_url_strips_rest_suffix():
    client = NavidromeClient("http://nd:4533/rest/", "ethan", "secret")
    assert client.base_url == "http://nd:4533"


def test_missing_credentials_raises():
    with pytest.raises(NavidromeError):
        NavidromeClient("http://nd:4533", "", "secret")
