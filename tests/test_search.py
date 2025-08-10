import types
import asyncio
import pytest
import discord
from discord.ext import commands

from cogs.search import SearchCog
from core import spotify, db


class DummyResponse:
    def __init__(self):
        self.message = None
        self.kwargs = None

    async def send_message(self, message=None, **kwargs):
        self.message = message
        self.kwargs = kwargs


class DummyInteraction:
    def __init__(self):
        self.user = types.SimpleNamespace(id=1, display_name="User1")
        self.response = DummyResponse()


def setup_cog():
    intents = discord.Intents.none()
    bot = commands.Bot(command_prefix="!", intents=intents)
    return bot, SearchCog(bot)


def test_findcollector_artist_not_found(monkeypatch):
    bot, cog = setup_cog()

    async def dummy_get_canonical_artist(name):
        return None

    monkeypatch.setattr(spotify, "get_canonical_artist", dummy_get_canonical_artist)

    interaction = DummyInteraction()
    asyncio.run(SearchCog.findcollector.callback(cog, interaction, "abc"))

    assert interaction.response.message == "Artist nicht gefunden."
    asyncio.run(bot.close())


def test_findcollector_no_collectors(monkeypatch):
    bot, cog = setup_cog()

    async def dummy_get_canonical_artist(name):
        return {"name": "Artist"}

    async def dummy_fetch_one(query, params):
        return {"artist_id": 1}

    async def dummy_fetch_all(query, params):
        return []

    monkeypatch.setattr(spotify, "get_canonical_artist", dummy_get_canonical_artist)
    monkeypatch.setattr(db, "fetch_one", dummy_fetch_one)
    monkeypatch.setattr(db, "fetch_all", dummy_fetch_all)

    interaction = DummyInteraction()
    asyncio.run(SearchCog.findcollector.callback(cog, interaction, "Artist"))

    assert interaction.response.message == "Niemand hat diesen Artist als Favorit gesetzt."
    asyncio.run(bot.close())


def test_findcollector_lists_collectors(monkeypatch):
    bot, cog = setup_cog()

    async def dummy_get_canonical_artist(name):
        return {"name": "Artist"}

    async def dummy_fetch_one(query, params):
        return {"artist_id": 1}

    async def dummy_fetch_all(query, params):
        return [
            {"user_id": "1", "badge": None},
            {"user_id": "2", "badge": "Gold"},
        ]

    monkeypatch.setattr(spotify, "get_canonical_artist", dummy_get_canonical_artist)
    monkeypatch.setattr(db, "fetch_one", dummy_fetch_one)
    monkeypatch.setattr(db, "fetch_all", dummy_fetch_all)

    interaction = DummyInteraction()
    asyncio.run(SearchCog.findcollector.callback(cog, interaction, "Artist"))

    assert "<@1>" in interaction.response.kwargs["embed"].fields[0].value
    assert "Gold" in interaction.response.kwargs["embed"].fields[0].value
    asyncio.run(bot.close())
