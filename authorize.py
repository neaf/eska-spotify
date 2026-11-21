#!/usr/bin/env python3
"""One-time interactive OAuth setup. Opens a browser, asks you to approve
playlist access, then caches the token (incl. refresh token) in
.spotify_cache for eska_to_spotify.py to use unattended. Run again only if
.spotify_cache is deleted or access is revoked in your Spotify account.

Pass --fallback to authorize the SPOTIFY_CLIENT_ID_FALLBACK/SECRET_FALLBACK
app instead, into its own .spotify_cache_fallback."""
import argparse

from spotipy.oauth2 import SpotifyOAuth

from eska_to_spotify import CACHE_PATH, CACHE_PATH_FALLBACK, REDIRECT_URI, SCOPE, load_env


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fallback", action="store_true")
    args = parser.parse_args()

    env = load_env()
    if args.fallback:
        client_id = env.get("SPOTIFY_CLIENT_ID_FALLBACK")
        client_secret = env.get("SPOTIFY_CLIENT_SECRET_FALLBACK")
        cache_path = CACHE_PATH_FALLBACK
        missing = "SPOTIFY_CLIENT_ID_FALLBACK and SPOTIFY_CLIENT_SECRET_FALLBACK"
    else:
        client_id = env.get("SPOTIFY_CLIENT_ID")
        client_secret = env.get("SPOTIFY_CLIENT_SECRET")
        cache_path = CACHE_PATH
        missing = "SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET"
    if not client_id or not client_secret:
        raise SystemExit(f"Set {missing} in .env first.")

    auth_manager = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=REDIRECT_URI,
        scope=SCOPE,
        open_browser=True,
        cache_path=str(cache_path),
    )
    auth_manager.get_access_token(as_dict=False)
    print(f"Authorized. Token cached at {cache_path}.")


if __name__ == "__main__":
    main()
