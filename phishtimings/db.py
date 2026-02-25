"""Thin wrapper over gdtimings.db that uses the Phish database path.

All schema, queries, and DB operations are reused from gdtimings.db.
Only get_connection() is overridden to point at ~/.phishtimings/phishtimings.db.
"""

from gdtimings.db import (  # noqa: F401 — re-export everything
    SCHEMA,
    get_scrape_state,
    set_scrape_state,
    release_exists,
    insert_release,
    update_release,
    get_or_create_song,
    get_song_by_alias,
    add_alias,
    insert_track,
    get_tracks_for_song,
    all_songs,
    all_releases,
    db_stats,
    unmatched_tracks,
    update_song_stats,
    mark_outlier,
    export_tracks,
)
from gdtimings.db import get_connection as _gd_get_connection

from phishtimings.config import DB_PATH


def get_connection(db_path=None):
    """Get a SQLite connection to the Phish database."""
    return _gd_get_connection(db_path or DB_PATH)


def dates_already_in_db(conn):
    """Return set of concert_date strings already in the DB (any source)."""
    rows = conn.execute("SELECT DISTINCT concert_date FROM releases").fetchall()
    return {row["concert_date"] for row in rows if row["concert_date"]}
