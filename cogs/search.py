"""Cog implementing search and trading related commands.


This cog provides commands for finding owners of a specific Epic track and for
matching potential trading partners based on a user's Epic collection and
wishes. It also exposes autocomplete helpers for tracks and artists that
are shared with the profile cog.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from typing import Optional, List
from core import db, spotify
from cogs.profile import BADGE_EMOJIS


class SearchCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # Autocomplete helpers
    async def autocomplete_spotify_tracks(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        """Autocomplete helper using live Spotify track search."""
        term = (current or "").strip()
        try:
            results = await spotify.search_tracks(term, limit=10) if term else []
        except Exception:
            results = []
        choices = []
        for t in results:
            label = f"{t['artist_name']} – {t['title']}"
            if t.get("year"):
                label += f" ({t['year']})"
            choices.append(app_commands.Choice(name=label[:100], value=t["track_id"]))
        return choices[:25]

    async def autocomplete_artists(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        """Autocomplete helper for artists using live Spotify search."""
        term = (current or "").strip()
        try:
            results = await spotify.search_artists(term, limit=10) if term else []
        except Exception:
            results = []
        return [app_commands.Choice(name=a["name"][:100], value=a["name"]) for a in results][:25]

    # /findowners command
    @app_commands.command(
        name="findowners",
        description="Show owners and seekers of an Epic song",
    )
    @app_commands.rename(track="song")
    @app_commands.describe(track="The song (selectable via autocomplete)")
    @app_commands.autocomplete(track=autocomplete_spotify_tracks)
    async def findowners(self, interaction: discord.Interaction, track: str) -> None:
        # Fetch track metadata from DB or Spotify
        meta = await db.fetch_one(
            "SELECT title, artist_name, url FROM tracks WHERE track_id=?",
            (track,),
        )
        if not meta:
            try:
                meta = await spotify.get_track(track)
            except Exception:
                meta = None
            if not meta:
                await interaction.response.send_message(
                    "Song not found.", ephemeral=True
                )
                return
            await spotify.upsert_track(
                meta["track_id"], meta["title"], meta["artist_name"], meta["url"]
            )

        # Fetch epic owners
        owners = await db.fetch_all(
            """
            SELECT user_id, epic_number
            FROM user_epics
            WHERE track_id=?
            ORDER BY epic_number ASC
            """,
            (track,),
        )
        # Fetch wishers
        wishers = await db.fetch_all(
            "SELECT user_id, note FROM user_wishlist_epics WHERE track_id=?",
            (track,),
        )
        embed = discord.Embed(
            title=f"🔎 Ownership & Wishes for {meta['artist_name']} – {meta['title']}",
            url=meta["url"],
            color=discord.Color.blue(),
        )
        if owners:
            lines = [
                f"<@{row['user_id']}> — #{row['epic_number']}" for row in owners[:20]
            ]
            more = "" if len(owners) <= 20 else f"\n… {len(owners) - 20} more"
            embed.add_field(
                name=f"💎 Owners ({len(owners)})",
                value="\n".join(lines) + more,
                inline=False,
            )
        else:
            embed.add_field(
                name="💎 Owners",
                value="No one owns this Epic.",
                inline=False,
            )
        if wishers:
            lines = [
                f"<@{row['user_id']}>"
                + (f" — _{row['note']}_" if row["note"] else "")
                for row in wishers[:20]
            ]
            more = "" if len(wishers) <= 20 else f"\n… {len(wishers) - 20} more"
            embed.add_field(
                name=f"🎯 Seekers ({len(wishers)})",
                value="\n".join(lines) + more,
                inline=False,
            )
        else:
            embed.add_field(
                name="🎯 Seekers",
                value="No one is looking for this Epic.",
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # /tradehelp command
    @app_commands.command(
        name="tradehelp",
        description="Find potential trade partners based on epics and wishlist",
    )
    async def tradehelp(self, interaction: discord.Interaction, user: Optional[discord.Member] = None) -> None:
        target = user or interaction.user
        user_id = str(target.id)
        # Fetch user's wishlist and epics
        wish_rows = await db.fetch_all(
            "SELECT track_id FROM user_wishlist_epics WHERE user_id=?",
            (user_id,),
        )
        epic_rows = await db.fetch_all(
            "SELECT track_id, epic_number FROM user_epics WHERE user_id=?",
            (user_id,),
        )
        wish_ids = [row['track_id'] for row in wish_rows]
        my_epic_ids = [row['track_id'] for row in epic_rows]
        # Who has what I want
        have_what_i_want = []
        if wish_ids:
            placeholder = ",".join(["?"] * len(wish_ids))
            query = (
                f"SELECT ue.user_id, ue.track_id, ue.epic_number, t.title, t.artist_name "
                "FROM user_epics ue JOIN tracks t ON t.track_id=ue.track_id "
                "WHERE ue.track_id IN (" + placeholder + ") AND ue.user_id <> ?"
            )
            rows = await db.fetch_all(query, (*wish_ids, user_id))
            have_what_i_want = rows
        # Who wants what I have
        want_what_i_have = []
        if my_epic_ids:
            placeholder = ",".join(["?"] * len(my_epic_ids))
            query = (
                f"SELECT uw.user_id, uw.track_id, t.title, t.artist_name "
                "FROM user_wishlist_epics uw JOIN tracks t ON t.track_id=uw.track_id "
                "WHERE uw.track_id IN (" + placeholder + ") AND uw.user_id <> ?"
            )
            rows = await db.fetch_all(query, (*my_epic_ids, user_id))
            want_what_i_have = rows
        embed = discord.Embed(
            title=f"🤝 Trade help for {target.display_name}",
            color=discord.Color.green(),
        )
        if have_what_i_want:
            lines = []
            for row in have_what_i_want[:20]:
                lines.append(f"<@{row['user_id']}> — {row['artist_name']} – {row['title']} (# {row['epic_number']})")
            more = "" if len(have_what_i_want) <= 20 else f"\n… {len(have_what_i_want) - 20} more matches"
            embed.add_field(name="They have what you want", value="\n".join(lines) + more, inline=False)
        else:
            embed.add_field(name="They have what you want", value="No matches", inline=False)
        if want_what_i_have:
            lines = []
            for row in want_what_i_have[:20]:
                lines.append(f"<@{row['user_id']}> — {row['artist_name']} – {row['title']}")
            more = "" if len(want_what_i_have) <= 20 else f"\n… {len(want_what_i_have) - 20} more matches"
            embed.add_field(name="They want what you have", value="\n".join(lines) + more, inline=False)
        else:
            embed.add_field(name="They want what you have", value="No matches", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # /findcollector command
    @app_commands.command(
        name="findcollector", description="Shows users who have set an artist as favorite"
    )
    @app_commands.autocomplete(artist=autocomplete_artists)
    async def findcollector(self, interaction: discord.Interaction, artist: str) -> None:
        # Spotify canonicalisation
        sp = await spotify.get_canonical_artist(artist)
        if not sp:
            await interaction.response.send_message("Artist not found.", ephemeral=True)
            return
        canonical_name = sp["name"]
        row = await db.fetch_one("SELECT artist_id FROM artists WHERE name=?", (canonical_name,))
        if not row:
            await interaction.response.send_message(
                "Nobody has set this artist as a favorite.", ephemeral=True
            )
            return
        artist_id = row["artist_id"]
        collectors = await db.fetch_all(
            "SELECT user_id, badge FROM user_fav_artists WHERE artist_id=?",
            (artist_id,),
        )
        if not collectors:
            await interaction.response.send_message(
                "Nobody has set this artist as a favorite.", ephemeral=True
            )
            return

        badge_order = {
            "Bronze": 0,
            "Silver": 1,
            "Gold": 2,
            "Platinum": 3,
            "Diamond": 4,
            "Legendary": 5,
            "VIP": 6,
            "Shiny": 7,
        }
        collectors.sort(
            key=lambda row: (badge_order.get(row["badge"], -1), int(row["user_id"])),
            reverse=True,
        )
        embed = discord.Embed(
            title=f"🔍 Collectors of {canonical_name}",
            color=discord.Color.purple(),
        )
        lines = []
        for row in collectors[:20]:
            badge = row["badge"]
            badge_emoji = BADGE_EMOJIS.get(badge, "") if badge else ""
            badge_str = f" — {badge_emoji} {badge}" if badge else ""
            lines.append(f"<@{row['user_id']}>{badge_str}")
        more = "" if len(collectors) <= 20 else f"\n… {len(collectors) - 20} more"
        embed.add_field(
            name=f"🌟 Collectors ({len(collectors)})",
            value="\n".join(lines) + more,
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
