"""Constants, thresholds, and API URLs for Phish timings."""

import os

# ── Paths ──────────────────────────────────────────────────────────────
DB_DIR = os.path.expanduser("~/.phishtimings")
DB_PATH = os.path.join(DB_DIR, "phishtimings.db")
MB_CACHE_DIR = os.path.join(DB_DIR, "cache")

# ── LivePhish (official streaming catalog) ────────────────────────────
LP_CACHE_DIR = os.path.join(DB_DIR, "cache_livephish")
LP_API_BASE = "https://streamapi.livephish.com/api.aspx"
LP_RATE_LIMIT = 0.5
LP_USER_AGENT = "PhishTimingsBot/1.0 (https://github.com/phishtimings)"

# ── MusicBrainz (authoritative timing source) ─────────────────────────
MUSICBRAINZ_ARTIST_ID = "e01646f2-2a04-450d-8bf2-0d993082e058"  # Phish
MUSICBRAINZ_RATE_LIMIT = 1.0  # seconds between requests (MB policy)

# The "Live Phish" series (20 volumes).  Most Phish live releases are NOT
# in any series — they're browsed by artist instead (see musicbrainz.py).
MUSICBRAINZ_SERIES_IDS = {
    "Live Phish": "ef2a0131-2731-4692-bd84-e16df12f79e5",
}

# ── Year bounds ───────────────────────────────────────────────────────
CONCERT_YEAR_MIN = 1983
CONCERT_YEAR_MAX = 2026

# ── Song classification ──────────────────────────────────────────────
# Phish has no Drums/Space equivalent
UTILITY_SONGS = frozenset()

# ── Normalization thresholds ─────────────────────────────────────────
FUZZY_AUTO_THRESHOLD = 0.85
FUZZY_FLAG_THRESHOLD = 0.65

# ── Analysis ─────────────────────────────────────────────────────────
OUTLIER_STD_MULTIPLIER = 3.0
MIN_SAMPLES_FOR_STATS = 3

# ── phish.in (fan recordings) ─────────────────────────────────────────
PI_CACHE_DIR = os.path.join(DB_DIR, "cache_phishin")
PI_API_BASE = "https://phish.in/api/v2"
PI_RATE_LIMIT = 0.25

# ── Quality ranking ──────────────────────────────────────────────────
QUALITY_RANKS = {
    "official": 500,
}
