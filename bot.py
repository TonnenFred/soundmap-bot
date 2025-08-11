"""Entry point for the Soundmap Discord bot.

This script configures the Discord bot client, loads command cogs and
initialises the database on startup. It reads environment variables via
core.config and synchronises slash commands either globally or for a
development guild when configured. The bot uses only slash commands; the
traditional prefix commands are disabled.
"""

import asyncio
import logging
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional

import discord
from discord.ext import commands

# When running as a script, adjust sys.path so that the 'core' and 'cogs'
# packages can be imported without relative import errors. This allows
# executing `python bot.py` directly from within the soundmap-bot directory.
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core import config as cfg  # type: ignore
from core import db as db_module  # type: ignore
from cogs.profile import ProfileCog  # type: ignore
from cogs.search import SearchCog  # type: ignore

logging.basicConfig(level=logging.INFO)

# --- Health check HTTP server -------------------------------------------------
# Koyeb performs health checks by connecting to the service's exposed port. Since
# the Discord bot itself does not provide an HTTP interface, deployments will
# otherwise remain in the "Starting" state forever. To satisfy the health
# check, we spin up a very simple HTTP server that responds with "OK" to
# any request. The server listens on the port defined by the PORT
# environment variable (default 8000) and binds to 0.0.0.0 so Koyeb can
# reach it from outside the container.
class _HealthHandler(BaseHTTPRequestHandler):
    """Simple request handler that always returns 200 OK."""

    def do_GET(self) -> None:  # type: ignore[override]
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    # Suppress logging to stdout
    def log_message(self, format: str, *args: object) -> None:  # type: ignore[override]
        return


def _start_health_server() -> None:
    """Start the health check HTTP server in a background thread."""
    # Determine port from environment; fall back to 8000 if not set
    try:
        port = int(os.environ.get("PORT", "8000"))
    except ValueError:
        port = 8000
    server = HTTPServer(("0.0.0.0", port), _HealthHandler)
    # Run server in a daemon thread so it doesn't block program exit
    thread = threading.Thread(target=server.serve_forever, name="health-server", daemon=True)
    thread.start()

# Configure intents and member cache so that Spotify activities are available
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.presences = True  # required for wishcurrent/favartistcurrent

# Cache members so their presence/activities are available
cache_flags = discord.MemberCacheFlags.all()

bot = commands.Bot(
    command_prefix="!", intents=intents, member_cache_flags=cache_flags
)


@bot.tree.command(name="commands", description="List all available commands")
async def list_commands(interaction: discord.Interaction) -> None:
    """Send a grouped list of all registered slash commands."""
    tree_cmds = {c.name: c for c in interaction.client.tree.get_commands()}

    groups = {
        "General": ["commands"],
        "Profile": ["profile", "username"],
        "Collection Management": [
            "addepic",
            "delepic",
            "addwish",
            "delwish",
            "addartist",
            "delartist",
            "setbadge",
            "wishcurrent",
            "favartistcurrent",
        ],
        "Sorting": ["sortepics", "sortwishes", "sortartists"],
        "Search & Trading": ["searchuser", "findcollector", "findowners", "tradehelp"],
    }

    lines: list[str] = []
    used: set[str] = set()
    for title, names in groups.items():
        entries = []
        for name in names:
            cmd = tree_cmds.get(name)
            if cmd:
                entries.append(f"/{cmd.name} - {cmd.description}")
                used.add(name)
        if entries:
            lines.append(f"**{title}**")
            lines.extend(entries)
            lines.append("")

    leftovers = [c for n, c in tree_cmds.items() if n not in used]
    if leftovers:
        lines.append("**Other**")
        for cmd in sorted(leftovers, key=lambda c: c.name):
            lines.append(f"/{cmd.name} - {cmd.description}")

    await interaction.response.send_message("\n".join(lines).strip(), ephemeral=True)


@bot.event
async def on_ready():
    # Ensure guild member caches are populated so activities are available
    for g in bot.guilds:
        await g.chunk()
    # Initialise the database. This runs migrations if necessary.
    await db_module.init_db()
    logging.info("Database path: %s", db_module.DB_PATH)
    # Load cogs if not already loaded
    # Load only once to avoid duplication on reconnect
    if not bot.get_cog("ProfileCog"):
        await bot.add_cog(ProfileCog(bot))
    if not bot.get_cog("SearchCog"):
        await bot.add_cog(SearchCog(bot))
    # Sync slash commands. Use dev guild if specified for faster sync.
    try:
        if cfg.GUILD_ID_DEV:
            guild_obj = discord.Object(id=int(cfg.GUILD_ID_DEV))
            await bot.tree.sync(guild=guild_obj)
            logging.info("Synced commands to dev guild %s", cfg.GUILD_ID_DEV)
        else:
            await bot.tree.sync()
            logging.info("Synced commands globally")
    except Exception as e:
        logging.exception("Failed to sync commands: %s", e)
    logging.info("Bot is ready. Logged in as %s", bot.user)


def main() -> None:
    # Start a simple HTTP server for Koyeb health checks. Without this,
    # the deployment would remain in the "Starting" state indefinitely.
    _start_health_server()
    # Run the Discord bot
    bot.run(cfg.DISCORD_TOKEN)


if __name__ == "__main__":
    main()
