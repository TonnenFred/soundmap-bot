import types
from pathlib import Path
import sys
import os

import asyncio
import pytest
import discord
from discord.ext import commands

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DISCORD_TOKEN", "test-token")
os.environ.setdefault("SPOTIFY_CLIENT_ID", "cid")
os.environ.setdefault("SPOTIFY_CLIENT_SECRET", "csecret")

from cogs.profile import ProfileCog
from core import spotify, db


class DummyResponse:
    def __init__(self):
        self.message = None
        self.kwargs = None

    async def send_message(self, message, **kwargs):
        self.message = message
        self.kwargs = kwargs


class DummyInteraction:
    def __init__(self, user_id=1):
        self.user = types.SimpleNamespace(id=user_id)
        self.response = DummyResponse()


def test_addepic_rejects_non_positive_number(monkeypatch):
    intents = discord.Intents.none()
    bot = commands.Bot(command_prefix="!", intents=intents)
    cog = ProfileCog(bot)

    async def dummy_get_track(track):
        return {"track_id": "t1", "title": "Song", "artist_name": "Artist", "url": "u"}

    monkeypatch.setattr(spotify, "get_track", dummy_get_track)

    interaction = DummyInteraction()
    asyncio.run(ProfileCog.addepic.callback(cog, interaction, "abc", 0))
    assert interaction.response.message == "Epic-Nummer muss > 0 sein."
    asyncio.run(bot.close())


def test_addepic_inserts_epic(monkeypatch):
    intents = discord.Intents.none()
    bot = commands.Bot(command_prefix="!", intents=intents)
    cog = ProfileCog(bot)

    async def dummy_get_track(track):
        return {"track_id": "t1", "title": "Song", "artist_name": "Artist", "url": "u"}

    async def dummy_upsert_track(*args, **kwargs):
        pass

    async def dummy_fetch_one(*args, **kwargs):
        return None

    async def dummy_execute(*args, **kwargs):
        dummy_execute.called = True

    dummy_execute.called = False

    async def dummy_get_next_position(self, uid):
        return 1

    async def dummy_ensure_user(self, uid):
        pass

    monkeypatch.setattr(spotify, "get_track", dummy_get_track)
    monkeypatch.setattr(spotify, "upsert_track", dummy_upsert_track)
    monkeypatch.setattr(db, "fetch_one", dummy_fetch_one)
    monkeypatch.setattr(db, "execute", dummy_execute)
    monkeypatch.setattr(ProfileCog, "get_next_position", dummy_get_next_position)
    monkeypatch.setattr(ProfileCog, "ensure_user", dummy_ensure_user)

    interaction = DummyInteraction()
    asyncio.run(ProfileCog.addepic.callback(cog, interaction, "abc", 5))

    assert dummy_execute.called
    assert "✅ Epic hinzugefügt" in interaction.response.message
    asyncio.run(bot.close())
