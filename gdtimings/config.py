"""Constants, thresholds, and API URLs."""

import os

# ── Paths ──────────────────────────────────────────────────────────────
DB_DIR = os.path.expanduser("~/.gdtimings")
DB_PATH = os.path.join(DB_DIR, "gdtimings.db")
ARCHIVE_CACHE_DIR = os.path.join(DB_DIR, "cache")
ARCHIVE_DEFAULT_WORKERS = 64

# ── Wikipedia API (release discovery + coverage metadata) ─────────────
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

# Default coverage by Wikipedia category (used for release discovery and
# coverage metadata; MusicBrainz is the authoritative timing source).
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

# ── MusicBrainz (authoritative timing source for official releases) ───
MUSICBRAINZ_ARTIST_ID = "6faa7ca7-0d99-4a5e-bfa6-1fd5037520c6"  # Grateful Dead
MUSICBRAINZ_RATE_LIMIT = 1.0  # seconds between requests (MB policy)

# Series MBIDs for systematic enumeration of official releases.
# All are release group series on MusicBrainz.
MUSICBRAINZ_SERIES_IDS = {
    "Dick's Picks": "972d3352-0a10-4a3a-9c89-c0444c000d1a",
    "Dave's Picks": "9c50cb94-967a-4747-976e-cc61bd621f37",
    "Road Trips": "098710be-5412-4914-9243-956c82cf2f30",
    "Download Series": "c3d80fe0-f74e-48ea-96cc-ba7c384a2744",
    "Europe '72: The Complete Recordings": "ce8adb72-377d-4b70-aa18-22b0dc1b5dfe",
}

# Coverage classification for MusicBrainz series — mirrors CATEGORY_COVERAGE.
MUSICBRAINZ_SERIES_COVERAGE = {
    "Dick's Picks": "complete",
    "Dave's Picks": "complete",
    "Road Trips": "unedited",
    "Download Series": "complete",
    "Europe '72: The Complete Recordings": "complete",
}

# Standalone box sets not in any MusicBrainz series.
# Key = release group MBID, value = coverage tier.
MUSICBRAINZ_STANDALONE_RELEASES = {
    "a2d4652b-0cfc-340d-baa1-5db355769f1e": "complete",  # Fillmore West 1969
    "282a8755-cf19-42e9-ac3e-ddc05e101b1c": "complete",  # Winterland June 1977
    "aa3370c2-99a9-4c2c-a0be-f870b887aee5": "complete",  # May 1977: Get Shown the Light
    "399df1ca-f362-4dd5-87c7-e5b15497faa3": "complete",  # July 1978
    "d0249401-6a5f-468d-997a-fa2a8b0fca46": "complete",  # Giants Stadium 1987, 1989, 1991
    "221e9122-e43e-46fa-881b-34357902acae": "complete",  # Pacific Northwest '73-'74
}

# ── Internet Archive ──────────────────────────────────────────────────
ARCHIVE_SCRAPE_URL = "https://archive.org/services/search/v1/scrape"
ARCHIVE_METADATA_URL = "https://archive.org/metadata/{identifier}"
ARCHIVE_USER_AGENT = "GDTimingsBot/1.0 (Grateful Dead song timings research)"
ARCHIVE_RATE_LIMIT = 0.0  # seconds between requests (IA allows 500/s)

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
