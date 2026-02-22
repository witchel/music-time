"""Song name canonicalization and alias table.

Cleaning pipeline:
1. Strip track numbers, segue markers, set annotations
2. Normalize quotes and whitespace
3. Classify non-songs (tuning, crowd, banter, etc.) → NULL
4. Look up in alias table (DB) → exact match
5. Look up in static CANONICAL_SONGS dictionary → exact match
6. Fuzzy match via difflib against canonical names
7. Fuzzy match against established DB songs (>=50 tracks)
8. Create new song entry if no match found
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
    "All Along the Watchtower": ["all along the watchtower"],
    "Althea": [],
    "And We Bid You Goodnight": ["we bid you goodnight", "bid you goodnight",
                                  "and we bid you good night"],
    "Around and Around": ["around & around"],
    "Attics of My Life": [],
    "Baby What You Want Me to Do": [],
    "Beat It On Down the Line": ["beat it on down the line", "biodtl"],
    "Bertha": [],
    "Big Boss Man": [],
    "Big Boy Pete": [],
    "Big Railroad Blues": ["big rr blues"],
    "Big River": [],
    "Bird Song": ["birdsong"],
    "Black Muddy River": [],
    "Black Peter": [],
    "Black Queen": [],
    "Black-Throated Wind": ["black throated wind"],
    "Blow Away": [],
    "Blues for Allah": [],
    "Born Cross-Eyed": ["born cross eyed"],
    "Box of Rain": [],
    "Branford Marsalis Jam": [],
    "Brokedown Palace": [],
    "Broken Arrow": [],
    "Brown-Eyed Women": ["brown eyed women"],
    "Built to Last": [],
    "Candyman": [],
    "Casey Jones": [],
    "Cassidy": [],
    "Cats Under the Stars": [],
    "Caution (Do Not Stop on Tracks)": ["caution", "caution (do not stop on tracks)",
                                         "caution do not stop on tracks"],
    "C.C. Rider": ["cc rider", "c c rider", "c.c.rider", "see see rider"],
    "China Cat Sunflower": ["china cat"],
    "China Doll": [],
    "Cold Rain and Snow": ["cold rain & snow"],
    "Comes a Time": [],
    "Corrina": ["corina"],
    "Cosmic Charlie": [],
    "Crazy Fingers": [],
    "Cryptical Envelopment": [],
    "Cumberland Blues": [],
    "Dancing in the Street": ["dancin' in the streets", "dancin in the street",
                               "dancing in the streets", "dancin' in the street"],
    "Dark Hollow": [],
    "Dark Star": [],
    "Days Between": [],
    "Deal": [],
    "Dear Mr. Fantasy": ["dear mr fantasy"],
    "Death Don't Have No Mercy": ["death don't have no mercy"],
    "Deep Elem Blues": ["deep elem", "deep ellum blues"],
    "Desolation Row": [],
    "Dire Wolf": [],
    "Doin' That Rag": ["doin that rag"],
    "Don't Ease Me In": ["dont ease me in"],
    "Don't Need Love": ["i don't need love", "i don't need no love"],
    "Drums": ["drums/space", "rhythm devils", "drumz"],
    "Dupree's Diamond Blues": ["dupree's diamond blues"],
    "Easy Answers": [],
    "Easy to Love You": [],
    "Easy Wind": [],
    "El Paso": [],
    "Estimated Prophet": [],
    "Eternity": [],
    "Eyes of the World": [],
    "Far from Me": [],
    "Feedback": [],
    "Fennario": [],
    "Fire on the Mountain": [],
    "Foolish Heart": [],
    "Franklin's Tower": ["franklins tower"],
    "Friend of the Devil": [],
    "From the Heart of Me": [],
    "Gentlemen, Start Your Engines": ["gentlemen start your engines"],
    "Gimme Some Lovin'": ["gimme some lovin", "gimme some loving"],
    "Gloria": [],
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
        "mississippi half step",
        "half-step",
        "mississippi half-step uptown toodeloo",
    ],
    "Hard to Handle": [],
    "He's Gone": ["hes gone", "he's gone"],
    "Heaven Help the Fool": [],
    "Hell in a Bucket": [],
    "Help on the Way": [],
    "Here Comes Sunshine": [],
    "Hey Jude": [],
    "Hey Pocky Way": ["hey pocky way", "hey pocky away"],
    "High Time": [],
    "I Fought the Law": [],
    "I Know You Rider": ["i know you rider", "know you rider"],
    "I Need a Miracle": [],
    "I Will Take You Home": [],
    "I've Been All Around This World": ["ive been all around this world",
                                         "i've been all around this world"],
    "If the Shoe Fits": [],
    "In the Midnight Hour": [],
    "It Hurts Me Too": ["hurts me too", "it hurts me too"],
    "It Must Have Been the Roses": ["it must have been the roses",
                                     "must have been the roses"],
    "It's All Over Now": ["its all over now"],
    "It's All Over Now, Baby Blue": ["baby blue", "it's all over now baby blue",
                                      "it's all over now, baby blue"],
    "Jack Straw": [],
    "Jack-A-Roe": ["jack a roe", "jackaroe"],
    "Jam": [],
    "Jenny Josephine": [],
    "Johnny B. Goode": ["johnny b goode", "johnny b. good"],
    "Just a Little Light": [],
    "Just Like Tom Thumb's Blues": ["just like tom thumbs blues"],
    "Katie Mae": [],
    "Keep Your Day Job": ["day job"],
    "King Bee": ["i'm a king bee"],
    "King Solomon's Marbles": [],
    "Knocking on Heaven's Door": ["knockin' on heaven's door",
                                    "knockin on heavens door",
                                    "knocking on heavens door"],
    "La Bamba": [],
    "Lady with a Fan": ["terrapin station part 1"],
    "Lazy Lightning": [],
    "Lazy River Road": [],
    "Let It Grow": [],
    "Let the Good Times Roll": [],
    "Liberty": [],
    "Little Red Rooster": [],
    "Looks Like Rain": [],
    "Loose Lucy": [],
    "Lost Sailor": [],
    "Loser": [],
    "Maggie's Farm": ["maggies farm"],
    "Mama Tried": [],
    "Man Smart, Woman Smarter": ["man smart woman smarter"],
    "Mason's Children": ["masons children"],
    "Matilda": [],
    "Me and Bobby McGee": ["me & bobby mcgee"],
    "Me and My Uncle": ["me & my uncle"],
    "Mexicali Blues": [],
    "Might as Well": [],
    "Mission in the Rain": [],
    "Money Money": [],
    "Monkey and the Engineer": [],
    "Morning Dew": [],
    "Mountains of the Moon": [],
    "Mr. Charlie": ["mr charlie", "mister charlie"],
    "Music Never Stopped": ["the music never stopped"],
    "My Brother Esau": [],
    "Never Trust a Woman": [],
    "New Minglewood Blues": ["the new minglewood blues", "new minglewood",
                              "all new minglewood blues", "minglewood blues"],
    "New Potato Caboose": [],
    "New Speedway Boogie": [],
    "Next Time You See Me": [],
    "Night They Drove Old Dixie Down": ["the night they drove old dixie down"],
    "Nobody's Fault but Mine": ["nobodys fault but mine", "nobody's fault but mine"],
    "Not Fade Away": ["nfa"],
    "Ode to Billie Joe": [],
    "On the Road Again": [],
    "One More Saturday Night": [],
    "Operator": [],
    "Other One": ["the other one", "that's it for the other one"],
    "Passenger": [],
    "Peggy-O": ["peggy o", "peggy-o"],
    "Picasso Moon": [],
    "Playing in the Band": ["playin' in the band", "playin in the band", "pitb"],
    "Playing in the Band Reprise": ["playin' in the band reprise",
                                     "playin in the band reprise",
                                     "pitb reprise"],
    "Promised Land": ["the promised land"],
    "Queen Jane Approximately": [],
    "Quinn the Eskimo": ["the mighty quinn", "mighty quinn",
                          "quinn the eskimo (the mighty quinn)"],
    "Rain": [],
    "Ramble On Rose": [],
    "Revolution": [],
    "Revolutionary Hamstrung Blues": [],
    "Ripple": [],
    "Row Jimmy": ["row jimmy row"],
    "Sage and Spirit": ["sage & spirit"],
    "Saint of Circumstance": ["saint of circumstance"],
    "Saint Stephen": ["st. stephen", "st stephen"],
    "Samson and Delilah": ["samson & delilah"],
    "(I Can't Get No) Satisfaction": ["satisfaction", "i can't get no satisfaction",
                                       "(i can't get no) satisfaction"],
    "Satin Doll": [],
    "Scarlet Begonias": [],
    "Shakedown Street": [],
    "She Belongs to Me": [],
    "Ship of Fools": [],
    "Sing Me Back Home": [],
    "Slipknot!": ["slipknot"],
    "Smokestack Lightning": ["smokestack lightnin'"],
    "So Many Roads": [],
    "Space": [],
    "Spanish Jam": [],
    "Spoonful": [],
    "Stagger Lee": [],
    "Standing on the Moon": [],
    "Stella Blue": [],
    "Stranger": ["feel like a stranger"],
    "Stuck Inside of Mobile with the Memphis Blues Again": [
        "stuck inside of mobile",
        "stuck inside of mobile with the memphis blues again",
        "memphis blues again",
        "memphis blues",
    ],
    "Sugar Magnolia": [],
    "Sugaree": [],
    "Sunrise": [],
    "Sunshine Daydream": [],
    "Supplication": [],
    "Take a Step Back": [],
    "Tennessee Jed": [],
    "Terrapin Station": ["terrapin"],
    "That's It for the Other One": [],
    "The Eleven": ["eleven"],
    "The Last Time": [],
    "The Race Is On": ["race is on"],
    "The Same Thing": ["same thing"],
    "The Weight": ["weight"],
    "The Wheel": ["wheel"],
    "They Love Each Other": [],
    "Throwing Stones": [],
    "To Lay Me Down": [],
    "Tom Thumb's Blues": [],
    "Tomorrow Never Knows": [],
    "Tons of Steel": [],
    "Touch of Grey": ["touch of gray"],
    "Truckin'": ["truckin", "trucking", "truckin'"],
    "Turn On Your Lovelight": ["turn on your love light", "lovelight"],
    "Uncle John's Band": ["uncle johns band"],
    "Unbroken Chain": [],
    "US Blues": ["u.s. blues", "us blues"],
    "Victim or the Crime": [],
    "Viola Lee Blues": [],
    "Wang Dang Doodle": [],
    "Wave to the Wind": [],
    "Way to Go Home": [],
    "We Can Run": [],
    "Weather Report Suite": [],
    "Werewolves of London": [],
    "West L.A. Fadeaway": ["west la fadeaway", "west l.a. fadeaway"],
    "Wharf Rat": ["warf rat"],
    "What's Become of the Baby": [],
    "When I Paint My Masterpiece": ["masterpiece"],
    "Women Are Smarter": [],
    "You Win Again": [],
}

# Build a lowercase lookup: alias → canonical name
_ALIAS_MAP = {}
for canonical, aliases in CANONICAL_SONGS.items():
    _ALIAS_MAP[canonical.lower()] = canonical
    for alias in aliases:
        _ALIAS_MAP[alias.lower()] = canonical

# All canonical names for fuzzy matching
_CANONICAL_NAMES = list(CANONICAL_SONGS.keys())

# ── Non-song words ────────────────────────────────────────────────────
# After cleaning, titles matching these are classified as non-songs (song_id=NULL).
_NON_SONG_WORDS = frozenset({
    "tuning", "tune up", "tune-up",
    "crowd", "crowd noise", "audience",
    "encore break", "set break", "intermission", "break",
    "banter", "stage banter", "stage talk", "rap",
    "dead air", "silence", "blank",
    "noodling", "noodle", "warm up", "warmup", "warm-up", "soundcheck",
    "intro", "introduction", "introductions", "band introductions",
    "band introduction", "band intro",
    "applause", "cheering",
    "fade in", "fade out", "fade-in", "fade-out", "fades in", "fades out",
    "tape flip", "tape break", "tape change",
    "set up", "setup",
    "announcements", "announcement", "mc",
    "preshow", "pre-show", "pre show",
    "radio interview", "radio interviews", "interview",
    "commentary", "spoken word",
    "rain delay",
    "unknown", "untitled",
    "not available",
    "missing",
})


def _is_non_song(title):
    """Check whether a cleaned title is a non-song (tuning, crowd, etc.).

    Handles compound forms like "crowd/tuning", "Crowd & Tuning",
    "Encore Break/Crowd/Tuning" by splitting on delimiters and checking
    if ALL parts are non-song words.

    Also catches "X tuning" patterns (e.g. "Polka Tuning", "Beer Barrel
    Polka tuning") — any title whose final word is a non-song keyword.
    """
    lower = title.lower().strip()
    if not lower:
        return True
    # Direct match
    if lower in _NON_SONG_WORDS:
        return True
    # Compound: split on /, &, " and ", " + ", "-" (when surrounded by spaces)
    parts = re.split(r'\s*/\s*|\s*&\s*|\s+and\s+|\s*\+\s*|\s+-\s+', lower)
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) > 1 and all(p in _NON_SONG_WORDS for p in parts):
        return True
    # Ends with a non-song keyword: "Polka Tuning", "Beer Barrel Polka tuning",
    # "Bill Graham intro", "Bobby Banter"
    _TRAILING_NON_SONG = {"tuning", "crowd", "banter", "stage talk",
                           "dead air", "noodling", "soundcheck",
                           "introduction", "introductions", "applause",
                           "crowd noise", "warmup", "warm-up"}
    for keyword in _TRAILING_NON_SONG:
        if lower.endswith(" " + keyword) or lower.endswith("/" + keyword):
            return True
    return False


def clean_title(raw):
    """Strip track numbers, segue markers, set annotations, normalize quotes.

    Returns empty string for:
    - Multi-song combo tracks (e.g. "Help > Slip > Franklin's")
    - Non-song tracks (tuning, crowd, banter, etc.)
    """
    s = raw.strip()
    # Take only the first line (discard venue/date info on subsequent lines)
    s = s.split("\n")[0].strip()
    # Strip trailing backslashes (archive.org escaped newlines)
    s = s.rstrip('\\')

    # Remove bracketed metadata labels like [crowd], [tuning], [signals]
    s = re.sub(r'^\[.*\]$', '', s).strip()
    # Strip surrounding dashes/hyphens: "- encore break -", "--dead air--"
    s = re.sub(r'^[-–—]+\s*', '', s)
    s = re.sub(r'\s*[-–—]+$', '', s)

    # Strip surrounding parens from non-song-like entries: "(Tuning)", "(fade in)"
    s = re.sub(r'^\(([^)]+)\)$', r'\1', s)

    # ── Leading reel markers "//" ──
    # "//St. Stephen", "// Gimme Some Lovin'"
    s = re.sub(r'^//\s*', '', s)

    # ── Encore prefix "e:" or "Encore:" ──
    # "e: Keep Your Day Job", "Encore: U.S. Blues", "** E: U. S. Blues"
    s = re.sub(r'^[\s*]*[Ee]:\s*', '', s)
    s = re.sub(r'^[Ee]ncore:\s*', '', s)

    # ── Timestamp prefix "##:##]" or "##:##.##|" ──
    # "00:11] tuning/dead air", "01:16] crowd and tuning", "1:03] crowd"
    # "10:16.41| Wharf Rat", "1:13.70| Tuning"
    s = re.sub(r'^\d{1,3}(?::\d{2})*(?:\.\d+)?\s*[]\|]\s*', '', s)
    # "12:54 ] Drums" — with space before bracket
    s = re.sub(r'^\d{1,3}:\d{2}\s+\]\s*', '', s)

    # ── Disc###-Song format ──
    # "Disc103-CC Rider", "Disc301-Iko Iko"
    s = re.sub(r'^Disc\d+-', '', s, flags=re.IGNORECASE)

    # ── t01.Song format ──
    # "t01.Set Up", "t03.CC Rider"
    s = re.sub(r'^t\d+\.\s*', '', s, flags=re.IGNORECASE)

    # ── Date-prefix tracks → drop ──
    # "05/85 - Thursday", "11/84 Augusta Civic Center", "95-02-20 211 Crowd"
    if re.match(r'^\d{1,2}[-/]\d{2,4}\s', s):
        return ""
    # "95-02-20 211 Crowd" — YYMMDD prefix
    if re.match(r'^\d{2}-\d{2}-\d{2}\s', s):
        return ""

    # ── Leading asterisks and slashes (recording notes) ──
    # "*Desolation Row", "/Saint Stephen*", "(e) Gloria*"
    s = re.sub(r'^[\s(e)]*[*/]+\s*', '', s)

    # ── Multi-song combo tracks → drop entirely ──
    # Tracks like "Help > Slip > Franklin's" or "Drums > Space" combine
    # multiple songs into one track.  Other releases split them properly,
    # so we drop combos rather than trying to extract a single song.
    # Match: "Song > Song" or "Song -> Song" or "Song → Song"
    # (with at least one letter on each side of the arrow).
    # Exclude tape-flip annotations like "Dru..ms > (Tape Flip)"
    # and "S..pace > (Tape Flip Near Start)" — those are single songs.
    if re.search(r'[A-Za-z\'\"]\s*(?:->|→|>)\s*[A-Za-z(]', s) \
       and '(Tape Flip' not in s:
        return ""

    # Remove leading track numbers like "1.", "01.", "1)", "12 ."
    s = re.sub(r"^\d+\s*[\.\)]\s*", "", s)
    # Strip archive.org-style prefixes:
    #   "d1t01 - Title", "d2t05. Title" (disc/track notation)
    #   "gd77-05-08d1t01 - Title" (identifier prefix)
    #   "gd81-12-28 s2t07 Title" (space-separated set/track notation)
    #   "gd79-07-01 s1 t02 Title" (space between set and track)
    #   "gd73-06-22 t01 Title" (track-only, no disc/set prefix)
    #   "GD 1987-03-22.GEMS.d01t01" (full identifier as title, no song name)
    # Aggressive stripping: entire identifier as title (no song name)
    # "GD 1987-03-22.GEMS.d01t01", "GD-Disc02,Track11", "GD1989-07-17trk02"
    # Full identifier as entire title (no song follows): drop
    s = re.sub(r'^gd[\s\-]?\d{2,4}[\-.\s]\S*$', '', s, flags=re.IGNORECASE).strip()
    # "gd19790902.18.stella blue" — compact date.track.song
    s = re.sub(r'^gd\d{8}\.\d+\.', '', s, flags=re.IGNORECASE)
    # "GD1995-03-19 05. Don't Ease" — full date with track number
    s = re.sub(r'^gd\d{4}-\d{2}-\d{2}\s+\d+\.\s*', '', s, flags=re.IGNORECASE)
    # "gd94-03-21 12 Liberty" — 2-digit year date with track number
    s = re.sub(r'^gd\d{2}-\d{2}-\d{2}\s+\d+\s+', '', s, flags=re.IGNORECASE)
    # "GD 01 6-18-83 ..." or "GD 02 6-18-83 ..." (numbered file dumps)
    s = re.sub(r'^gd\s+\d+\s+\d{1,2}-\d{1,2}-\d{2,4}\b.*$', '', s, flags=re.IGNORECASE).strip()
    s = re.sub(r'^gd\d{2,4}-?\d{2}-?\d{2}\s*(?:[ds]\d+\s*)?t\d+\s*[-–—.]?\s*',
               '', s, flags=re.IGNORECASE)
    # "gd88-06-25 Sugaree" — date followed directly by song (no track number)
    # Must come AFTER the more specific set/track patterns above
    s = re.sub(r'^gd\d{2,4}-?\d{2}-?\d{2}\s+(?![ds]\d)', '', s, flags=re.IGNORECASE)
    s = re.sub(r'^d\d+t\d+\s*[-–—.]\s*', '', s, flags=re.IGNORECASE)
    # "Disc01,Track01 Title" or "Disc02,Track03 Title" (comma-separated)
    # Also "GD-Disc02,Track11" (with GD prefix)
    s = re.sub(r'^(?:gd[\s\-]?)?Disc\d+\s*,\s*Track\d+\s*', '', s, flags=re.IGNORECASE)
    # Bare disc/track codes with no song: "D1T12", "D2T05", "disc305"
    if re.match(r'^D\d+T?\d*$', s, flags=re.IGNORECASE):
        return ""
    if re.match(r'^disc\d+$', s, flags=re.IGNORECASE):
        return ""
    # Date-disc-track identifiers: "4-26-69d1t03"
    if re.match(r'^\d{1,2}-\d{1,2}-\d{2,4}[dD]\d+[tT]\d+', s):
        return ""
    # Spelled-out disc/track: 'Disc five, track seven: "Jam into Days Between'
    s = re.sub(r'^Disc\s+\w+\s*,\s*track\s+\w+\s*:\s*', '', s, flags=re.IGNORECASE)
    # Clean tape-flip dotted names: "Dru..ms" → "Drums", "S..pace" → "Space"
    s = re.sub(r'\.\.+', '', s)

    # ── Disc-dash-track: "2-01 Tuning" ──
    s = re.sub(r'^\d+-\d+\s+', '', s)
    # ── Underscore separator: "02_Mississippi Half-Step" ──
    s = re.sub(r'^\d+_', '', s)

    # ── Bare track number "NN Song" or "NNN Song" ──
    # "01 Hell In A Bucket", "14 Drumz", "100 tuning", "900 crowd"
    # Must come after disc/track prefix stripping. Only match when
    # the rest starts with a letter (avoid stripping "29 Rainy Day Women #12...")
    s = re.sub(r'^\d{1,3}\s+(?=[A-Za-z(])', '', s)

    # "01 - Title" or "02 – Title" (number + spaced dash, distinct from "01." above)
    s = re.sub(r'^\d+\s+[-–—]\s+', '', s)
    # Normalize quotes: convert all fancy quotes to straight
    s = s.replace("\u2018", "'").replace("\u2019", "'")
    s = s.replace("\u201c", '"').replace("\u201d", '"')
    # Remove trailing footnote markers like [a], [b], [1]
    s = re.sub(r'\s*\[[a-z0-9]+\]\s*$', '', s)

    # ── Trailing symbols: asterisks, #, ~, + ──
    # "Wang Dang Doodle *", "encore break~~", "All Along The Watchtower ->*"
    # Strip trailing *, #, ~, + and combinations (but preserve song-internal ones
    # like "Slipknot!" or "Rainy Day Women #12 And #35")
    s = re.sub(r'\s*[->=→]*\s*[*#~+]+\s*$', '', s)
    # Also handle leading (e) prefix: "(e) Gloria*" → "Gloria"
    s = re.sub(r'^\(e\)\s*', '', s)

    # ── Recording metadata annotations ──
    # "(2 AUD Matrix)", "(audience recording)", "(Aud patch)",
    # "(some music lost in the flip-spliced) (audience section edited)"
    s = re.sub(r'\s*\((?:\d+\s+)?(?:AUD|SBD|aud|sbd|audience|Aud)[^)]*\)\s*', '', s,
               flags=re.IGNORECASE)
    # "(X)Casey Jones(audience recording)" — leading (X) marker
    s = re.sub(r'^\(X\)\s*', '', s, flags=re.IGNORECASE)

    # ── Tape flip annotations ──
    # "(Tape Flip After Song)", "(Tape Flip)", "(tape flip)"
    s = re.sub(r'\s*\((?:[Tt]ape\s+[Ff]lip[^)]*)\)', '', s)

    # ── Duration in brackets "[6:05]" ──
    # "Saint Stephen [6:05]", "Bertha [4:52] ;"
    s = re.sub(r'\s*\[\d+:\d{2}\]\s*;?\s*', '', s)

    # ── Trailing ", Set Break" / "Announcements, Set Break" ──
    s = re.sub(r',\s*[Ss]et\s+[Bb]reak\s*$', '', s)

    # Remove segue markers FIRST (before duration, since → may follow duration)
    # Handle both > and -> variants
    s = re.sub(r'\s*-?[>→]+\s*$', '', s)
    # Remove trailing duration like – 14:35 or - 5:32
    s = re.sub(r'\s*[–\-—]\s*\d+:\d{2}(?::\d{2})?\s*$', '', s)
    # Remove trailing writer credits: " (writers) with optional segue marker between
    s = re.sub(r'"\s*-?[>→]?\s*\([^)]+\)\s*$', '', s)
    # Remove trailing " - or " – (e.g. 'St. Stephen" -')
    s = re.sub(r'"\s*[–\-—]\s*$', '', s)
    # Catch-all: if a bare " remains followed by metadata (writers, duration, etc.)
    # truncate at the " — the title is everything before it
    s = re.sub(r'"\s*-?[>→(–\-—].*$', '', s)
    # Remove trailing ", part N" (e.g. 'Space", part 1')
    s = re.sub(r'",?\s*part\s+\d+\s*$', '', s, flags=re.IGNORECASE)
    # Remove set annotations like "[Set 1]" or "(Set 2)"
    s = re.sub(r"\s*[\[\(](?:Set|Disc|Encore)\s*\d*[\]\)]", "", s, flags=re.IGNORECASE)
    # Remove parenthetical reel/track metadata like "(reel #2 side B; 8-track 15 ips)"
    s = re.sub(r'\s*\(reel\s+[^)]+\)', '', s, flags=re.IGNORECASE)
    # Strip surrounding matched quote pairs (but not lone apostrophes like Truckin')
    if (s.startswith('"') and s.endswith('"')) or \
       (s.startswith("'") and s.endswith("'") and len(s) > 2):
        s = s[1:-1]
    # Strip a lone leading double-quote left after writer-credits stripping
    elif s.startswith('"') and '"' not in s[1:]:
        s = s[1:]
    # Strip segment labels for songs split across a show (Category B splits).
    # These are labeled parts of ONE performance (e.g. Dark Star V1/V2) and
    # must resolve to the same canonical song. Do NOT strip "Reprise" — that
    # indicates a musically distinct song (Category A, see CONCEPTS.md).
    s = re.sub(r'\s*\(?(V\d+|verse\s+\d+|part\s+\d+|continued)\)?\s*$', '', s,
               flags=re.IGNORECASE)
    # Final cleanup: segue markers that may remain after other stripping
    s = re.sub(r'\s*-?[>→]+\s*$', '', s)
    # Strip any remaining trailing asterisks/symbols after all other cleanup
    s = re.sub(r'[*#~]+\s*$', '', s)
    # Collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()

    # ── Non-song classification ──
    # After all cleaning, check if the result is a non-song and return ""
    if _is_non_song(s):
        return ""

    # ── Long descriptions / not real song names ──
    # Real song titles are rarely > 60 chars. Long strings are usually tape notes,
    # venue descriptions, or recording metadata.
    if len(s) > 80:
        return ""

    # ── Remaining identifier patterns ──
    # Titles that are mostly numbers/punctuation with few letters
    letters = sum(1 for c in s if c.isalpha())
    if letters < 3 and len(s) > 3:
        return ""

    return s


def normalize_song(conn, raw_title):
    """Resolve a raw track title to a (song_id, canonical_name, match_type) tuple.

    match_type is one of: 'exact', 'alias', 'fuzzy', 'new'
    """
    cleaned = clean_title(raw_title)
    if not cleaned:
        return None, None, None

    # Reject titles that are purely punctuation or too short to be a song name
    if len(cleaned) < 2 or not re.search(r'[a-zA-Z]', cleaned):
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
        matched_lower = matches[0]
        canonical = _ALIAS_MAP[matched_lower]
        ratio = difflib.SequenceMatcher(None, lower, matched_lower).ratio()
        alias_type = "auto_fuzzy" if ratio >= FUZZY_AUTO_THRESHOLD else "fuzzy_flagged"
        song_id = db.get_or_create_song(conn, canonical)
        db.add_alias(conn, lower, song_id, alias_type)
        return song_id, canonical, "fuzzy"

    # 5. Fuzzy match against established DB songs (>=50 tracks)
    db_songs = conn.execute(
        """SELECT s.canonical_name
           FROM songs s
           JOIN tracks t ON t.song_id = s.id
           GROUP BY s.id
           HAVING COUNT(t.id) >= 50"""
    ).fetchall()
    if db_songs:
        db_names = [row["canonical_name"] for row in db_songs]
        db_matches = difflib.get_close_matches(
            lower, [n.lower() for n in db_names],
            n=1, cutoff=FUZZY_AUTO_THRESHOLD,
        )
        if db_matches:
            matched_lower = db_matches[0]
            # Find the original-cased canonical name
            canonical = next(n for n in db_names if n.lower() == matched_lower)
            song_id = db.get_or_create_song(conn, canonical)
            db.add_alias(conn, lower, song_id, "auto_fuzzy_db")
            return song_id, canonical, "fuzzy"

    # 6. No match — create new song entry
    song_id = db.get_or_create_song(conn, cleaned)
    db.add_alias(conn, lower, song_id, "variant")
    return song_id, cleaned, "new"


def prune_rare_songs(conn, min_tracks=3):
    """Null out song_id for songs with fewer than min_tracks tracks.

    After processing ~18K archive recordings, real songs appear in many
    recordings. Songs with very few tracks are almost certainly junk —
    tape notes, venue descriptions, stage patter, etc.

    Also removes orphan songs (0 tracks) that are non-songs or not in
    the canonical dictionary.

    Returns the number of songs pruned.
    """
    # Find songs below threshold (including songs with 0 tracks via LEFT JOIN)
    rare = conn.execute(
        """SELECT s.id, s.canonical_name, COUNT(t.id) AS cnt
           FROM songs s
           LEFT JOIN tracks t ON t.song_id = s.id
           GROUP BY s.id
           HAVING cnt < ?""",
        (min_tracks,),
    ).fetchall()

    pruned = 0
    for row in rare:
        song_id = row["id"]
        name_lower = row["canonical_name"].lower()
        # Don't prune songs in the canonical dictionary — those are known real songs
        # even if they only appear rarely in the archive
        if name_lower in _ALIAS_MAP:
            continue
        # Null out the song_id on all tracks for this song
        conn.execute("UPDATE tracks SET song_id = NULL WHERE song_id = ?", (song_id,))
        # Delete the song and its aliases
        conn.execute("DELETE FROM song_aliases WHERE song_id = ?", (song_id,))
        conn.execute("DELETE FROM songs WHERE id = ?", (song_id,))
        pruned += 1

    conn.commit()
    return pruned
