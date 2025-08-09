"""Spotify API client for the Soundmap Discord bot.

This module manages authentication against the Spotify Web API using the
Client Credentials flow. It caches access tokens until shortly before they
expire and exposes helpers for searching tracks and upserting track metadata
into the local database.

It also provides artist search helpers used for validation and autocomplete.
"""

from __future__ import annotations

import aiohttp
import base64
import time
from typing import Any

from .config import SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET
from . import db as db_module

_session: aiohttp.ClientSession | None = None
_token_data: dict[str, Any] = {"access_token": None, "expires_at": 0.0}


async def _get_session() -> aiohttp.ClientSession:
    """Return a global aiohttp session. Creates it on first use."""
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession()
    return _session


async def get_token() -> str:
    """Obtain a Spotify API access token using the Client Credentials flow.

    The token is cached until 60 seconds before expiry to minimise HTTP
    requests. If a valid token is cached, it is returned immediately.
    """
    global _token_data
    now = time.time()
    # Use cached token if still valid
    if _token_data.get("access_token") and now < _token_data.get("expires_at", 0):
        return _token_data["access_token"]
    session = await _get_session()
    auth_str = f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}"
    b64_auth = base64.b64encode(auth_str.encode()).decode()
    headers = {"Authorization": f"Basic {b64_auth}"}
    data = {"grant_type": "client_credentials"}
    async with session.post("https://accounts.spotify.com/api/token", headers=headers, data=data) as resp:
        resp.raise_for_status()
        payload = await resp.json()
    access_token = payload["access_token"]
    expires_in = int(payload.get("expires_in", 3600))
    # Set expiry 60 seconds before actual expiry to allow margin
    _token_data = {
        "access_token": access_token,
        "expires_at": now + expires_in - 60,
    }
    return access_token


# -----------------------------------------------------------------------------
# Track Search
# -----------------------------------------------------------------------------
async def search_tracks(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Search for tracks on Spotify by a free text query.

    Returns a list of dictionaries containing the track ID, title, artist name,
    year (release year if available) and URL. The number of results can be
    limited via the ``limit`` parameter.
    """
    token = await get_token()
    session = await _get_session()
    params = {
        "q": query,
        "type": "track",
        "limit": limit,
    }
    headers = {"Authorization": f"Bearer {token}"}
    async with session.get("https://api.spotify.com/v1/search", params=params, headers=headers) as resp:
        resp.raise_for_status()
        data = await resp.json()
    tracks: list[dict[str, Any]] = []
    for item in data.get("tracks", {}).get("items", []):
        track_id = item["id"]
        title = item["name"]
        artist_name = ", ".join(artist["name"] for artist in item["artists"])
        url = item["external_urls"]["spotify"]
        release_date = item.get("album", {}).get("release_date") or ""
        year = release_date.split("-")[0] if release_date else ""
        tracks.append({
            "track_id": track_id,
            "title": title,
            "artist_name": artist_name,
            "url": url,
            "year": year,
        })
    return tracks


# -----------------------------------------------------------------------------
# Artist Search (for validation & autocomplete)
# -----------------------------------------------------------------------------
async def search_artists(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Search artists on Spotify.

    Returns a list of dicts with at least: {"id": str, "name": str, "popularity": int}
    """
    if not query.strip():
        return []
    token = await get_token()
    session = await _get_session()
    params = {"q": query, "type": "artist", "limit": limit}
    headers = {"Authorization": f"Bearer {token}"}
    async with session.get("https://api.spotify.com/v1/search", params=params, headers=headers) as resp:
        resp.raise_for_status()
        data = await resp.json()

    items = (data.get("artists", {}) or {}).get("items", []) or []
    results: list[dict[str, Any]] = []
    for a in items:
        results.append({
            "id": a["id"],
            "name": a["name"],
            "popularity": int(a.get("popularity", 0)),
        })
    return results


async def get_canonical_artist(query: str) -> dict[str, Any] | None:
    """Return the best matching artist (first result) or None if not found."""
    results = await search_artists(query, limit=1)
    return results[0] if results else None


# -----------------------------------------------------------------------------
# Track Upsert
# -----------------------------------------------------------------------------
async def upsert_track(track_id: str, title: str, artist_name: str, url: str) -> None:
    """Insert or update a track in the local database.

    If a track with the given Spotify ID already exists, its title, artist name
    and URL are updated. Otherwise a new record is inserted. Foreign key
    constraints are honoured implicitly by referencing this table from
    ``user_epics`` and ``user_wishlist_epics``.
    """
    await db_module.execute(
        """
        INSERT INTO tracks(track_id, title, artist_name, url)
        VALUES(?,?,?,?)
        ON CONFLICT(track_id) DO UPDATE
          SET title=excluded.title,
              artist_name=excluded.artist_name,
              url=excluded.url
        """,
        (track_id, title, artist_name, url),
    )
