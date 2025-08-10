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

from cogs.profile import ProfileCog
from core import db


class DummyResponse:
    def __init__(self):
        self.message = None
        self.kwargs = None

    async def send_message(self, message=None, **kwargs):
        self.message = message
        self.kwargs = kwargs


class DummyInteraction:
    def __init__(self, user_id=1):
        self.user = types.SimpleNamespace(id=user_id, display_name=f"User{user_id}")
        self.response = DummyResponse()


def test_username_command_updates_db(monkeypatch):
    intents = discord.Intents.none()
    bot = commands.Bot(command_prefix="!", intents=intents)
    cog = ProfileCog(bot)

    executed = {}

    async def dummy_execute(query, params=()):
        executed["query"] = query
        executed["params"] = params

    async def dummy_ensure_user(self, uid):
        pass

    monkeypatch.setattr(db, "execute", dummy_execute)
    monkeypatch.setattr(ProfileCog, "ensure_user", dummy_ensure_user)

    interaction = DummyInteraction()

    asyncio.run(ProfileCog.username.callback(cog, interaction, "Player1"))

    assert executed["params"] == ("Player1", "1")
    assert "Username set" in interaction.response.message
    asyncio.run(bot.close())


def test_profile_shows_username(monkeypatch):
    intents = discord.Intents.none()
    bot = commands.Bot(command_prefix="!", intents=intents)
    cog = ProfileCog(bot)

    async def dummy_fetch_one(query, params=()):
        return {"username": "PlayerX", "epic_sort_mode": "added"}

    async def dummy_fetch_all(query, params=()):
        return []

    async def dummy_ensure_user(self, uid):
        pass

    monkeypatch.setattr(db, "fetch_one", dummy_fetch_one)
    monkeypatch.setattr(db, "fetch_all", dummy_fetch_all)
    monkeypatch.setattr(ProfileCog, "ensure_user", dummy_ensure_user)

    interaction = DummyInteraction()
    asyncio.run(ProfileCog.profile.callback(cog, interaction, None))
    embed = interaction.response.kwargs["embed"]
    assert embed.title == "🎵 User1's Collection"
    assert embed.fields[0].name == "👤 Soundmap Username"
    assert embed.fields[0].value == "PlayerX"
    asyncio.run(bot.close())

