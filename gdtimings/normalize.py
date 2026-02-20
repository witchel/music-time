"""Song name canonicalization and alias table.

Cleaning pipeline:
1. Strip track numbers, segue markers, set annotations
2. Normalize quotes and whitespace
3. Look up in alias table (DB) → exact match
4. Look up in static CANONICAL_SONGS dictionary → exact match
5. Fuzzy match via difflib against canonical names
6. Create new song entry if no match found
"""

import re
import difflib

from gdtimings.config import FUZZY_AUTO_THRESHOLD, FUZZY_FLAG_THRESHOLD
from gdtimings import db

# ── Canonical songs with known aliases ─────────────────────────────────
# Maps canonical name → list of known aliases (all lowercase for matching).
# This covers the most commonly seen GD songs in official releases.
CANONICAL_SONGS = {
    "Aiko-Aiko": ["iko iko", "aiko aiko"],
    "Alabama Getaway": [],
    "Alligator": [],
    "Althea": [],
    "And We Bid You Goodnight": ["we bid you goodnight", "bid you goodnight",
                                  "and we bid you good night"],
    "Around and Around": ["around & around"],
    "Attics of My Life": [],
    "Beat It On Down the Line": ["beat it on down the line"],
    "Bertha": [],
    "Big Boss Man": [],
    "Big Railroad Blues": ["big rr blues"],
    "Big River": [],
    "Bird Song": ["birdsong"],
    "Black Muddy River": [],
    "Black Peter": [],
    "Black-Throated Wind": ["black throated wind"],
    "Blow Away": [],
    "Blues for Allah": [],
    "Born Cross-Eyed": ["born cross eyed"],
    "Box of Rain": [],
    "Branford Marsalis Jam": [],
    "Brokedown Palace": [],
    "Brown-Eyed Women": ["brown eyed women"],
    "Built to Last": [],
    "Candyman": [],
    "Casey Jones": [],
    "Cassidy": [],
    "Cats Under the Stars": [],
    "China Cat Sunflower": ["china cat"],
    "China Doll": [],
    "Cold Rain and Snow": ["cold rain & snow"],
    "Comes a Time": [],
    "Corrina": ["corina"],
    "Cosmic Charlie": [],
    "Crazy Fingers": [],
    "Cumberland Blues": [],
    "Dancing in the Street": ["dancin' in the streets", "dancin in the street",
                               "dancing in the streets"],
    "Dark Star": [],
    "Days Between": [],
    "Deal": [],
    "Dear Mr. Fantasy": ["dear mr fantasy"],
    "Death Don't Have No Mercy": ["death don't have no mercy"],
    "Deep Elem Blues": ["deep elem", "deep ellum blues"],
    "Dire Wolf": [],
    "Don't Ease Me In": ["dont ease me in"],
    "Drums": ["drums/space", "rhythm devils"],
    "Dupree's Diamond Blues": ["dupree's diamond blues"],
    "Easy Answers": [],
    "Easy Wind": [],
    "El Paso": [],
    "Estimated Prophet": [],
    "Eyes of the World": [],
    "Fennario": [],
    "Fire on the Mountain": [],
    "Foolish Heart": [],
    "Franklin's Tower": ["franklins tower"],
    "Friend of the Devil": [],
    "From the Heart of Me": [],
    "Gentlemen, Start Your Engines": ["gentlemen start your engines"],
    "Going Down the Road Feeling Bad": ["goin' down the road feelin' bad",
                                         "goin' down the road feeling bad",
                                         "gdtrfb", "going down the road feelin' bad"],
    "Good Lovin'": ["good lovin", "good loving"],
    "Good Morning Little Schoolgirl": ["good morning little school girl"],
    "Greatest Story Ever Told": ["the greatest story ever told"],
    "Half-Step Mississippi Uptown Toodleloo": [
        "mississippi half-step uptown toodeloo",
        "mississippi half-step uptown toodleloo",
        "mississippi half step uptown toodeloo",
        "half step mississippi uptown toodeloo",
        "mississippi half-step",
        "half-step",
    ],
    "Hard to Handle": [],
    "He's Gone": ["hes gone", "he's gone"],
    "Help on the Way": [],
    "Here Comes Sunshine": [],
    "High Time": [],
    "I Know You Rider": ["i know you rider", "know you rider"],
    "I Need a Miracle": [],
    "If the Shoe Fits": [],
    "In the Midnight Hour": [],
    "It Must Have Been the Roses": ["it must have been the roses",
                                     "must have been the roses"],
    "It's All Over Now": ["its all over now", "it's all over now, baby blue"],
    "It's All Over Now, Baby Blue": ["baby blue", "it's all over now baby blue"],
    "Jack Straw": [],
    "Jack-A-Roe": ["jack a roe", "jackaroe"],
    "Jam": [],
    "Jenny Josephine": [],
    "Johnny B. Goode": ["johnny b goode", "johnny b. good"],
    "Just Like Tom Thumb's Blues": ["just like tom thumbs blues"],
    "Katie Mae": [],
    "King Bee": ["i'm a king bee"],
    "King Solomon's Marbles": [],
    "Knocking on Heaven's Door": ["knockin' on heaven's door",
                                    "knockin on heavens door",
                                    "knocking on heavens door"],
    "Lady with a Fan": ["terrapin station part 1"],
    "Lazy Lightning": [],
    "Let It Grow": [],
    "Liberty": [],
    "Little Red Rooster": [],
    "Looks Like Rain": [],
    "Loose Lucy": [],
    "Lost Sailor": [],
    "Loser": [],
    "Mama Tried": [],
    "Man Smart, Woman Smarter": ["man smart woman smarter"],
    "Mason's Children": ["masons children"],
    "Matilda": [],
    "Me and Bobby McGee": ["me & bobby mcgee"],
    "Me and My Uncle": ["me & my uncle"],
    "Mexicali Blues": [],
    "Might as Well": [],
    "Mission in the Rain": [],
    "Mississippi Half-Step Uptown Toodeloo": [],
    "Money Money": [],
    "Morning Dew": [],
    "Mountains of the Moon": [],
    "Mr. Charlie": ["mr charlie", "mister charlie"],
    "Music Never Stopped": ["the music never stopped"],
    "My Brother Esau": [],
    "New Minglewood Blues": ["the new minglewood blues", "new minglewood",
                              "all new minglewood blues"],
    "New Potato Caboose": [],
    "New Speedway Boogie": [],
    "Next Time You See Me": [],
    "Night They Drove Old Dixie Down": ["the night they drove old dixie down"],
    "Not Fade Away": [],
    "Ode to Billie Joe": [],
    "One More Saturday Night": [],
    "Operator": [],
    "Other One": ["the other one", "that's it for the other one"],
    "Passenger": [],
    "Peggy-O": ["peggy o", "peggy-o"],
    "Picasso Moon": [],
    "Playing in the Band": ["playin' in the band", "playin in the band"],
    "Promised Land": ["the promised land"],
    "Queen Jane Approximately": [],
    "Ramble On Rose": [],
    "Revolutionary Hamstrung Blues": [],
    "Ripple": [],
    "Row Jimmy": [],
    "Sage and Spirit": ["sage & spirit"],
    "Saint of Circumstance": ["saint of circumstance"],
    "Samson and Delilah": ["samson & delilah"],
    "Satin Doll": [],
    "Scarlet Begonias": [],
    "Shakedown Street": [],
    "Ship of Fools": [],
    "Slipknot!": ["slipknot"],
    "Smokestack Lightning": ["smokestack lightnin'"],
    "So Many Roads": [],
    "Space": [],
    "Stagger Lee": [],
    "Standing on the Moon": [],
    "Stella Blue": [],
    "Stranger": ["feel like a stranger"],
    "Sugar Magnolia": [],
    "Sugaree": [],
    "Sunrise": [],
    "Sunshine Daydream": [],
    "Supplication": [],
    "Tennessee Jed": [],
    "Terrapin Station": ["terrapin"],
    "That's It for the Other One": [],
    "The Eleven": ["eleven"],
    "The Wheel": ["wheel"],
    "They Love Each Other": [],
    "Throwing Stones": [],
    "To Lay Me Down": [],
    "Tom Thumb's Blues": [],
    "Tomorrow Never Knows": [],
    "Touch of Grey": ["touch of gray"],
    "Truckin'": ["truckin", "trucking", "truckin'"],
    "Turn On Your Lovelight": ["turn on your love light"],
    "Uncle John's Band": ["uncle johns band"],
    "Unbroken Chain": [],
    "US Blues": ["u.s. blues", "us blues"],
    "Victim or the Crime": [],
    "Viola Lee Blues": [],
    "Warf Rat": ["wharf rat"],
    "Wave to the Wind": [],
    "Way to Go Home": [],
    "Weather Report Suite": [],
    "West L.A. Fadeaway": ["west la fadeaway", "west l.a. fadeaway"],
    "What's Become of the Baby": [],
    "Wheel": [],
    "When I Paint My Masterpiece": [],
    "Wharf Rat": [],
    "Women Are Smarter": [],
    "Werewolves of London": [],
}

