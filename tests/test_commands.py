import types
from pathlib import Path
import sys
import os
import asyncio

import discord
from discord.ext import commands

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DISCORD_TOKEN", "test-token")
os.environ.setdefault("SPOTIFY_CLIENT_ID", "cid")
os.environ.setdefault("SPOTIFY_CLIENT_SECRET", "csecret")

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
    @bot_module.bot.tree.command(name="dummy", description="Dummy command")
    async def dummy(interaction):
        pass

    interaction = DummyInteraction(bot_module.bot)
    asyncio.run(bot_module.list_commands.callback(interaction))

    assert "**Other**" in interaction.response.message
    assert "/dummy - Dummy command" in interaction.response.message
    assert interaction.response.kwargs.get("ephemeral") is True

    asyncio.run(bot_module.bot.close())
