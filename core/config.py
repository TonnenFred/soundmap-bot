"""Configuration loader for the Soundmap Discord bot.

This module wraps reading of environment variables using python-dotenv to
facilitate local development while also working seamlessly on hosted
environments. The following environment variables are recognised:

  DISCORD_TOKEN:       Bot token for Discord authentication.
  SPOTIFY_CLIENT_ID:   Spotify client ID for API access.
  SPOTIFY_CLIENT_SECRET: Spotify client secret for API access.
  DATABASE_PATH:       Filesystem path where the SQLite database should be stored.
                       If not provided, defaults to 'bot.db' in the current working directory.
  GUILD_ID_DEV:        Optional guild ID for rapid slash command registration during
                       development. If provided, commands are synced only to this
                       guild rather than globally.
"""

import os
from dotenv import load_dotenv

# Load .env file if present. This call is idempotent and has no effect if
# called multiple times. It will not override existing environment variables.
load_dotenv()

DISCORD_TOKEN: str | None = os.environ.get("DISCORD_TOKEN")
SPOTIFY_CLIENT_ID: str | None = os.environ.get("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET: str | None = os.environ.get("SPOTIFY_CLIENT_SECRET")

# Default database path. On Koyeb, this should be overridden via environment
# variable to a persistent volume (e.g. '/data/bot.db').
DATABASE_PATH: str = os.environ.get("DATABASE_PATH", "bot.db")

# Guild ID for development-only command sync. If provided, slash commands will
# be registered exclusively on this guild, bypassing the hour-long global
# propagation delay. Leave unset or set to an empty string to perform global
# registration.
GUILD_ID_DEV: str | None = os.environ.get("GUILD_ID_DEV") or None

assert DISCORD_TOKEN, "DISCORD_TOKEN must be set in environment"
assert SPOTIFY_CLIENT_ID, "SPOTIFY_CLIENT_ID must be set in environment"
assert SPOTIFY_CLIENT_SECRET, "SPOTIFY_CLIENT_SECRET must be set in environment"
