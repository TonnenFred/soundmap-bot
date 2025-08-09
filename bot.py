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

# Configure intents: we only need guilds and presences to read Spotify activity
intents = discord.Intents.default()
intents.guilds = True
intents.presences = True  # required for wishcurrent/favartistcurrent

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    # Initialise the database. This runs migrations if necessary.
    await db_module.init_db()
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
    # Run the bot
    bot.run(cfg.DISCORD_TOKEN)


if __name__ == "__main__":
    main()
