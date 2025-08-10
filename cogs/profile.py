"""Cog implementing commands related to user profiles and Epic management.

This cog exposes slash commands for adding and removing Epics from a user's
collection, managing favourite artists and badges, recording Epic wishes,
setting the Epic sorting mode, moving Epics within a custom manual ordering
and displaying a user's profile overview. It relies heavily on the SQLite
database layer and Spotify search functionality defined in the core modules.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from typing import Optional, Iterable, List

from core import db, spotify, util
from core.config import GUILD_ID_DEV

# Valid badges that can be assigned to favourite artists. Exposed for
# autocomplete and validation. The badge 'Shiny' refers to the highest
# badge tier; it is not associated with storing shiny track versions.
BADGES = [
    "Bronze",
    "Silver",
    "Gold",
    "Platinum",
    "Diamond",
    "Legendary",
    "VIP",
    "Shiny",
]


class MoveEpicView(discord.ui.View):
    """Simple UI view offering buttons to move an Epic up or down."""

    def __init__(self, cog: "ProfileCog", user_id: str, track_id: str, epic_number: int) -> None:
        super().__init__()
        self.cog = cog
        self.user_id = user_id
        self.track_id = track_id
        self.epic_number = epic_number

    async def _get_position(self) -> int:
        row = await db.fetch_one(
            "SELECT position FROM user_epics WHERE user_id=? AND track_id=? AND epic_number=?",
            (self.user_id, self.track_id, self.epic_number),
        )
        return row["position"] if row else 0

    @discord.ui.button(emoji="⬆️", style=discord.ButtonStyle.secondary)
    async def move_up(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        pos = await self._get_position()
        await self.cog.move_epic_to(self.user_id, self.track_id, self.epic_number, pos - 1)
        pos = await self._get_position()
        await interaction.response.edit_message(
            content=f"Current position: {pos}", view=self
        )

    @discord.ui.button(emoji="⬇️", style=discord.ButtonStyle.secondary)
    async def move_down(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        pos = await self._get_position()
        await self.cog.move_epic_to(self.user_id, self.track_id, self.epic_number, pos + 1)
        pos = await self._get_position()
        await interaction.response.edit_message(
            content=f"Current position: {pos}", view=self
        )


class ProfileCog(commands.Cog):
    """Cog handling profile management commands for Epics and badges."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # Helper method to ensure a user row exists
    async def ensure_user(self, user_id: str) -> None:
        await db.execute(
            "INSERT INTO users(user_id) VALUES(?) ON CONFLICT DO NOTHING",
            (user_id,),
        )

    async def get_next_position(self, user_id: str) -> int:
        """Return the next manual position for a new Epic for the given user."""
        row = await db.fetch_one(
            "SELECT COALESCE(MAX(position), 0) AS maxp FROM user_epics WHERE user_id=?",
            (user_id,),
        )
        return (row["maxp"] or 0) + 1

    async def move_epic_to(self, user_id: str, track_id: str, epic_number: int, new_pos: int) -> None:
        """Reposition an Epic in manual ordering, adjusting other positions accordingly."""
        # Fetch the current position
        row = await db.fetch_one(
            "SELECT position FROM user_epics WHERE user_id=? AND track_id=? AND epic_number=?",
            (user_id, track_id, epic_number),
        )
        if row is None:
            raise ValueError("Epic not found for this user.")
        old_pos = row["position"] or 1
        if new_pos < 1:
            new_pos = 1
        # Determine the maximum position to bound moves
        max_row = await db.fetch_one(
            "SELECT COALESCE(MAX(position), 0) AS maxp FROM user_epics WHERE user_id=?",
            (user_id,),
        )
        max_pos = max_row["maxp"] or 1
        if new_pos > max_pos:
            new_pos = max_pos
        if old_pos == new_pos:
            return
        async with db.transaction():
            if new_pos < old_pos:
                # Shift down: increment positions in [new_pos, old_pos-1]
                await db.execute(
                    """
                    UPDATE user_epics
                    SET position = position + 1
                    WHERE user_id=? AND position >= ? AND position < ?
                    """,
                    (user_id, new_pos, old_pos),
                )
            else:
                # Shift up: decrement positions in [old_pos+1, new_pos]
                await db.execute(
                    """
                    UPDATE user_epics
                    SET position = position - 1
                    WHERE user_id=? AND position <= ? AND position > ?
                    """,
                    (user_id, new_pos, old_pos),
                )
            # Set new position for the moved Epic
            await db.execute(
                """
                UPDATE user_epics
                SET position=?
                WHERE user_id=? AND track_id=? AND epic_number=?
                """,
                (new_pos, user_id, track_id, epic_number),
            )

    # Slash commands
    # Autocomplete for track selection reused across commands
    async def autocomplete_tracks(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete helper for Spotify tracks stored in the local database."""
        term = (current or "").strip()
        # Build list of suggestions: prefix matches first, then substring
        suggestions: list[tuple[str, str]] = []
        if term:
            # Prefix matches
            rows = await db.fetch_all(
                """
                SELECT track_id, title, artist_name
                FROM tracks
                WHERE title LIKE ? OR artist_name LIKE ?
                ORDER BY artist_name COLLATE NOCASE, title COLLATE NOCASE
                LIMIT 15
                """,
                (term + "%", term + "%"),
            )
            suggestions += [(r["track_id"], f"{r['artist_name']} – {r['title']}") for r in rows]
            if len(suggestions) < 25:
                rows2 = await db.fetch_all(
                    """
                    SELECT track_id, title, artist_name
                    FROM tracks
                    WHERE (title LIKE ? OR artist_name LIKE ?) AND (title NOT LIKE ? AND artist_name NOT LIKE ?)
                    ORDER BY artist_name COLLATE NOCASE, title COLLATE NOCASE
                    LIMIT ?
                    """,
                    (f"%{term}%", f"%{term}%", term + "%", term + "%", 25 - len(suggestions)),
                )
                suggestions += [(r["track_id"], f"{r['artist_name']} – {r['title']}") for r in rows2]
        else:
            suggestions = []
        return [app_commands.Choice(name=label[:100], value=track_id) for track_id, label in suggestions[:25]]

    # ---------- NEW: Autocomplete tracks via Spotify live ----------
    async def autocomplete_spotify_tracks(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete helper using live Spotify track search."""
        term = (current or "").strip()
        try:
            results = await spotify.search_tracks(term, limit=10) if term else []
        except Exception:
            results = []
        choices = []
        for t in results:
            label = f"{t['artist_name']} – {t['title']}"
            if t.get('year'):
                label += f" ({t['year']})"
            choices.append(app_commands.Choice(name=label[:100], value=t['track_id']))
        return choices[:25]

    # ---------- UPDATED: Autocomplete artists via Spotify live ----------
    async def autocomplete_artists(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete helper for artists using live Spotify search."""
        term = (current or "").strip()
        try:
            results = await spotify.search_artists(term, limit=10) if term else []
        except Exception:
            results = []
        # Return the name as the value; the DB insert handles creation
        return [app_commands.Choice(name=a["name"][:100], value=a["name"]) for a in results][:25]

    @app_commands.command(name="username", description="Set your Soundmap in-game username")
    @app_commands.describe(name="Your new in-game username")
    async def username(self, interaction: discord.Interaction, name: str) -> None:
        """Set or update the ingame Soundmap username directly."""
        user_id = str(interaction.user.id)
        await self.ensure_user(user_id)
        name = name.strip()
        await db.execute(
            "UPDATE users SET username=? WHERE user_id=?", (name, user_id)
        )
        await interaction.response.send_message(
            f"✅ Username set: **{name}**", ephemeral=True
        )

    # Command: add Epic via Spotify search with autocomplete
    @app_commands.command(name="addepic", description="Add an Epic from Spotify")
    @app_commands.rename(track="song", epic_number="number")
    @app_commands.describe(
        track="The song (selectable via autocomplete)",
        epic_number="The serial number of the Epic",
    )
    @app_commands.autocomplete(track=autocomplete_spotify_tracks)
    async def addepic(
        self, interaction: discord.Interaction, track: str, epic_number: int
    ) -> None:
        """Add an Epic by selecting a Spotify track via autocomplete."""
        try:
            t = await spotify.get_track(track)
        except Exception:
            t = None
        if not t:
            await interaction.response.send_message(
                "Song not found.", ephemeral=True
            )
            return
        if epic_number <= 0:
            await interaction.response.send_message(
                "Epic number must be > 0.", ephemeral=True
            )
            return
        user_id = str(interaction.user.id)
        await self.ensure_user(user_id)
        await spotify.upsert_track(
            t["track_id"], t["title"], t["artist_name"], t["url"]
        )
        exists = await db.fetch_one(
            """
            SELECT 1 FROM user_epics WHERE user_id=? AND track_id=? AND epic_number=?
            """,
            (user_id, t["track_id"], epic_number),
        )
        if exists:
            await interaction.response.send_message(
                "You already own this Epic.", ephemeral=True
            )
            return
        next_pos = await self.get_next_position(user_id)
        await db.execute(
            """
            INSERT INTO user_epics(user_id, track_id, epic_number, position)
            VALUES(?,?,?,?)
            """,
            (user_id, t["track_id"], epic_number, next_pos),
        )
        await interaction.response.send_message(
            f"✅ Epic added: **{t['artist_name']} – {t['title']}** (# {epic_number})",
            ephemeral=True,
        )

    # Command: remove an Epic
    @app_commands.command(name="delepic", description="Remove an Epic from your collection")
    @app_commands.rename(track="song", epic_number="number")
    @app_commands.describe(track="The song (selectable via autocomplete)", epic_number="The serial number of the Epic")
    @app_commands.autocomplete(track=autocomplete_tracks)
    async def delepic(self, interaction: discord.Interaction, track: str, epic_number: int) -> None:
        user_id = str(interaction.user.id)
        # Check if the epic exists
        row = await db.fetch_one(
            "SELECT position FROM user_epics WHERE user_id=? AND track_id=? AND epic_number=?",
            (user_id, track, epic_number),
        )
        if not row:
            await interaction.response.send_message(
                "You don't own this Epic.",
                ephemeral=True,
            )
            return
        pos = row["position"] or 1
        # Remove epic and shift positions
        async with db.transaction():
            await db.execute(
                "DELETE FROM user_epics WHERE user_id=? AND track_id=? AND epic_number=?",
                (user_id, track, epic_number),
            )
            # Decrement positions greater than removed
            await db.execute(
                """
                UPDATE user_epics
                SET position = position - 1
                WHERE user_id=? AND position > ?
                """,
                (user_id, pos),
            )
        await interaction.response.send_message(
            "✅ Epic removed.",
            ephemeral=True,
        )

    # Command: add a song to the wishlist via Spotify search
    @app_commands.command(name="addwish", description="Add a song to your wishlist")
    @app_commands.rename(track="song")
    @app_commands.describe(track="The song (selectable via autocomplete)", note="Optional note")
    @app_commands.autocomplete(track=autocomplete_spotify_tracks)
    async def addwish(self, interaction: discord.Interaction, track: str, note: Optional[str] = None) -> None:
        user_id = str(interaction.user.id)
        await self.ensure_user(user_id)
        # Fetch track details from Spotify
        try:
            t = await spotify.get_track(track)
        except Exception:
            t = None
        if not t:
            await interaction.response.send_message("Song not found.", ephemeral=True)
            return
        await spotify.upsert_track(t["track_id"], t["title"], t["artist_name"], t["url"])
        # Insert or update wishlist note
        row = await db.fetch_one(
            "SELECT 1 FROM user_wishlist_epics WHERE user_id=? AND track_id=?",
            (user_id, t["track_id"]),
        )
        if row:
            await db.execute(
                "UPDATE user_wishlist_epics SET note=? WHERE user_id=? AND track_id=?",
                (note, user_id, t["track_id"]),
            )
            msg = "Wishlist note updated."
        else:
            await db.execute(
                "INSERT INTO user_wishlist_epics(user_id, track_id, note) VALUES(?,?,?)",
                (user_id, t["track_id"], note),
            )
            msg = "✅ Added to wishlist."
        await interaction.response.send_message(msg, ephemeral=True)

    # Command: remove from wishlist
    @app_commands.command(name="delwish", description="Remove a song from your wishlist")
    @app_commands.rename(track="song")
    @app_commands.autocomplete(track=autocomplete_tracks)
    async def delwish(self, interaction: discord.Interaction, track: str) -> None:
        user_id = str(interaction.user.id)
        row = await db.fetch_one(
            "SELECT 1 FROM user_wishlist_epics WHERE user_id=? AND track_id=?",
            (user_id, track),
        )
        if not row:
            await interaction.response.send_message("This song is not on your wishlist.", ephemeral=True)
            return
        await db.execute(
            "DELETE FROM user_wishlist_epics WHERE user_id=? AND track_id=?",
            (user_id, track),
        )
        await interaction.response.send_message("✅ Removed from wishlist.", ephemeral=True)

    # ---------- UPDATED: add favourite artist (Spotify validation) ----------
    @app_commands.command(name="addartist", description="Add a favorite artist")
    @app_commands.autocomplete(artist=autocomplete_artists)
    async def addartist(self, interaction: discord.Interaction, artist: str) -> None:
        user_id = str(interaction.user.id)
        await self.ensure_user(user_id)

        # Spotify-Validierung & Kanonisierung
        sp = await spotify.get_canonical_artist(artist)
        if not sp:
            await interaction.response.send_message("Artist not found on Spotify.", ephemeral=True)
            return
        canonical_name = sp["name"]

        # In lokale Tabelle eintragen (unique by name)
        await db.execute(
            "INSERT INTO artists(name) VALUES(?) ON CONFLICT(name) DO NOTHING",
            (canonical_name,),
        )
        row = await db.fetch_one("SELECT artist_id FROM artists WHERE name=?", (canonical_name,))
        if not row:
            await interaction.response.send_message("Internal error saving artist.", ephemeral=True)
            return
        artist_id_int = row["artist_id"]

        # Set favorite artist
        await db.execute(
            "INSERT INTO user_fav_artists(user_id, artist_id) VALUES(?,?) ON CONFLICT(user_id, artist_id) DO NOTHING",
            (user_id, artist_id_int),
        )
        await interaction.response.send_message(f"✅ Favorite artist added: **{canonical_name}**.", ephemeral=True)

    # ---------- NEW: remove favourite artist ----------
    @app_commands.command(name="delartist", description="Remove a favorite artist")
    @app_commands.autocomplete(artist=autocomplete_artists)
    async def delartist(self, interaction: discord.Interaction, artist: str) -> None:
        user_id = str(interaction.user.id)
        await self.ensure_user(user_id)

        # Spotify-Validierung & Kanonisierung
        sp = await spotify.get_canonical_artist(artist)
        if not sp:
            await interaction.response.send_message("Artist not found on Spotify.", ephemeral=True)
            return
        canonical_name = sp["name"]

        # Artist-ID nachschlagen
        row = await db.fetch_one("SELECT artist_id FROM artists WHERE name=?", (canonical_name,))
        if not row:
            await interaction.response.send_message("This artist is not in your list.", ephemeral=True)
            return
        artist_id_int = row["artist_id"]

        fav_row = await db.fetch_one(
            "SELECT 1 FROM user_fav_artists WHERE user_id=? AND artist_id=?",
            (user_id, artist_id_int),
        )
        if not fav_row:
            await interaction.response.send_message("This artist is not in your list.", ephemeral=True)
            return

        await db.execute(
            "DELETE FROM user_fav_artists WHERE user_id=? AND artist_id=?",
            (user_id, artist_id_int),
        )
        await interaction.response.send_message(
            f"✅ Favorite artist removed: **{canonical_name}**.", ephemeral=True
        )

    # ---------- UPDATED: set badge with Spotify validation ----------
    @app_commands.command(name="setbadge", description="Set your badge for a favorite artist")
    @app_commands.autocomplete(artist=autocomplete_artists)
    @app_commands.choices(badge=[app_commands.Choice(name=b, value=b) for b in BADGES])
    @app_commands.describe(badge="Which badge you have")
    async def setbadge(self, interaction: discord.Interaction, artist: str, badge: app_commands.Choice[str]) -> None:
        user_id = str(interaction.user.id)
        await self.ensure_user(user_id)

        # Spotify-Validierung & Kanonisierung
        sp = await spotify.get_canonical_artist(artist)
        if not sp:
            await interaction.response.send_message("Artist not found on Spotify.", ephemeral=True)
            return
        canonical_name = sp["name"]

        # Ensure the artist exists in 'artists'
        await db.execute(
            "INSERT INTO artists(name) VALUES(?) ON CONFLICT(name) DO NOTHING",
            (canonical_name,),
        )
        row = await db.fetch_one("SELECT artist_id FROM artists WHERE name=?", (canonical_name,))
        artist_id_int = row["artist_id"]

        # Upsert favourite artist row with badge
        await db.execute(
            """
            INSERT INTO user_fav_artists(user_id, artist_id, badge)
            VALUES(?,?,?)
            ON CONFLICT(user_id, artist_id) DO UPDATE SET badge=excluded.badge
            """,
            (user_id, artist_id_int, badge.value),
        )
        await interaction.response.send_message(f"✅ Badge **{badge.value}** set for **{canonical_name}**.", ephemeral=True)

    # Command: set epic sort mode
    @app_commands.command(name="set_epic_sort", description="Choose how your Epics are sorted in the profile")
    @app_commands.choices(mode=[
        app_commands.Choice(name="Added order", value="added"),
        app_commands.Choice(name="By artist", value="artist"),
        app_commands.Choice(name="Manual", value="manual"),
    ])
    async def set_epic_sort(self, interaction: discord.Interaction, mode: app_commands.Choice[str]) -> None:
        user_id = str(interaction.user.id)
        await self.ensure_user(user_id)
        await db.execute(
            "INSERT INTO users(user_id, epic_sort_mode) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET epic_sort_mode=excluded.epic_sort_mode",
            (user_id, mode.value),
        )
        await interaction.response.send_message(
            f"✅ Sort mode set to **{mode.name}**.",
            ephemeral=True,
        )

    # Command: move epic manually
    @app_commands.command(
        name="move_epic", description="Interactively move one of your Epics"
    )
    @app_commands.autocomplete(track=autocomplete_tracks)
    @app_commands.describe(epic_number="The Epic's serial number to move")
    async def move_epic(
        self, interaction: discord.Interaction, track: str, epic_number: int
    ) -> None:
        user_id = str(interaction.user.id)
        row = await db.fetch_one(
            "SELECT position FROM user_epics WHERE user_id=? AND track_id=? AND epic_number=?",
            (user_id, track, epic_number),
        )
        if row is None:
            await interaction.response.send_message(
                "Epic not found for this user.", ephemeral=True
            )
            return
        view = MoveEpicView(self, user_id, track, epic_number)
        await interaction.response.send_message(
            f"Current position: {row['position']}. Use the buttons to move the Epic.",
            view=view,
            ephemeral=True,
        )

    # Command: show profile
    @app_commands.command(name="profile", description="Show your Soundmap profile")
    async def profile(self, interaction: discord.Interaction, user: Optional[discord.Member] = None) -> None:
        member = user or interaction.user
        user_id = str(member.id)
        await self.ensure_user(user_id)
        # Fetch username and sort mode
        row = await db.fetch_one(
            "SELECT username, epic_sort_mode FROM users WHERE user_id=?", (user_id,)
        )
        username = row["username"] if row else None
        sort_mode = row["epic_sort_mode"] if row else "added"
        # Fetch epics sorted accordingly
        if sort_mode == "artist":
            epics = await db.fetch_all(
                """
                SELECT ue.epic_number, t.title, t.artist_name, t.url
                FROM user_epics ue
                JOIN tracks t ON t.track_id = ue.track_id
                WHERE ue.user_id=?
                ORDER BY t.artist_name COLLATE NOCASE ASC, t.title COLLATE NOCASE ASC, ue.epic_number ASC
                """,
                (user_id,),
            )
        elif sort_mode == "manual":
            epics = await db.fetch_all(
                """
                SELECT ue.epic_number, t.title, t.artist_name, t.url
                FROM user_epics ue
                JOIN tracks t ON t.track_id = ue.track_id
                WHERE ue.user_id=?
                ORDER BY ue.position ASC, ue.epic_number ASC
                """,
                (user_id,),
            )
        else:
            # added order
            epics = await db.fetch_all(
                """
                SELECT ue.epic_number, t.title, t.artist_name, t.url, ue.added_at
                FROM user_epics ue
                JOIN tracks t ON t.track_id = ue.track_id
                WHERE ue.user_id=?
                ORDER BY ue.added_at ASC, ue.rowid ASC
                """,
                (user_id,),
            )
        # Fetch wishlist
        wishlist = await db.fetch_all(
            """
            SELECT t.title, t.artist_name, uw.note, t.url
            FROM user_wishlist_epics uw
            JOIN tracks t ON t.track_id = uw.track_id
            WHERE uw.user_id=?
            ORDER BY t.artist_name COLLATE NOCASE ASC, t.title COLLATE NOCASE ASC
            """,
            (user_id,),
        )
        # Fetch fav artists & badges
        favs = await db.fetch_all(
            """
            SELECT a.name, ufa.badge
            FROM user_fav_artists ufa
            JOIN artists a ON a.artist_id = ufa.artist_id
            WHERE ufa.user_id=?
            ORDER BY a.name COLLATE NOCASE
            """,
            (user_id,),
        )
        # Build embed
        embed = discord.Embed(
            title=f"🎵 {member.display_name}'s Soundmap Collection",
            color=discord.Color.purple(),
        )
        if username:
            embed.insert_field_at(0, name="👤 SM-Username", value=username, inline=False)
        # Epics list
        if epics:
            epic_lines: list[str] = []
            for i, e in enumerate(epics[:15]):  # show up to 15
                # Display format: "Artist – Title #Number" instead of "#Number: Artist – Title"
                epic_lines.append(
                    f"{e['artist_name']} – {e['title']} #{e['epic_number']}"
                )
            more = "" if len(epics) <= 15 else f"\n… {len(epics) - 15} more"
            embed.add_field(name=f"💎 Epics ({len(epics)})", value="\n".join(epic_lines) + more, inline=False)
        else:
            embed.add_field(name="💎 Epics", value="No epics", inline=False)
        # Favourite artists with badge
        if favs:
            fa_lines: list[str] = []
            for a in favs[:15]:
                badge = a["badge"]
                badge_str = f" — {badge}" if badge else ""
                fa_lines.append(f"{a['name']}{badge_str}")
            more = "" if len(favs) <= 15 else f"\n… {len(favs) - 15} more"
            embed.add_field(name=f"🌟 Favorite Artists ({len(favs)})", value="\n".join(fa_lines) + more, inline=False)
        else:
            embed.add_field(name="🌟 Favorite Artists", value="No favorite artists", inline=False)
        # Wishlist
        if wishlist:
            wl_lines: list[str] = []
            for w in wishlist[:15]:
                note_part = f" — _{w['note']}_" if w['note'] else ""
                wl_lines.append(f"{w['artist_name']} – {w['title']}{note_part}")
            more = "" if len(wishlist) <= 15 else f"\n… {len(wishlist) - 15} more"
            embed.add_field(name=f"🎯 Wishlist ({len(wishlist)})", value="\n".join(wl_lines) + more, inline=False)
        else:
            embed.add_field(name="🎯 Wishlist", value="No wishes", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=(user is None))

    # Command: wishcurrent (current song as wishlist)
    @app_commands.command(name="wishcurrent", description="Add the currently playing song (Spotify) to your wishlist")
    async def wishcurrent(self, interaction: discord.Interaction) -> None:
        # Check if user has Spotify activity visible
        activity = next((a for a in interaction.user.activities if isinstance(a, discord.Spotify)), None)
        if not activity:
            await interaction.response.send_message(
                "I don't see a currently playing Spotify song or you've hidden your activity.",
                ephemeral=True,
            )
            return
        user_id = str(interaction.user.id)
        await self.ensure_user(user_id)
        track_id = activity.track_id
        # Upsert track
        await spotify.upsert_track(track_id, activity.title, activity.artist, activity.track_url)
        # Add to wishlist
        row = await db.fetch_one(
            "SELECT 1 FROM user_wishlist_epics WHERE user_id=? AND track_id=?",
            (user_id, track_id),
        )
        if not row:
            await db.execute(
                "INSERT INTO user_wishlist_epics(user_id, track_id, note) VALUES(?,?,?)",
                (user_id, track_id, None),
            )
        await interaction.response.send_message(
            f"✅ Wish added: **{activity.artist} – {activity.title}**.",
            ephemeral=True,
        )

    # ---------- UPDATED: favartistcurrent normalized via Spotify ----------
    @app_commands.command(name="favartistcurrent", description="Add the currently playing artist as a favorite artist")
    async def favartistcurrent(self, interaction: discord.Interaction) -> None:
        activity = next((a for a in interaction.user.activities if isinstance(a, discord.Spotify)), None)
        if not activity:
            await interaction.response.send_message(
                "I don't see a currently playing Spotify song or you've hidden your activity.",
                ephemeral=True,
            )
            return
        user_id = str(interaction.user.id)
        await self.ensure_user(user_id)

        # Normalization via Spotify
        sp = await spotify.get_canonical_artist(activity.artist)
        canonical_name = sp["name"] if sp else activity.artist

        # Insert artist if needed
        await db.execute(
            "INSERT INTO artists(name) VALUES(?) ON CONFLICT(name) DO NOTHING",
            (canonical_name,),
        )
        row = await db.fetch_one("SELECT artist_id FROM artists WHERE name=?", (canonical_name,))
        artist_id_int = row["artist_id"]

        # Add favourite
        await db.execute(
            "INSERT INTO user_fav_artists(user_id, artist_id) VALUES(?,?) ON CONFLICT(user_id, artist_id) DO NOTHING",
            (user_id, artist_id_int),
        )
        await interaction.response.send_message(
            f"✅ Favorite artist added: **{canonical_name}**.",
            ephemeral=True,
        )
