import spotipy
from spotipy.oauth2 import SpotifyOAuth
import csv
import json
import os
from dotenv import load_dotenv

from spotify_client import flatten_track_item

# Load environment variables from .env file
load_dotenv()

# Get credentials from environment variables
CLIENT_ID = os.getenv('CLIENT_ID')
CLIENT_SECRET = os.getenv('CLIENT_SECRET')
REDIRECT_URI = os.getenv('REDIRECT_URI')
SCOPE = "user-library-read"

sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    redirect_uri=REDIRECT_URI,
    scope=SCOPE
))

liked_tracks = []
limit = 50
offset = 0

print("Fetching user's liked songs...")
while True:
    results = sp.current_user_saved_tracks(limit=limit, offset=offset)
    items = results['items']
    if not items:
        break
    for item in items:
        flat = flatten_track_item(item)
        if flat is None:
            continue
        liked_tracks.append(flat)
    offset += len(items)
    print(f"Fetched {offset} liked songs so far...")

print(f"Fetched a total of {len(liked_tracks)} liked songs.")

# Save to JSON
with open('liked_tracks.json', 'w', encoding='utf-8') as f:
    json.dump(liked_tracks, f, ensure_ascii=False, indent=2)
print("Exported liked songs to liked_tracks.json")

# Save to CSV (optional)
if liked_tracks:
    keys = liked_tracks[0].keys()
    with open('liked_tracks.csv', 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, keys)
        writer.writeheader()
        writer.writerows(liked_tracks)
    print("Exported liked songs to liked_tracks.csv")
else:
    print("No tracks found to export.")
