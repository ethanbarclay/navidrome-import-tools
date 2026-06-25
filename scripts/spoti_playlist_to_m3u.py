#!/usr/bin/env python3
import json
import os
import sqlite3
from collections import defaultdict

from dotenv import load_dotenv

load_dotenv()

# Path to your Navidrome SQLite database file
DB_PATH = os.getenv("DATABASE_PATH", "navidrome.db")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", ".")


class NavidromeLibrary:
    """In-memory representation of Navidrome library for fast searching."""

    def __init__(self, conn):
        print("Loading library into memory...", flush=True)
        cursor = conn.execute("""
            SELECT id, path, title, artist, album_artist, album, duration
            FROM media_file
        """)

        self.tracks = []
        self.title_index = defaultdict(list)
        self.artist_index = defaultdict(list)

        for row in cursor:
            track = {
                "id": row[0],
                "path": row[1],
                "title": row[2],
                "artist": row[3],
                "album_artist": row[4],
                "album": row[5],
                "duration": row[6],
                "title_lower": row[2].lower() if row[2] else "",
                "artist_lower": row[3].lower() if row[3] else "",
                "album_artist_lower": row[4].lower() if row[4] else "",
            }
            self.tracks.append(track)

            # Index by normalized title for fast lookup
            if track["title_lower"]:
                self.title_index[track["title_lower"]].append(track)

            # Index by artist tokens
            if track["artist_lower"]:
                for token in track["artist_lower"].split("•"):
                    token = token.strip()
                    if token:
                        self.artist_index[token].append(track)

        print(f"Loaded {len(self.tracks)} tracks into memory", flush=True)

    def search_track(self, track_name, artist_name):
        """Fast in-memory search for track."""
        track_lower = track_name.lower()
        artist_lower = artist_name.lower()
        primary_artist = artist_name.split(",")[0].strip().lower()
        core_track = track_name.split("(")[0].strip().lower()

        # Strategy 1: Exact title match with artist verification
        if track_lower in self.title_index:
            for track in self.title_index[track_lower]:
                if self._artist_matches(track, artist_lower, primary_artist):
                    return track

        # Strategy 2: Core title match (without feat. parts)
        if core_track != track_lower and core_track in self.title_index:
            for track in self.title_index[core_track]:
                if self._artist_matches(track, artist_lower, primary_artist):
                    return track

        # Strategy 3: Fuzzy title match with artist check
        for track in self.tracks:
            if (
                track_lower in track["title_lower"]
                or core_track in track["title_lower"]
            ):
                if self._artist_matches(track, artist_lower, primary_artist):
                    return track

        # Strategy 4: Artist-first search (check artist index then verify title)
        if primary_artist in self.artist_index:
            for track in self.artist_index[primary_artist]:
                if (
                    track_lower in track["title_lower"]
                    or core_track in track["title_lower"]
                ):
                    return track

        return None

    def _artist_matches(self, track, artist_lower, primary_artist):
        """Check if track artist matches the search artist."""
        return (
            artist_lower in track["artist_lower"]
            or artist_lower in track["album_artist_lower"]
            or primary_artist in track["artist_lower"]
            or primary_artist in track["album_artist_lower"]
        )


