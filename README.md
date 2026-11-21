# eska-spotify

Every day at 11:50 and 23:50, scans Radio Eska Dwa's playout log (yesterday and today) and adds new tracks to a Spotify playlist. Looked-up tracks are cached in `state.json`, so reruns are safe.

## Install (macOS)

1. `brew install uv`
2. Create a Spotify app at https://developer.spotify.com/dashboard with redirect URI `http://127.0.0.1:8080/callback`.
3. `./install.sh`. First run creates `.env` and `config.json` and stops. Fill in the client id, secret and `playlist_id`.
4. `./install.sh` again. It installs dependencies, opens the browser once for Spotify authorization, and loads the launchd job.

Dependencies and the Python version are handled by uv, so Homebrew Python upgrades do not break it.

## Use

- Run now: `./run.sh`, then `tail run.log`
- Dry run: `uv run eska_to_spotify.py --dry-run`
- Fallback Spotify app (used if the first fails): set the `_FALLBACK` values in `.env`, then `uv run authorize.py --fallback`
- Remove: `./uninstall.sh`

A failed scheduled run shows a macOS notification. Details are in `run.log`.
