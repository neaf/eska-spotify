#!/usr/bin/env python3
"""Scan Radio Eska Dwa's "co bylo grane" playout log for yesterday and today
and append new tracks to a Spotify playlist. Safe to run repeatedly (and
several times a day): tracks already looked up (found or not found on
Spotify) are cached in state.json and skipped. Any Spotify API error (e.g.
rate limiting) aborts the run without caching a false "not found" for
whatever hadn't been looked up yet.

Usage:
    eska_to_spotify.py [--dry-run]

--dry-run still performs (and caches) the Spotify lookups, only skips the
actual playlist_add_items call — so it's safe to convert into a real run
right after without redoing the searches.
"""
import argparse
import datetime
import json
import pathlib
import sys
import time

import requests
import spotipy
from spotipy.oauth2 import SpotifyOAuth

BASE_DIR = pathlib.Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
STATE_PATH = BASE_DIR / "state.json"
ENV_PATH = BASE_DIR / ".env"
CACHE_PATH = BASE_DIR / ".spotify_cache"
CACHE_PATH_FALLBACK = BASE_DIR / ".spotify_cache_fallback"
REDIRECT_URI = "http://127.0.0.1:8080/callback"
SCOPE = "playlist-modify-public playlist-modify-private"


class FallbackSpotify:
    """Wraps a primary + optional fallback spotipy.Spotify client. Any
    exception from a call on the active client switches permanently to the
    next one (for the rest of this process) and retries that one call; only
    raises once every client has been tried."""

    def __init__(self, profiles):
        self.profiles = profiles  # list of (client_id, client_secret, cache_path)
        self.index = 0
        self.client = self._build(self.index)

    def _build(self, index):
        client_id, client_secret, cache_path = self.profiles[index]
        auth_manager = SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=REDIRECT_URI,
            scope=SCOPE,
            open_browser=False,
            cache_path=str(cache_path),
        )
        # retries=0/status_retries=0: spotipy's default retry policy treats 429
        # as retryable and honors the server's Retry-After header by sleeping
        # for that exact duration *inside* the request call — observed once as
        # an ~24h synchronous hang. Fail fast instead so we can switch clients.
        return spotipy.Spotify(auth_manager=auth_manager, retries=0, status_retries=0)

    def _call(self, method, *args, **kwargs):
        while True:
            try:
                return getattr(self.client, method)(*args, **kwargs)
            except Exception as exc:
                if self.index + 1 < len(self.profiles):
                    self.index += 1
                    print(f"  ! Spotify app failed ({exc}); switching to fallback app", file=sys.stderr)
                    self.client = self._build(self.index)
                    continue
                raise

    def search(self, **kwargs):
        return self._call("search", **kwargs)

    def playlist_items(self, *args, **kwargs):
        return self._call("playlist_items", *args, **kwargs)

    def playlist_add_items(self, *args, **kwargs):
        return self._call("playlist_add_items", *args, **kwargs)


def load_env():
    env = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip()
    return env


def load_state():
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {"added_media_ids": {}}


def save_state(state):
    STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def fetch_hour(station_id, station_host, date_str, hour):
    url = f"https://{station_host}/api/mobile/station/{station_id}/was_played/"
    resp = requests.get(
        url,
        params={"date": date_str, "hour": hour},
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def dates_to_scan(today):
    yield today - datetime.timedelta(days=1)
    yield today


def search_track(sp, artist, title):
    """Returns a track URI, or None if genuinely not found. Raises on API
    errors (rate limit, network, etc.) — the caller must NOT cache those as
    not-found, or a Spotify outage would permanently poison state.json."""
    for query in (f"track:{title} artist:{artist}", f"{artist} {title}"):
        result = sp.search(q=query, type="track", limit=1)
        time.sleep(0.1)
        items = result.get("tracks", {}).get("items", [])
        if items:
            return items[0]["uri"]
    return None


def existing_playlist_uris(sp, playlist_id):
    uris = set()
    offset = 0
    while True:
        page = sp.playlist_items(
            playlist_id, fields="items.track.uri,next", limit=100, offset=offset
        )
        items = page.get("items", [])
        if not items:
            break
        for item in items:
            track = item.get("track")
            if track and track.get("uri"):
                uris.add(track["uri"])
        if not page.get("next"):
            break
        offset += 100
    return uris


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    env = load_env()
    client_id = env.get("SPOTIFY_CLIENT_ID")
    client_secret = env.get("SPOTIFY_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise SystemExit("Missing SPOTIFY_CLIENT_ID/SPOTIFY_CLIENT_SECRET in .env")
    if not CACHE_PATH.exists():
        raise SystemExit("No .spotify_cache found — run authorize.py once first.")

    profiles = [(client_id, client_secret, CACHE_PATH)]
    fallback_id = env.get("SPOTIFY_CLIENT_ID_FALLBACK")
    fallback_secret = env.get("SPOTIFY_CLIENT_SECRET_FALLBACK")
    if fallback_id and fallback_secret:
        if CACHE_PATH_FALLBACK.exists():
            profiles.append((fallback_id, fallback_secret, CACHE_PATH_FALLBACK))
        else:
            print("Fallback credentials set but not authorized — run authorize.py --fallback once. Skipping fallback.", file=sys.stderr)

    config = json.loads(CONFIG_PATH.read_text())
    state = load_state()
    sp = FallbackSpotify(profiles)

    today = datetime.date.today()
    new_uris = []
    aborted = False

    try:
        for date in dates_to_scan(today):
            max_hour = datetime.datetime.now().hour if date == today else 23
            print(f"Scanning {date.isoformat()} (hours 0-{max_hour})")
            for hour in range(0, max_hour + 1):
                try:
                    items = fetch_hour(config["station_id"], config["station_host"], date.isoformat(), hour)
                except requests.HTTPError as exc:
                    print(f"  ! hour {hour}: {exc}", file=sys.stderr)
                    continue
                for item in items:
                    media_id = str(item["media_id"])
                    if media_id in state["added_media_ids"]:
                        continue
                    artist = " & ".join(a["name"] for a in item.get("artists", [])) or "Unknown"
                    title = item["name"]
                    uri = search_track(sp, artist, title)
                    state["added_media_ids"][media_id] = uri
                    if uri:
                        print(f"  + {artist} - {title}")
                        new_uris.append(uri)
                    else:
                        print(f"  ? not found on Spotify: {artist} - {title}")
    except Exception as exc:
        print(f"Spotify API error, stopping early (progress so far is still saved): {exc}", file=sys.stderr)
        aborted = True

    unique_new = list(dict.fromkeys(new_uris))
    if unique_new and not args.dry_run and not aborted:
        existing = existing_playlist_uris(sp, config["playlist_id"])
        to_add = [uri for uri in unique_new if uri not in existing]
        for i in range(0, len(to_add), 100):
            sp.playlist_add_items(config["playlist_id"], to_add[i : i + 100])
        print(f"Added {len(to_add)} new track(s) to playlist.")
    elif unique_new:
        print(f"[dry-run or aborted] would add {len(unique_new)} track(s).")

    save_state(state)
    if aborted:
        sys.exit(1)


if __name__ == "__main__":
    main()