def navidrome_search_track_db(conn, track_name, artist_name):
    """Search Navidrome database for track by name and artist using SQL LIKE queries."""

    # Normalize artist names - handle different separators
    # Spotify uses "," but Navidrome uses "•"
    primary_artist = artist_name.split(",")[0].strip()  # Get first artist

    # Create multiple artist patterns to try
    artist_patterns = [
        f"%{artist_name.lower()}%",  # Original format
        f"%{primary_artist.lower()}%",  # Just primary artist
        f"%{artist_name.replace(',', ' •').lower()}%",  # Replace comma with bullet
        f"%{artist_name.replace(', ', ' • ').lower()}%",  # Replace comma+space with bullet
    ]

    # Create search patterns for fuzzy matching
    track_pattern = f"%{track_name.lower()}%"

    # Try exact title match first with multiple artist patterns
    for artist_pattern in artist_patterns:
        cursor = conn.execute(
            """
            SELECT id, path, title, artist, album, duration
            FROM media_file
            WHERE LOWER(title) = LOWER(?)
            AND (LOWER(artist) LIKE ? OR LOWER(album_artist) LIKE ?)
            LIMIT 1
        """,
            (track_name, artist_pattern, artist_pattern),
        )

        result = cursor.fetchone()
        if result:
            return {
                "id": result[0],
                "path": result[1],
                "title": result[2],
                "artist": result[3],
                "album": result[4],
                "duration": result[5],
            }

    # Try partial title match (handles "feat." differences)
    core_track_name = track_name.split("(")[0].strip()  # Remove "(feat. ...)" parts
    core_pattern = f"%{core_track_name.lower()}%"

    for artist_pattern in artist_patterns:
        cursor = conn.execute(
            """
            SELECT id, path, title, artist, album, duration
            FROM media_file
            WHERE (LOWER(title) LIKE ? OR LOWER(title) LIKE ?)
            AND (LOWER(artist) LIKE ? OR LOWER(album_artist) LIKE ?)
            LIMIT 1
        """,
            (track_pattern, core_pattern, artist_pattern, artist_pattern),
        )

        result = cursor.fetchone()
        if result:
            return {
                "id": result[0],
                "path": result[1],
                "title": result[2],
                "artist": result[3],
                "album": result[4],
                "duration": result[5],
            }

    # Fallback: search by primary artist only in full text
    query_text = f"{track_name} {primary_artist}".lower()
    cursor = conn.execute(
        """
        SELECT id, path, title, artist, album, duration
        FROM media_file
        WHERE LOWER(full_text) LIKE ?
        LIMIT 1
    """,
        (f"%{query_text}%",),
    )

    result = cursor.fetchone()
    if result:
        return {
            "id": result[0],
            "path": result[1],
            "title": result[2],
            "artist": result[3],
            "album": result[4],
            "duration": result[5],
        }

    return None


def generate_m3u_from_db(
    playlist_name,
    spotify_playlist_json_path,
    output_path,
    test_mode=False,
    use_memory=True,
):
    """Generate M3U playlist from Spotify JSON using direct database access."""

    with open(spotify_playlist_json_path, "r", encoding="utf-8") as f:
        spotify_tracks = json.load(f)

    if test_mode:
        # Test with first 10 tracks only
        spotify_tracks = spotify_tracks[:10]
        print(f"Processing {len(spotify_tracks)} tracks (TEST MODE - first 10 only)...")
    else:
        print(f"Processing {len(spotify_tracks)} tracks...")

    lines = ["#EXTM3U", "#PLAYLIST:" + playlist_name]
    total_tracks = len(spotify_tracks)
    matched_count = 0
    processed_count = 0
    failed_matches = []

    # Simple progress indicator
    print(f"Processing tracks...", flush=True)

    conn = None
    try:
        # Open database connection
        print(f"Opening database: {DB_PATH}", flush=True)
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro&immutable=1", uri=True)
        print("Database connected successfully", flush=True)

        # Load library into memory for fast searching
        library = None
        if use_memory:
            library = NavidromeLibrary(conn)
        else:
            # Start transaction for better performance with direct queries
            conn.execute("BEGIN TRANSACTION")

        for i, track in enumerate(spotify_tracks):
            track_name = track["track_name"]
            artist_name = track["artist_name"]
            duration_sec = int(track["duration_ms"] / 1000)

            # Use in-memory search or optimized database query
            if library:
                song = library.search_track(track_name, artist_name)
            else:
                song = navidrome_search_track_db(conn, track_name, artist_name)

            if song:
                file_path = song["path"]
                if file_path:
                    # Prepend /music/ to the file path
                    full_path = f"/music/{file_path}"
                    # Build EXTINF line
                    extinf = f"#EXTINF:{duration_sec},{artist_name} - {track_name}"
                    lines.append(extinf)
                    lines.append(full_path)
                    matched_count += 1
                else:
                    failed_matches.append(
                        {
                            "track_name": track_name,
                            "artist_name": artist_name,
                            "reason": "No file path found",
                        }
                    )
            else:
                failed_matches.append(
                    {
                        "track_name": track_name,
                        "artist_name": artist_name,
                        "reason": "No match found in database",
                    }
                )

            processed_count += 1

            # Simple progress indicator - print every few tracks
            if processed_count % 5 == 0 or processed_count == total_tracks:
                percent = int((processed_count / total_tracks) * 100)
                print(
                    f"\r{percent}% ({processed_count}/{total_tracks}) - Matched: {matched_count}",
                    flush=True,
                )

        if not use_memory:
            conn.execute("COMMIT")

    except sqlite3.Error as e:
        print(f"\nSQLite error: {e}", flush=True)
        raise RuntimeError(f"Database error: {e}")
    except Exception as e:
        print(f"\n!!! Unexpected error: {e}", flush=True)
        import traceback

        traceback.print_exc()
        raise RuntimeError(f"Failed to process tracks: {e}")
    finally:
        if conn:
            conn.close()

    print(
        f"\nCompleted! Matched {matched_count} out of {total_tracks} tracks.",
        flush=True,
    )
    print(f"Success rate: {(matched_count / total_tracks) * 100:.1f}%", flush=True)

    # Write M3U file
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"M3U playlist written to: {output_path}")

    # Write failed matches to JSON file for analysis
    if failed_matches:
        try:
            print(f"\nWriting {len(failed_matches)} failed matches...", flush=True)

            base_name = os.path.splitext(os.path.basename(output_path))[0]
            failed_file = os.path.join(OUTPUT_DIR, f"{base_name}_failed_matches.json")

            print(f"Failed matches file path: {failed_file}", flush=True)

            with open(failed_file, "w", encoding="utf-8") as f:
                json.dump(failed_matches, f, indent=2, ensure_ascii=False)
            print(f"Failed matches written successfully to: {failed_file}", flush=True)
        except Exception as e:
            print(f"Error writing failed matches file: {e}", flush=True)
            import traceback

            traceback.print_exc()


