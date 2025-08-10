import types
from pathlib import Path
import sys
import os

import asyncio
import pytest
import discord
from discord.ext import commands
from discord import app_commands

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DISCORD_TOKEN", "test-token")
os.environ.setdefault("SPOTIFY_CLIENT_ID", "cid")
os.environ.setdefault("SPOTIFY_CLIENT_SECRET", "csecret")

from cogs.profile import ProfileCog, BADGE_EMOJIS
from core import spotify, db


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


def test_addepic_rejects_non_positive_number(monkeypatch):
    intents = discord.Intents.none()
    bot = commands.Bot(command_prefix="!", intents=intents)
    cog = ProfileCog(bot)

    async def dummy_get_track(track):
        return {"track_id": "t1", "title": "Song", "artist_name": "Artist", "url": "u"}

    monkeypatch.setattr(spotify, "get_track", dummy_get_track)

    interaction = DummyInteraction()
    asyncio.run(ProfileCog.addepic.callback(cog, interaction, "abc", 0))
    assert interaction.response.message == "Epic number must be > 0."
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
    assert "✅ Epic added" in interaction.response.message
    asyncio.run(bot.close())


def test_addwish_song_not_found(monkeypatch):
    intents = discord.Intents.none()
    bot = commands.Bot(command_prefix="!", intents=intents)
    cog = ProfileCog(bot)

    async def dummy_get_track(track):
        return None
    async def dummy_ensure_user(self, uid):
        pass

    monkeypatch.setattr(spotify, "get_track", dummy_get_track)
    monkeypatch.setattr(ProfileCog, "ensure_user", dummy_ensure_user)

    interaction = DummyInteraction()
    asyncio.run(ProfileCog.addwish.callback(cog, interaction, "abc", None))

    assert interaction.response.message == "Song not found."
    asyncio.run(bot.close())


def test_addwish_inserts_song(monkeypatch):
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

    async def dummy_ensure_user(self, uid):
        pass

    monkeypatch.setattr(spotify, "get_track", dummy_get_track)
    monkeypatch.setattr(spotify, "upsert_track", dummy_upsert_track)
    monkeypatch.setattr(db, "fetch_one", dummy_fetch_one)
    monkeypatch.setattr(db, "execute", dummy_execute)
    monkeypatch.setattr(ProfileCog, "ensure_user", dummy_ensure_user)

    interaction = DummyInteraction()
    asyncio.run(ProfileCog.addwish.callback(cog, interaction, "abc", None))

    assert dummy_execute.called
    assert interaction.response.message == "✅ Added to wishlist."
    asyncio.run(bot.close())


def test_addartist_sets_badge(monkeypatch):
    intents = discord.Intents.none()
    bot = commands.Bot(command_prefix="!", intents=intents)
    cog = ProfileCog(bot)

    async def dummy_get_canonical_artist(artist):
        return {"name": "Artist"}

    async def dummy_fetch_one(query, params):
        if "SELECT artist_id" in query:
            return {"artist_id": 1}
        return None

    async def dummy_execute(query, params):
        if "user_fav_artists" in query:
            dummy_execute.called = True
            dummy_execute.query = query
            dummy_execute.params = params

    dummy_execute.called = False

    async def dummy_get_next_artist_position(self, uid):
        return 1

    async def dummy_ensure_user(self, uid):
        pass

    monkeypatch.setattr(spotify, "get_canonical_artist", dummy_get_canonical_artist)
    monkeypatch.setattr(db, "fetch_one", dummy_fetch_one)
    monkeypatch.setattr(db, "execute", dummy_execute)
    monkeypatch.setattr(ProfileCog, "get_next_artist_position", dummy_get_next_artist_position)
    monkeypatch.setattr(ProfileCog, "ensure_user", dummy_ensure_user)

    interaction = DummyInteraction()
    badge_choice = app_commands.Choice(name="Gold", value="Gold")
    asyncio.run(ProfileCog.addartist.callback(cog, interaction, "Artist", badge_choice))

    assert dummy_execute.called
    assert "badge" in dummy_execute.query
    assert dummy_execute.params[2] == "Gold"
    assert "Gold" in interaction.response.message
    asyncio.run(bot.close())


def test_profile_shows_badge_with_emoji(monkeypatch):
    intents = discord.Intents.none()
    bot = commands.Bot(command_prefix="!", intents=intents)
    cog = ProfileCog(bot)

    async def dummy_fetch_one(query, params=()):
        return {"username": "PlayerX"}

    async def dummy_fetch_all(query, params=()):
        if "user_fav_artists" in query:
            return [{"name": "Artist", "badge": "Gold"}]
        return []

    async def dummy_ensure_user(self, uid):
        pass

    monkeypatch.setattr(db, "fetch_one", dummy_fetch_one)
    monkeypatch.setattr(db, "fetch_all", dummy_fetch_all)
    monkeypatch.setattr(ProfileCog, "ensure_user", dummy_ensure_user)

    interaction = DummyInteraction()
    asyncio.run(ProfileCog.profile.callback(cog, interaction, None))
    embed = interaction.response.kwargs["embed"]
    field = next(f for f in embed.fields if f.name.startswith("🌟 Favorite Artists"))
    assert field.value == f"Artist — {BADGE_EMOJIS['Gold']} Gold"
    asyncio.run(bot.close())


def test_setbadge_updates_existing(monkeypatch):
    intents = discord.Intents.none()
    bot = commands.Bot(command_prefix="!", intents=intents)
    cog = ProfileCog(bot)

    async def dummy_fetch_one(query, params):
        if "FROM user_fav_artists" in query:
            return {"name": "Artist"}
        return None

    async def dummy_execute(query, params):
        dummy_execute.called = True
        dummy_execute.params = params

    dummy_execute.called = False

    async def dummy_ensure_user(self, uid):
        pass

    monkeypatch.setattr(db, "fetch_one", dummy_fetch_one)
    monkeypatch.setattr(db, "execute", dummy_execute)
    monkeypatch.setattr(ProfileCog, "ensure_user", dummy_ensure_user)

    interaction = DummyInteraction()
    badge_choice = app_commands.Choice(name="Gold", value="Gold")
    asyncio.run(ProfileCog.setbadge.callback(cog, interaction, "1", badge_choice))

    assert dummy_execute.called
    assert "Gold" in interaction.response.message
    asyncio.run(bot.close())


def test_setbadge_rejects_non_favorite(monkeypatch):
    intents = discord.Intents.none()
    bot = commands.Bot(command_prefix="!", intents=intents)
    cog = ProfileCog(bot)

    async def dummy_fetch_one(query, params):
        return None

    async def dummy_execute(query, params):
        dummy_execute.called = True

    dummy_execute.called = False

    async def dummy_ensure_user(self, uid):
        pass

    monkeypatch.setattr(db, "fetch_one", dummy_fetch_one)
    monkeypatch.setattr(db, "execute", dummy_execute)
    monkeypatch.setattr(ProfileCog, "ensure_user", dummy_ensure_user)

    interaction = DummyInteraction()
    badge_choice = app_commands.Choice(name="Gold", value="Gold")
    asyncio.run(ProfileCog.setbadge.callback(cog, interaction, "1", badge_choice))

    assert not dummy_execute.called
    assert interaction.response.message == "This artist is not in your favourites."
    asyncio.run(bot.close())