# Build a lowercase lookup: alias → canonical name
_ALIAS_MAP = {}
for canonical, aliases in CANONICAL_SONGS.items():
    _ALIAS_MAP[canonical.lower()] = canonical
    for alias in aliases:
        _ALIAS_MAP[alias.lower()] = canonical

# All canonical names for fuzzy matching
_CANONICAL_NAMES = list(CANONICAL_SONGS.keys())


def clean_title(raw):
    """Strip track numbers, segue markers, set annotations, normalize quotes."""
    s = raw.strip()
    # Take only the first line (discard venue/date info on subsequent lines)
    s = s.split("\n")[0].strip()
    # Remove leading track numbers like "1.", "01.", "1)"
    s = re.sub(r"^\d+[\.\)]\s*", "", s)
    # Normalize quotes: convert all fancy quotes to straight
    s = s.replace("\u2018", "'").replace("\u2019", "'")
    s = s.replace("\u201c", '"').replace("\u201d", '"')
    # Remove trailing footnote markers like [a], [b], [1]
    s = re.sub(r'\s*\[[a-z0-9]+\]\s*$', '', s)
    # Remove segue markers FIRST (before duration, since → may follow duration)
    s = s.rstrip(">→ ")
    s = re.sub(r'\s*[>→]+\s*"?\s*$', '', s)
    # Remove trailing duration like – 14:35 or - 5:32
    s = re.sub(r'\s*[–\-—]\s*\d+:\d{2}(?::\d{2})?\s*$', '', s)
    # Remove trailing writer credits: " (writers) with optional segue marker between
    s = re.sub(r'"\s*[>→]?\s*\([^)]+\)\s*$', '', s)
    # Remove trailing " - or " – (e.g. 'St. Stephen" -')
    s = re.sub(r'"\s*[–\-—]\s*$', '', s)
    # Catch-all: if a bare " remains followed by metadata (writers, duration, etc.)
    # truncate at the " — the title is everything before it
    s = re.sub(r'"\s*[>→(–\-—].*$', '', s)
    # Remove trailing ", part N" (e.g. 'Space", part 1')
    s = re.sub(r'",?\s*part\s+\d+\s*$', '', s, flags=re.IGNORECASE)
    # Remove set annotations like "[Set 1]" or "(Set 2)"
    s = re.sub(r"\s*[\[\(](?:Set|Disc|Encore)\s*\d*[\]\)]", "", s, flags=re.IGNORECASE)
    # Strip surrounding quotes
    s = s.strip('"\'')
    # Final cleanup: segue markers that may remain after other stripping
    s = s.rstrip(">→ ")
    s = re.sub(r"\s*[>→]\s*$", "", s)
    # Collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s


