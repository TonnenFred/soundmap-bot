import types
from pathlib import Path
import sys
import os

import asyncio
from contextlib import asynccontextmanager
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
    assert interaction.response.kwargs.get("ephemeral") is True
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


def test_addepic_rejects_duplicate_song(monkeypatch):
    intents = discord.Intents.none()
    bot = commands.Bot(command_prefix="!", intents=intents)
    cog = ProfileCog(bot)

    async def dummy_get_track(track):
        return {"track_id": "t1", "title": "Song", "artist_name": "Artist", "url": "u"}

    async def dummy_upsert_track(*args, **kwargs):
        pass

    async def dummy_fetch_one(*args, **kwargs):
        return 1

    async def dummy_ensure_user(self, uid):
        pass

    monkeypatch.setattr(spotify, "get_track", dummy_get_track)
    monkeypatch.setattr(spotify, "upsert_track", dummy_upsert_track)
    monkeypatch.setattr(db, "fetch_one", dummy_fetch_one)
    monkeypatch.setattr(ProfileCog, "ensure_user", dummy_ensure_user)

    interaction = DummyInteraction()
    asyncio.run(ProfileCog.addepic.callback(cog, interaction, "abc", 5))

    assert interaction.response.message == "You already own an Epic for this song."
    asyncio.run(bot.close())


def test_delepic_deletes_epic(monkeypatch):
    intents = discord.Intents.none()
    bot = commands.Bot(command_prefix="!", intents=intents)
    cog = ProfileCog(bot)

    async def dummy_fetch_one(query, params):
        return {"position": 2}

    executed = []

    async def dummy_execute(query, params):
        executed.append((query, params))

    @asynccontextmanager
    async def dummy_transaction():
        yield

    monkeypatch.setattr(db, "fetch_one", dummy_fetch_one)
    monkeypatch.setattr(db, "execute", dummy_execute)
    monkeypatch.setattr(db, "transaction", dummy_transaction)

    interaction = DummyInteraction()
    asyncio.run(ProfileCog.delepic.callback(cog, interaction, "t1"))

    assert executed[0][0].startswith("DELETE")
    assert interaction.response.message == "✅ Epic removed."
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


def test_sortartists_by_name(monkeypatch):
    intents = discord.Intents.none()
    bot = commands.Bot(command_prefix="!", intents=intents)
    cog = ProfileCog(bot)

    async def dummy_ensure_user(self, uid):
        pass

    async def dummy_fetch_all(query, params):
        dummy_fetch_all.query = query
        return [{"artist_id": 2}, {"artist_id": 1}]

    updates = []

    async def dummy_execute(query, params):
        updates.append(params)

    @asynccontextmanager
    async def dummy_transaction():
        yield

    monkeypatch.setattr(ProfileCog, "ensure_user", dummy_ensure_user)
    monkeypatch.setattr(db, "fetch_all", dummy_fetch_all)
    monkeypatch.setattr(db, "execute", dummy_execute)
    monkeypatch.setattr(db, "transaction", dummy_transaction)

    interaction = DummyInteraction()
    choice = app_commands.Choice(name="Name", value="name")
    asyncio.run(ProfileCog.sortartists.callback(cog, interaction, choice))

    assert "ORDER BY a.name" in dummy_fetch_all.query
    assert updates == [(1, "1", 2), (2, "1", 1)]
    assert interaction.response.message == "✅ Favorite artists sorted alphabetically."
    asyncio.run(bot.close())


def test_sortartists_by_badge(monkeypatch):
    intents = discord.Intents.none()
    bot = commands.Bot(command_prefix="!", intents=intents)
    cog = ProfileCog(bot)

    async def dummy_ensure_user(self, uid):
        pass

    async def dummy_fetch_all(query, params):
        dummy_fetch_all.query = query
        return [{"artist_id": 2}, {"artist_id": 1}]

    updates = []

    async def dummy_execute(query, params):
        updates.append(params)

    @asynccontextmanager
    async def dummy_transaction():
        yield

    monkeypatch.setattr(ProfileCog, "ensure_user", dummy_ensure_user)
    monkeypatch.setattr(db, "fetch_all", dummy_fetch_all)
    monkeypatch.setattr(db, "execute", dummy_execute)
    monkeypatch.setattr(db, "transaction", dummy_transaction)

    interaction = DummyInteraction()
    choice = app_commands.Choice(name="Badge", value="badge")
    asyncio.run(ProfileCog.sortartists.callback(cog, interaction, choice))

    assert "ORDER BY CASE ufa.badge" in dummy_fetch_all.query
    assert updates == [(1, "1", 2), (2, "1", 1)]
    assert interaction.response.message == "✅ Favorite artists sorted by badge."
    asyncio.run(bot.close())


