#!/bin/bash
# Sets up a new machine: dependencies, config, Spotify authorization, launchd job.
set -euo pipefail
cd "$(dirname "$0")"
DIR="$PWD"
LABEL="com.tomaszwerbicki.eska-spotify"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

command -v uv >/dev/null || { echo "uv not found. Install it: brew install uv"; exit 1; }

[ -f .env ] || { cp .env.example .env; chmod 600 .env; }
[ -f config.json ] || cp config.example.json config.json
if ! grep -qE '^SPOTIFY_CLIENT_ID=.+' .env || grep -q YOUR_PLAYLIST_ID config.json; then
    echo "Fill in .env (Spotify client id and secret) and config.json (playlist_id), then rerun ./install.sh"
    exit 1
fi

uv sync --quiet
[ -f .spotify_cache ] || uv run authorize.py

mkdir -p "$HOME/Library/LaunchAgents"
sed "s|__PROJECT_DIR__|$DIR|g" com.eska-spotify.plist.template > "$PLIST"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Installed. Runs at 11:50 and 23:50. Test now: ./run.sh && tail run.log"