def normalize_song(conn, raw_title):
    """Resolve a raw track title to a (song_id, canonical_name, match_type) tuple.

    match_type is one of: 'exact', 'alias', 'fuzzy', 'new'
    """
    cleaned = clean_title(raw_title)
    if not cleaned:
        return None, None, None

    lower = cleaned.lower()

    # 1. Check DB alias table first (includes manual corrections)
    song_id = db.get_song_by_alias(conn, lower)
    if song_id:
        row = conn.execute("SELECT canonical_name FROM songs WHERE id = ?", (song_id,)).fetchone()
        return song_id, row["canonical_name"], "alias"

    # 2. Check static dictionary
    if lower in _ALIAS_MAP:
        canonical = _ALIAS_MAP[lower]
        song_id = db.get_or_create_song(conn, canonical)
        db.add_alias(conn, lower, song_id, "variant")
        return song_id, canonical, "exact"

    # 3. Check if already a canonical name in DB
    row = conn.execute(
        "SELECT id, canonical_name FROM songs WHERE LOWER(canonical_name) = ?", (lower,)
    ).fetchone()
    if row:
        db.add_alias(conn, lower, row["id"], "variant")
        return row["id"], row["canonical_name"], "exact"

    # 4. Fuzzy match against canonical names
    matches = difflib.get_close_matches(lower, [n.lower() for n in _CANONICAL_NAMES],
                                         n=1, cutoff=FUZZY_FLAG_THRESHOLD)
    if matches:
        # Find the original-cased canonical name
        matched_lower = matches[0]
        canonical = _ALIAS_MAP[matched_lower]
        ratio = difflib.SequenceMatcher(None, lower, matched_lower).ratio()
        if ratio >= FUZZY_AUTO_THRESHOLD:
            song_id = db.get_or_create_song(conn, canonical)
            db.add_alias(conn, lower, song_id, "auto_fuzzy")
            return song_id, canonical, "fuzzy"
        # Below auto threshold but above flag threshold — still create
        # but mark as needing review
        song_id = db.get_or_create_song(conn, canonical)
        db.add_alias(conn, lower, song_id, "auto_fuzzy")
        return song_id, canonical, "fuzzy"

    # 5. No match — create new song entry
    song_id = db.get_or_create_song(conn, cleaned)
    db.add_alias(conn, lower, song_id, "variant")
    return song_id, cleaned, "new"