def collect_navidrome_song_ids(spotify_playlist_json_path, db_path=DB_PATH):
    """Match Spotify tracks against the Navidrome library and collect song ids.

    Reuses the same in-memory matcher as M3U generation, but returns the
    matched ``media_file.id`` values (which are also the Subsonic song ids)
    instead of writing an M3U.

    Returns:
        dict: {"matched_ids": [...], "matched": int, "total": int,
               "failed": [{"track_name", "artist_name"}, ...]}
    """
    with open(spotify_playlist_json_path, "r", encoding="utf-8") as f:
        spotify_tracks = json.load(f)

    total = len(spotify_tracks)
    matched_ids = []
    failed = []

    conn = sqlite3.connect(f"file:{db_path}?mode=ro&immutable=1", uri=True)
    try:
        library = NavidromeLibrary(conn)
        for track in spotify_tracks:
            song = library.search_track(track["track_name"], track["artist_name"])
            if song and song.get("id"):
                matched_ids.append(song["id"])
            else:
                failed.append(
                    {
                        "track_name": track["track_name"],
                        "artist_name": track["artist_name"],
                    }
                )
    finally:
        conn.close()

    return {
        "matched_ids": matched_ids,
        "matched": len(matched_ids),
        "total": total,
        "failed": failed,
    }


def list_songs(conn, limit=5):
    """Fetch and print song info from the database."""
    cursor = conn.execute(
        f"SELECT id, path, title, artist, album, duration FROM media_file LIMIT {limit}"
    )
    rows = cursor.fetchall()

    if not rows:
        print("No songs found in the database.")
        return

    print(f"Sample songs from database:\n")
    for row in rows:
        song = {
            "id": row[0],
            "path": row[1],
            "title": row[2],
            "artist": row[3],
            "album": row[4],
            "duration": row[5],
        }
        print(json.dumps(song, indent=2))
        print("-" * 40)


