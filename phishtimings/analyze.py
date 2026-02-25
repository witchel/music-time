"""Song statistics and post-scrape enrichment for Phish.

Reuses compute_song_stats and print_song_summary from gdtimings.analyze.
Skips classify_song_types (no utility songs) and detect_sandwiches
(no Drums/Space pattern in Phish).

Adds backfill_set_names() to copy set_name from phish.in cached data
to MB/LP tracks that lack it.
"""

import os

from gdtimings.analyze import compute_song_stats, print_song_summary
from gdtimings.cache import read_cache
from phishtimings.config import PI_CACHE_DIR
from phishtimings.normalize import clean_title


def backfill_set_names(conn, verbose=True):
    """Copy set_name from phish.in cache to MB/LP tracks missing it.

    For each release with NULL set_name, looks up the same concert_date
    in the phish.in cache and matches tracks by normalized song name.
    Falls back to positional matching when name matching fails.

    Returns the number of tracks updated.
    """
    if not os.path.isdir(PI_CACHE_DIR):
        if verbose:
            print("  No phish.in cache directory — skipping set_name backfill")
        return 0

    # Find releases with NULL set_name tracks (non-phishin sources)
    rows = conn.execute("""
        SELECT DISTINCT r.id, r.concert_date
        FROM releases r
        JOIN tracks t ON t.release_id = r.id
        WHERE t.set_name IS NULL
          AND r.source_type != 'phishin'
          AND r.concert_date IS NOT NULL
    """).fetchall()

    if not rows:
        if verbose:
            print("  No tracks need set_name backfill")
        return 0

    updated = 0
    for row in rows:
        release_id = row["id"]
        concert_date = row["concert_date"]

        # Read phish.in cache for this date
        cached = read_cache(PI_CACHE_DIR, concert_date)
        if not cached:
            continue

        pi_tracks = cached.get("tracks", [])
        if not pi_tracks:
            continue

        # Build lookup: normalized_name → set_name from phish.in
        pi_by_name = {}
        pi_by_pos = {}
        for pt in pi_tracks:
            title = pt.get("title", "")
            set_name = pt.get("set_name")
            pos = pt.get("position", 0)
            if not set_name:
                continue
            cleaned = clean_title(title).lower()
            if cleaned:
                pi_by_name[cleaned] = set_name
            if pos:
                pi_by_pos[pos] = set_name

        if not pi_by_name and not pi_by_pos:
            continue

        # Get tracks needing backfill for this release
        db_tracks = conn.execute("""
            SELECT id, title_raw, track_number
            FROM tracks
            WHERE release_id = ? AND set_name IS NULL
            ORDER BY track_number
        """, (release_id,)).fetchall()

        for dt in db_tracks:
            cleaned = clean_title(dt["title_raw"]).lower()
            set_name = pi_by_name.get(cleaned) or pi_by_pos.get(dt["track_number"])
            if set_name:
                conn.execute(
                    "UPDATE tracks SET set_name = ? WHERE id = ?",
                    (set_name, dt["id"]),
                )
                updated += 1

    conn.commit()
    if verbose:
        print(f"  Backfilled set_name for {updated} tracks")
    return updated


__all__ = ["compute_song_stats", "print_song_summary", "backfill_set_names"]
