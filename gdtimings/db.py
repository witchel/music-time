"""SQLite schema, connection, and all DB operations."""

import os
import sqlite3
from datetime import datetime, timezone

from gdtimings.config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS songs (
    id              INTEGER PRIMARY KEY,
    canonical_name  TEXT NOT NULL UNIQUE,
    first_played    TEXT,
    last_played     TEXT,
    times_played    INTEGER DEFAULT 0,
    median_duration REAL,
    mean_duration   REAL,
    std_duration    REAL
);

CREATE TABLE IF NOT EXISTS song_aliases (
    alias   TEXT PRIMARY KEY,
    song_id INTEGER NOT NULL REFERENCES songs(id),
    alias_type TEXT DEFAULT 'variant'
);

CREATE TABLE IF NOT EXISTS releases (
    id              INTEGER PRIMARY KEY,
    source_type     TEXT NOT NULL,
    source_id       TEXT NOT NULL UNIQUE,
    title           TEXT,
    concert_date    TEXT,
    venue           TEXT,
    coverage        TEXT,
    recording_type  TEXT,
    quality_rank    INTEGER DEFAULT 0,
    release_date    TEXT,
    label           TEXT,
    source_url      TEXT,
    scraped_at      TEXT NOT NULL,
    scrape_status   TEXT DEFAULT 'complete'
);
CREATE INDEX IF NOT EXISTS idx_releases_date ON releases(concert_date);

CREATE TABLE IF NOT EXISTS tracks (
    id              INTEGER PRIMARY KEY,
    release_id      INTEGER NOT NULL REFERENCES releases(id) ON DELETE CASCADE,
    song_id         INTEGER REFERENCES songs(id),
    title_raw       TEXT,
    disc_number     INTEGER,
    track_number    INTEGER,
    set_name        TEXT,
    duration_seconds REAL,
    writers         TEXT,
    segue           INTEGER DEFAULT 0,
    is_outlier      INTEGER DEFAULT 0,
    UNIQUE(release_id, disc_number, track_number)
);
CREATE INDEX IF NOT EXISTS idx_tracks_song ON tracks(song_id);

CREATE TABLE IF NOT EXISTS scrape_state (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def get_connection(db_path=None):
    """Get a SQLite connection, creating the DB and schema if needed."""
    path = db_path or DB_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    return conn


# ── Scrape state ───────────────────────────────────────────────────────

def get_scrape_state(conn, key):
    row = conn.execute("SELECT value FROM scrape_state WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_scrape_state(conn, key, value):
    conn.execute(
        "INSERT INTO scrape_state (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()


# ── Releases ───────────────────────────────────────────────────────────

def release_exists(conn, source_id):
    row = conn.execute(
        "SELECT id FROM releases WHERE source_id = ?", (source_id,)
    ).fetchone()
    return row["id"] if row else None


def insert_release(conn, *, source_type, source_id, title=None, concert_date=None,
                   venue=None, coverage=None, recording_type="official",
                   quality_rank=500, release_date=None, label=None, source_url=None):
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        """INSERT INTO releases
           (source_type, source_id, title, concert_date, venue, coverage,
            recording_type, quality_rank, release_date, label, source_url, scraped_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (source_type, source_id, title, concert_date, venue, coverage,
         recording_type, quality_rank, release_date, label, source_url, now),
    )
    return cur.lastrowid


def update_release(conn, release_id, **fields):
    if not fields:
        return
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(
        f"UPDATE releases SET {set_clause} WHERE id = ?",
        (*fields.values(), release_id),
    )


# ── Songs ──────────────────────────────────────────────────────────────

def get_or_create_song(conn, canonical_name):
    row = conn.execute(
        "SELECT id FROM songs WHERE canonical_name = ?", (canonical_name,)
    ).fetchone()
    if row:
        return row["id"]
    cur = conn.execute(
        "INSERT INTO songs (canonical_name) VALUES (?)", (canonical_name,)
    )
    return cur.lastrowid


def get_song_by_alias(conn, alias):
    row = conn.execute(
        "SELECT song_id FROM song_aliases WHERE alias = ?", (alias,)
    ).fetchone()
    return row["song_id"] if row else None


def add_alias(conn, alias, song_id, alias_type="variant"):
    conn.execute(
        "INSERT OR IGNORE INTO song_aliases (alias, song_id, alias_type) VALUES (?, ?, ?)",
        (alias, song_id, alias_type),
    )


# ── Tracks ─────────────────────────────────────────────────────────────

def insert_track(conn, *, release_id, title_raw, disc_number=1, track_number,
                 song_id=None, set_name=None, duration_seconds=None,
                 writers=None, segue=0):
    conn.execute(
        """INSERT OR REPLACE INTO tracks
           (release_id, song_id, title_raw, disc_number, track_number,
            set_name, duration_seconds, writers, segue)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (release_id, song_id, title_raw, disc_number, track_number,
         set_name, duration_seconds, writers, segue),
    )


def get_tracks_for_song(conn, song_id):
    return conn.execute(
        "SELECT * FROM tracks WHERE song_id = ? AND duration_seconds IS NOT NULL",
        (song_id,),
    ).fetchall()


# ── Stats / queries ───────────────────────────────────────────────────

def all_songs(conn):
    return conn.execute("SELECT * FROM songs ORDER BY canonical_name").fetchall()


def all_releases(conn):
    return conn.execute("SELECT * FROM releases ORDER BY concert_date").fetchall()


def db_stats(conn):
    stats = {}
    for table in ("songs", "releases", "tracks", "song_aliases"):
        row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
        stats[table] = row["n"]
    stats["tracks_with_duration"] = conn.execute(
        "SELECT COUNT(*) AS n FROM tracks WHERE duration_seconds IS NOT NULL"
    ).fetchone()["n"]
    stats["unmatched_tracks"] = conn.execute(
        "SELECT COUNT(*) AS n FROM tracks WHERE song_id IS NULL"
    ).fetchone()["n"]
    return stats


def unmatched_tracks(conn):
    return conn.execute(
        """SELECT DISTINCT title_raw FROM tracks
           WHERE song_id IS NULL ORDER BY title_raw"""
    ).fetchall()


def update_song_stats(conn, song_id, *, times_played, median_duration,
                      mean_duration, std_duration, first_played, last_played):
    conn.execute(
        """UPDATE songs SET times_played=?, median_duration=?, mean_duration=?,
           std_duration=?, first_played=?, last_played=?
           WHERE id=?""",
        (times_played, median_duration, mean_duration, std_duration,
         first_played, last_played, song_id),
    )


def mark_outlier(conn, track_id, is_outlier=1):
    conn.execute("UPDATE tracks SET is_outlier = ? WHERE id = ?", (is_outlier, track_id))


def export_tracks(conn):
    return conn.execute(
        """SELECT s.canonical_name AS song, t.duration_seconds, t.disc_number,
                  t.track_number, t.set_name, t.writers, t.segue, t.is_outlier,
                  r.title AS release_title, r.concert_date, r.venue, r.coverage,
                  r.source_type
           FROM tracks t
           JOIN releases r ON t.release_id = r.id
           LEFT JOIN songs s ON t.song_id = s.id
           ORDER BY s.canonical_name, r.concert_date""",
    ).fetchall()