def main():
    import argparse
    import sys
    import tempfile

    parser = argparse.ArgumentParser(
        description="Generate M3U playlists from Spotify data using a Navidrome database."
    )
    subparsers = parser.add_subparsers(dest="command")

    # list command
    subparsers.add_parser("list", help="List sample songs from Navidrome database")

    # generate command
    gen_parser = subparsers.add_parser("generate", help="Generate an M3U playlist")
    source_group = gen_parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--spotify",
        metavar="URL_OR_ID",
        help="Fetch tracks directly from a Spotify playlist URL or ID",
    )
    source_group.add_argument(
        "--json",
        metavar="FILE",
        help="Use a pre-fetched JSON file of playlist tracks",
    )
    gen_parser.add_argument(
        "playlist_name",
        nargs="?",
        default=None,
        help="Playlist name (required with --json, auto-fetched with --spotify)",
    )
    gen_parser.add_argument("output", help="Output M3U file path")
    gen_parser.add_argument(
        "--no-memory",
        action="store_true",
        help="Use direct database queries instead of in-memory search",
    )

    # send-navidrome command
    nd_parser = subparsers.add_parser(
        "send-navidrome",
        help="Create a playlist in Navidrome (Subsonic API) from Spotify data",
    )
    nd_source = nd_parser.add_mutually_exclusive_group(required=True)
    nd_source.add_argument(
        "--spotify",
        metavar="URL_OR_ID",
        help="Fetch tracks directly from a Spotify playlist URL or ID",
    )
    nd_source.add_argument(
        "--json",
        metavar="FILE",
        help="Use a pre-fetched JSON file of playlist tracks",
    )
    nd_parser.add_argument(
        "--name",
        default=None,
        help="Playlist name (required with --json, auto-fetched with --spotify)",
    )
    nd_parser.add_argument("--navidrome-url", default=os.getenv("NAVIDROME_URL", ""))
    nd_parser.add_argument("--navidrome-user", default=os.getenv("NAVIDROME_USER", ""))
    nd_parser.add_argument(
        "--navidrome-password", default=os.getenv("NAVIDROME_PASSWORD", "")
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    if args.command == "list":
        conn = None
        try:
            conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro&immutable=1", uri=True)
            list_songs(conn)
        except sqlite3.Error as e:
            print(f"SQLite error: {e}")
        finally:
            if conn:
                conn.close()

    elif args.command == "generate":
        use_memory = not args.no_memory
        print(f"Using {'in-memory' if use_memory else 'direct database'} search mode")

        if args.spotify:
            # Fetch tracks from Spotify API
            from spotify_client import (
                extract_playlist_id,
                fetch_playlist_tracks,
                get_spotify_client,
            )

            sp = get_spotify_client()
            playlist_id = extract_playlist_id(args.spotify)
            playlist_name, tracks = fetch_playlist_tracks(sp, playlist_id)

            # Use CLI argument if provided, otherwise use fetched name
            if args.playlist_name:
                playlist_name = args.playlist_name

            # Write tracks to a temp JSON file for generate_m3u_from_db
            tmp = tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False, encoding="utf-8"
            )
            json.dump(tracks, tmp, ensure_ascii=False, indent=2)
            tmp.close()
            spotify_json = tmp.name
        else:
            # Use pre-fetched JSON file
            spotify_json = args.json
            playlist_name = args.playlist_name
            if not playlist_name:
                print("Error: playlist_name is required when using --json")
                sys.exit(1)
            if not os.path.exists(spotify_json):
                print(f"Error: Spotify playlist JSON file not found: {spotify_json}")
                return

        generate_m3u_from_db(
            playlist_name,
            spotify_json,
            args.output,
            test_mode=False,
            use_memory=use_memory,
        )

        # Clean up temp file if we created one
        if args.spotify:
            os.unlink(spotify_json)

    elif args.command == "send-navidrome":
        from navidrome_client import NavidromeClient, NavidromeError

        # Resolve tracks JSON + playlist name (same source handling as generate)
        if args.spotify:
            from spotify_client import (
                extract_playlist_id,
                fetch_playlist_tracks,
                get_spotify_client,
            )

            sp = get_spotify_client()
            playlist_id = extract_playlist_id(args.spotify)
            playlist_name, tracks = fetch_playlist_tracks(sp, playlist_id)
            if args.name:
                playlist_name = args.name

            tmp = tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False, encoding="utf-8"
            )
            json.dump(tracks, tmp, ensure_ascii=False, indent=2)
            tmp.close()
            spotify_json = tmp.name
        else:
            spotify_json = args.json
            playlist_name = args.name
            if not playlist_name:
                print("Error: --name is required when using --json")
                sys.exit(1)
            if not os.path.exists(spotify_json):
                print(f"Error: Spotify playlist JSON file not found: {spotify_json}")
                return

        try:
            result = collect_navidrome_song_ids(spotify_json)
            if not result["matched_ids"]:
                print(
                    f"No matches: none of the {result['total']} tracks were found "
                    "in your Navidrome library."
                )
                return

            print(
                f"Matched {result['matched']} of {result['total']} tracks. "
                "Creating playlist..."
            )
            client = NavidromeClient(
                args.navidrome_url, args.navidrome_user, args.navidrome_password
            )
            playlist_id = client.create_playlist(
                playlist_name,
                result["matched_ids"],
                on_progress=lambda a, t: print(f"  added {a}/{t}", flush=True),
            )

            skipped = result["total"] - result["matched"]
            summary = (
                f"Created playlist '{playlist_name}' (id {playlist_id}): "
                f"added {result['matched']} of {result['total']} tracks"
            )
            summary += f", {skipped} not in library." if skipped else "."
            print(summary)
        except NavidromeError as e:
            print(f"Navidrome error: {e}")
            sys.exit(1)
        finally:
            if args.spotify and os.path.exists(spotify_json):
                os.unlink(spotify_json)


if __name__ == "__main__":
    main()
