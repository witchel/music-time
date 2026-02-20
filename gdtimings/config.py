"""Constants, thresholds, and API URLs."""

import os

# ── Paths ──────────────────────────────────────────────────────────────
DB_DIR = os.path.expanduser("~/.gdtimings")
DB_PATH = os.path.join(DB_DIR, "gdtimings.db")

# ── Wikipedia API ──────────────────────────────────────────────────────
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
WIKIPEDIA_USER_AGENT = "GDTimingsBot/1.0 (Grateful Dead song timings research)"
WIKIPEDIA_RATE_LIMIT = 1.0  # seconds between requests

# Categories to scrape (order matters for dedup — earlier = higher priority)
WIKIPEDIA_CATEGORIES = [
    "Category:Dick's Picks albums",
    "Category:Dave's Picks albums",
    "Category:Road Trips albums",
    "Category:Grateful Dead Download Series",
    "Category:Grateful Dead live albums",
]

# ── Quality ranking ────────────────────────────────────────────────────
QUALITY_RANKS = {
    "official": 500,
    "SBD": 300,
    "MTX": 200,
    "AUD": 100,
}

# ── Normalization thresholds ───────────────────────────────────────────
FUZZY_AUTO_THRESHOLD = 0.85   # auto-match above this
FUZZY_FLAG_THRESHOLD = 0.65   # flag for review above this

# ── Analysis ───────────────────────────────────────────────────────────
OUTLIER_STD_MULTIPLIER = 3.0  # flag tracks > N std devs from mean
MIN_SAMPLES_FOR_STATS = 3     # need at least N tracks to compute stats
