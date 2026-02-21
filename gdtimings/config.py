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

# ── Coverage classification ───────────────────────────────────────────
# Three tiers (see CONCEPTS.md section 5):
#   "complete" — full unedited show, best timing data
#   "unedited" — songs unedited but release is not a complete show (still
#                good for timing, e.g. compilations of full-length takes)
#   "edited"  — songs may be trimmed/overdubbed/faded (exclude from timing)
#   "unknown" — not yet classified

# Default coverage by Wikipedia category.
CATEGORY_COVERAGE = {
    "Category:Dick's Picks albums": "complete",
    "Category:Dave's Picks albums": "complete",
    "Category:Road Trips albums": "unedited",
    "Category:Grateful Dead Download Series": "complete",
    "Category:Grateful Dead live albums": "unknown",
}

# Overrides for specific releases in the catch-all "live albums" category.
# Page title (exact Wikipedia article title) → coverage.
RELEASE_COVERAGE_OVERRIDES = {
    # ── Complete unedited shows ──────────────────────────────────────
    "One from the Vault": "complete",
    "Two from the Vault": "complete",
    "Three from the Vault": "complete",
    "Hundred Year Hall": "complete",
    "Dozin' at the Knick": "complete",
    "Crimson, White & Indigo": "complete",
    "To Terrapin: Hartford '77": "complete",
    "Winterland June 1977: The Complete Recordings": "complete",
    "Cornell 5/8/77": "complete",
    "Truckin' Up to Buffalo": "complete",
    "Nightfall of Diamonds": "complete",
    "Wake Up to Find Out": "complete",
    "Sunshine Daydream (album)": "complete",
    "The Closing of Winterland": "complete",
    "Live at the Cow Palace": "complete",
    "Red Rocks 7/8/78": "complete",
    "Duke '78": "complete",
    "Saint of Circumstance (album)": "complete",
    "Fillmore West 1969: The Complete Recordings": "complete",
    "Pacific Northwest '73–'74: The Complete Recordings": "complete",
    "May 1977: Get Shown the Light": "complete",
    "July 1978: The Complete Recordings": "complete",
    "Spring 1990 (The Other One)": "complete",
    "Giants Stadium 1987, 1989, 1991": "complete",
    "Lyceum '72: The Complete Recordings": "complete",
    # ── Unedited songs, not a complete show ──────────────────────────
    "Fallout from the Phil Zone": "unedited",
    "Ladies and Gentlemen... the Grateful Dead": "unedited",
    "Europe '72 Volume 2": "unedited",
    "Steppin' Out with the Grateful Dead: England '72": "unedited",
    "So Many Roads (1965–1995)": "unedited",
    # ── Edited / overdubbed — exclude from timing ────────────────────
    "Live/Dead": "edited",
    "Steal Your Face": "edited",
    "Without a Net": "edited",
    "Reckoning (Grateful Dead album)": "edited",
    "Dead Set": "edited",
    "Europe '72 (album)": "edited",
    "Grateful Dead (Skull and Roses)": "edited",
    "History of the Grateful Dead, Volume One (Bear's Choice)": "edited",
    "Dylan & the Dead": "edited",
    "The Grateful Dead Movie Soundtrack": "edited",
    "Ready or Not (Grateful Dead album)": "edited",
    "Go to Nassau": "unedited",  # only Drums is edited
}

# ── Internet Archive ──────────────────────────────────────────────────
ARCHIVE_SCRAPE_URL = "https://archive.org/services/search/v1/scrape"
ARCHIVE_METADATA_URL = "https://archive.org/metadata/{identifier}"
ARCHIVE_USER_AGENT = "GDTimingsBot/1.0 (Grateful Dead song timings research)"
ARCHIVE_RATE_LIMIT = 0.5  # seconds between requests

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

# ── Song classification ────────────────────────────────────────────────
# Matched songs that are not real songs (Drums/Space/Jam).  "tuning" and
# "crowd" already have song_id=NULL (unmatched tracks) so they are excluded
# by the existing WHERE t.song_id IS NOT NULL clause in queries.
UTILITY_SONGS = frozenset({"Drums", "Space", "Jam"})

# ── Analysis ───────────────────────────────────────────────────────────
OUTLIER_STD_MULTIPLIER = 3.0  # flag tracks > N std devs from mean
MIN_SAMPLES_FOR_STATS = 3     # need at least N tracks to compute stats
