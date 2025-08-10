-- Schema for the Soundmap Discord bot

-- Users table to persist per-user settings.
CREATE TABLE IF NOT EXISTS users (
  user_id TEXT PRIMARY KEY,
  username TEXT,
  epic_sort_mode TEXT NOT NULL DEFAULT 'added',
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Canonical artist list. Case-insensitive uniqueness enforced via COLLATE NOCASE.
CREATE TABLE IF NOT EXISTS artists (
  artist_id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE COLLATE NOCASE
);

-- Canonical track list keyed by Spotify ID.
CREATE TABLE IF NOT EXISTS tracks (
  track_id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  artist_name TEXT NOT NULL,
  url TEXT NOT NULL
);

-- Epics table: stores each Epic owned by a user. Epics are identified by a Spotify track
-- and a serial number. The added_at timestamp captures the time of insertion and
-- position can be used for manual ordering. A composite primary key prevents
-- duplicate entries for the same Epic.
CREATE TABLE IF NOT EXISTS user_epics (
  user_id TEXT NOT NULL,
  track_id TEXT NOT NULL,
  epic_number INTEGER NOT NULL CHECK (epic_number > 0),
  added_at TEXT DEFAULT CURRENT_TIMESTAMP,
  position INTEGER,
  PRIMARY KEY (user_id, track_id, epic_number),
  FOREIGN KEY (user_id) REFERENCES users(user_id),
  FOREIGN KEY (track_id) REFERENCES tracks(track_id)
);

-- Wishlist for Epics. Stores only the track, as the serial number is unique per
-- Epic but not needed for a wish. An optional note allows users to add context.
CREATE TABLE IF NOT EXISTS user_wishlist_epics (
  user_id TEXT NOT NULL,
  track_id TEXT NOT NULL,
  note TEXT,
  PRIMARY KEY (user_id, track_id),
  FOREIGN KEY (user_id) REFERENCES users(user_id),
  FOREIGN KEY (track_id) REFERENCES tracks(track_id)
);

-- Users can set their favourite artists and associate a badge. Badges must be
-- explicitly validated in application logic.
CREATE TABLE IF NOT EXISTS user_fav_artists (
  user_id TEXT NOT NULL,
  artist_id INTEGER NOT NULL,
  badge TEXT CHECK (badge IN ('Bronze','Silver','Gold','Platinum','Diamond','Legendary','VIP','Shiny')),
  PRIMARY KEY (user_id, artist_id),
  FOREIGN KEY (user_id) REFERENCES users(user_id),
  FOREIGN KEY (artist_id) REFERENCES artists(artist_id)
);

-- Indexes to speed up autocomplete for artists and tracks.
CREATE INDEX IF NOT EXISTS idx_artists_name ON artists(name);
CREATE INDEX IF NOT EXISTS idx_tracks_title ON tracks(title);
CREATE INDEX IF NOT EXISTS idx_tracks_artist ON tracks(artist_name);
