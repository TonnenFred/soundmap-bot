import types
from pathlib import Path
import sys
import os
import asyncio
import importlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DISCORD_TOKEN", "test-token")
os.environ.setdefault("SPOTIFY_CLIENT_ID", "cid")
os.environ.setdefault("SPOTIFY_CLIENT_SECRET", "csecret")

import discord
from discord.ext import commands
from cogs.search import SearchCog
from cogs.profile import ProfileCog

import bot as bot_module


class DummyResponse:
    def __init__(self):
        self.message = None
        self.kwargs = None

    async def send_message(self, message=None, **kwargs):
        self.message = message
        self.kwargs = kwargs


class DummyInteraction:
    def __init__(self, client):
        self.client = client
        self.user = types.SimpleNamespace(id=1, display_name="User1")
        self.response = DummyResponse()


def test_commands_lists_registered_commands():
    importlib.reload(bot_module)

    @bot_module.bot.tree.command(name="dummy", description="Dummy command")
    async def dummy(interaction):
        pass

    interaction = DummyInteraction(bot_module.bot)
    asyncio.run(bot_module.list_commands.callback(interaction))

    assert "**Other**" in interaction.response.message
    assert "/dummy - Dummy command" in interaction.response.message
    assert interaction.response.kwargs.get("ephemeral") is True

    asyncio.run(bot_module.bot.close())


def test_commands_includes_searchuser_and_delusername():
    importlib.reload(bot_module)
    asyncio.run(bot_module.bot.add_cog(SearchCog(bot_module.bot)))
    asyncio.run(bot_module.bot.add_cog(ProfileCog(bot_module.bot)))

    interaction = DummyInteraction(bot_module.bot)
    asyncio.run(bot_module.list_commands.callback(interaction))

    assert "/searchuser - Find Discord users by in-game username" in interaction.response.message
    assert "/delusername - Remove your Soundmap in-game username" in interaction.response.message

    asyncio.run(bot_module.bot.close())