def test_sortepics_by_name(monkeypatch):
    intents = discord.Intents.none()
    bot = commands.Bot(command_prefix="!", intents=intents)
    cog = ProfileCog(bot)

    async def dummy_ensure_user(self, uid):
        pass

    async def dummy_fetch_all(query, params):
        dummy_fetch_all.query = query
        return [{"track_id": "b", "epic_number": 2}, {"track_id": "a", "epic_number": 1}]

    updates = []

    async def dummy_execute(query, params):
        updates.append(params)

    @asynccontextmanager
    async def dummy_transaction():
        yield

    monkeypatch.setattr(ProfileCog, "ensure_user", dummy_ensure_user)
    monkeypatch.setattr(db, "fetch_all", dummy_fetch_all)
    monkeypatch.setattr(db, "execute", dummy_execute)
    monkeypatch.setattr(db, "transaction", dummy_transaction)

    interaction = DummyInteraction()
    choice = app_commands.Choice(name="Name", value="name")
    asyncio.run(ProfileCog.sortepics.callback(cog, interaction, choice))

    assert "ORDER BY t.artist_name" in dummy_fetch_all.query
    assert updates == [(1, "1", "b", 2), (2, "1", "a", 1)]
    assert interaction.response.message == "✅ Epics sorted alphabetically."
    asyncio.run(bot.close())


def test_sortwishes_by_name(monkeypatch):
    intents = discord.Intents.none()
    bot = commands.Bot(command_prefix="!", intents=intents)
    cog = ProfileCog(bot)

    async def dummy_ensure_user(self, uid):
        pass

    async def dummy_fetch_all(query, params):
        dummy_fetch_all.query = query
        return [{"track_id": "b"}, {"track_id": "a"}]

    updates = []

    async def dummy_execute(query, params):
        updates.append(params)

    @asynccontextmanager
    async def dummy_transaction():
        yield

    monkeypatch.setattr(ProfileCog, "ensure_user", dummy_ensure_user)
    monkeypatch.setattr(db, "fetch_all", dummy_fetch_all)
    monkeypatch.setattr(db, "execute", dummy_execute)
    monkeypatch.setattr(db, "transaction", dummy_transaction)

    interaction = DummyInteraction()
    choice = app_commands.Choice(name="Name", value="name")
    asyncio.run(ProfileCog.sortwishes.callback(cog, interaction, choice))

    assert "ORDER BY t.artist_name" in dummy_fetch_all.query
    assert updates == [(1, "1", "b"), (2, "1", "a")]
    assert interaction.response.message == "✅ Wishlist sorted alphabetically."
    asyncio.run(bot.close())


def test_autocomplete_owned_tracks(monkeypatch):
    intents = discord.Intents.none()
    bot = commands.Bot(command_prefix="!", intents=intents)
    cog = ProfileCog(bot)

    async def dummy_fetch_all(query, params):
        assert params[0] == "1"
        return [{"track_id": "t1", "title": "Song", "artist_name": "Artist"}]

    monkeypatch.setattr(db, "fetch_all", dummy_fetch_all)

    interaction = DummyInteraction()
    choices = asyncio.run(ProfileCog.autocomplete_owned_tracks(cog, interaction, ""))

    assert choices[0].value == "t1"
    assert "Artist" in choices[0].name
    asyncio.run(bot.close())


def test_autocomplete_wishlist_tracks(monkeypatch):
    intents = discord.Intents.none()
    bot = commands.Bot(command_prefix="!", intents=intents)
    cog = ProfileCog(bot)

    async def dummy_fetch_all(query, params):
        assert params[0] == "1"
        return [{"track_id": "t2", "title": "Wish", "artist_name": "Band"}]

    monkeypatch.setattr(db, "fetch_all", dummy_fetch_all)

    interaction = DummyInteraction()
    choices = asyncio.run(ProfileCog.autocomplete_wishlist_tracks(cog, interaction, ""))

    assert choices[0].value == "t2"
    assert "Band" in choices[0].name
    asyncio.run(bot.close())


def test_delartist_deletes_artist(monkeypatch):
    intents = discord.Intents.none()
    bot = commands.Bot(command_prefix="!", intents=intents)
    cog = ProfileCog(bot)

    async def dummy_ensure_user(self, uid):
        pass

    async def dummy_fetch_one(query, params):
        return {"position": 2, "name": "Artist"}

    executed = []

    async def dummy_execute(query, params):
        executed.append((query, params))

    @asynccontextmanager
    async def dummy_transaction():
        yield

    monkeypatch.setattr(ProfileCog, "ensure_user", dummy_ensure_user)
    monkeypatch.setattr(db, "fetch_one", dummy_fetch_one)
    monkeypatch.setattr(db, "execute", dummy_execute)
    monkeypatch.setattr(db, "transaction", dummy_transaction)

    interaction = DummyInteraction()
    asyncio.run(ProfileCog.delartist.callback(cog, interaction, "5"))

    assert executed[0][0].startswith("DELETE")
    assert interaction.response.message == "✅ Favorite artist removed: **Artist**."
    asyncio.run(bot.close())
