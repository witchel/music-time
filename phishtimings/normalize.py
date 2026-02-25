"""Minimal song normalization for Phish.

MusicBrainz recording titles are already clean, so this module is much
simpler than gdtimings/normalize.py.  No massive canonical dictionary
is needed — songs are created on first encounter and fuzzy matching
builds the alias table over time.
"""

import re
import difflib

from phishtimings.config import (
    FUZZY_AUTO_THRESHOLD,
    FUZZY_FLAG_THRESHOLD,
    CANONICAL_ALIASES,
)
from phishtimings import db


# ── Non-song patterns ────────────────────────────────────────────────
_NON_SONG_WORDS = frozenset({
    "tuning", "crowd", "crowd noise", "audience",
    "set break", "intermission", "break",
    "banter", "stage banter",
    "intro", "introduction", "band introductions",
    "applause",
    "soundcheck",
    "unknown", "untitled",
})


def _is_non_song(title):
    """Check whether a title is a non-song."""
    lower = title.lower().strip()
    if not lower:
        return True
    if lower in _NON_SONG_WORDS:
        return True
    return False


def clean_title(raw):
    """Minimal cleaning for MusicBrainz recording titles.

    MB titles are mostly clean; we just strip segment labels and
    normalize whitespace.
    """
    s = raw.strip()
    if not s:
        return ""

    # Strip segue markers FIRST (so segment labels become end-anchored)
    s = re.sub(r'\s*-?[>→]+\s*$', '', s)

    # Strip segment labels like "(Part 1)", "V1", "continued"
    s = re.sub(r'\s*\(?(V\d+|verse\s+\d+|part\s+\d+|continued)\)?\s*$', '', s,
               flags=re.IGNORECASE)

    # Normalize whitespace
    s = re.sub(r"\s+", " ", s).strip()

    if _is_non_song(s):
        return ""

    # Reject very short non-letter titles (but allow known numeric songs)
    if len(s) < 2 or not re.search(r'[a-zA-Z]', s):
        if s.lower() not in CANONICAL_ALIASES:
            return ""

    return s


def normalize_song(conn, raw_title):
    """Resolve a raw track title to a (song_id, canonical_name, match_type) tuple.

    match_type is one of: 'exact', 'alias', 'fuzzy', 'new'
    Returns (None, None, None) for non-songs.
    """
    cleaned = clean_title(raw_title)
    if not cleaned:
        return None, None, None

    lower = cleaned.lower()

    # 1. Check DB alias table first
    song_id = db.get_song_by_alias(conn, lower)
    if song_id:
        row = conn.execute("SELECT canonical_name FROM songs WHERE id = ?", (song_id,)).fetchone()
        return song_id, row["canonical_name"], "alias"

    # 2. Check if already a canonical name in DB
    row = conn.execute(
        "SELECT id, canonical_name FROM songs WHERE LOWER(canonical_name) = ?", (lower,)
    ).fetchone()
    if row:
        db.add_alias(conn, lower, row["id"], "variant")
        return row["id"], row["canonical_name"], "exact"

    # 2b. Check pre-seeded canonical aliases (abbreviations, numeric titles)
    if lower in CANONICAL_ALIASES:
        canonical = CANONICAL_ALIASES[lower]
        song_id = db.get_or_create_song(conn, canonical)
        db.add_alias(conn, lower, song_id, "canonical_alias")
        return song_id, canonical, "alias"

    # 3. Fuzzy match against established DB songs (>=10 tracks)
    db_songs = conn.execute(
        """SELECT s.canonical_name
           FROM songs s
           JOIN tracks t ON t.song_id = s.id
           GROUP BY s.id
           HAVING COUNT(t.id) >= 10"""
    ).fetchall()
    if db_songs:
        db_names = [row["canonical_name"] for row in db_songs]
        db_matches = difflib.get_close_matches(
            lower, [n.lower() for n in db_names],
            n=1, cutoff=FUZZY_FLAG_THRESHOLD,
        )
        if db_matches:
            matched_lower = db_matches[0]
            canonical = next(n for n in db_names if n.lower() == matched_lower)
            ratio = difflib.SequenceMatcher(None, lower, matched_lower).ratio()
            alias_type = "auto_fuzzy" if ratio >= FUZZY_AUTO_THRESHOLD else "fuzzy_flagged"
            song_id = db.get_or_create_song(conn, canonical)
            db.add_alias(conn, lower, song_id, alias_type)
            return song_id, canonical, "fuzzy"

    # 4. No match — create new song entry
    song_id = db.get_or_create_song(conn, cleaned)
    db.add_alias(conn, lower, song_id, "variant")
    return song_id, cleaned, "new"
