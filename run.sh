#!/bin/bash
cd "$(dirname "$0")"
# launchd starts with a minimal PATH
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$PATH"
if ! uv run --quiet eska_to_spotify.py >> run.log 2>&1; then
    osascript -e 'display notification "Run failed, see run.log" with title "eska-spotify"'
    exit 1
fi
