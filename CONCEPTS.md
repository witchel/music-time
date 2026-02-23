# Grateful Dead Timings: Key Concepts

This document describes domain concepts that shape how data is scraped,
stored, and analyzed. Understanding these is essential before changing the
pipeline.

---

## 1. Song Name Aliases

A single song can appear under many different names across releases:

| Canonical name | Common variants |
|---|---|
| Playing in the Band | Playin' in the Band, Playin in the Band |
| Going Down the Road Feeling Bad | Goin' Down the Road Feelin' Bad, GDTRFB |
| Half-Step Mississippi Uptown Toodleloo | Mississippi Half-Step Uptown Toodeloo, Half-Step |
| Truckin' | Truckin, Trucking |

The normalization pipeline in `normalize.py` resolves these in order:

1. **DB alias table** (`song_aliases`) — includes manual corrections
2. **Static dictionary** (`CANONICAL_SONGS`) — ~180 songs with known aliases
3. **Case-insensitive DB lookup** — catches exact matches with different casing
4. **Fuzzy match** via `difflib` — auto-accepts above 0.85 similarity, flags
   for review above 0.65
5. **New entry** — if nothing matches, creates a fresh canonical song

After scraping, run `gdtimings normalize --unmatched` to find titles that
fell through to step 5. These are often misspellings or unusual variants that
need a manual alias added to `CANONICAL_SONGS`.

### Pitfalls

- **Punctuation matters.** "Don't Ease Me In" vs "Dont Ease Me In" — the
  static dictionary must list both.
- **"The" prefix.** "The Wheel" vs "Wheel", "The Other One" vs "Other One".
  Always pick one canonical form and list the other as an alias.
- **Abbreviations.** "GDTRFB", "NFA" — these won't fuzzy-match; they must
  be in the static alias list.

---

## 2. Split Songs, Reprises, and Drums Sandwiches

The Grateful Dead frequently split a song across a show, performing part of it
in one slot and returning to it later.

### Two kinds of "split" — and they need opposite treatment

Not all multi-segment performances are the same. Some splits are musically
distinct songs that happen to share a parent; others are a single performance
chopped into labeled parts. The system must handle both.

#### Category A: Distinct related songs — keep separate

These are separate compositions (or at least separate musical sections) that
have their own identity. They should be **separate canonical entries** with
independent timing statistics.

| Parent | Related song | Notes |
|---|---|---|
| Playing in the Band | Playing in the Band Reprise | The reprise is almost always under 5 min; the main PITB is often 15-25 min. Musically distinct. |
| Sugar Magnolia | Sunshine Daydream | Sunshine Daydream is the coda/outro, sometimes split to a separate track or even a separate set. Already a separate canonical entry. |
| Help on the Way | Slipknot! / Franklin's Tower | Three distinct compositions, always separate entries. |
| Terrapin Station | Lady with a Fan | Sometimes listed as "Terrapin Station Part 1"; Lady with a Fan is the narrative section. |

For these, the normalizer should resolve each to its own canonical name. "PITB
Reprise" is not "PITB" — it's its own song.

#### Category B: Drums sandwiches — sum segments

A "Drums sandwich" occurs when a song is interrupted by a contiguous
Drums/Space sequence and then resumes:

    PITB (20 min) → Drums (10 min) → Space (5 min) → PITB (15 min)

The total PITB duration for this show is **35 minutes** (20 + 15), not 20.

`detect_sandwiches()` in `analyze.py` scans each release's ordered tracklist
for this pattern. When found, it writes:
- `sandwich_duration = sum of all segments` on the **first** segment's track
- `sandwich_duration = 0` on continuation segments (excluded from MAX/SUM)

The `all_performances` view and `_per_show_durations()` both prefer
`sandwich_duration` via `COALESCE(NULLIF(t.sandwich_duration, 0), t.duration_seconds)`.

**Scope**: Only contiguous Drums/Space interruptions count. If a different song
intervenes between the two appearances (Song X → Other Song → Song X), that's
a reprise (Category A), not a sandwich.

#### Category C: Segment labels — same song, already handled

Labeled segments like "Dark Star V1" / "Dark Star V2" all resolve to the same
canonical song via `clean_title()` stripping (`V1`, `V2`, `verse N`, `Part N`,
`continued`). Within a single release, `MAX(duration_seconds)` picks the
longest segment. If they form a Drums sandwich, `detect_sandwiches()` sums
them instead.

Contrast with "Reprise" which should **not** be stripped — it indicates a
distinct song (Category A).

### Why outlier detection order matters

Outlier detection runs **after** sandwich detection and per-show aggregation.
Without aggregation, every 10-minute Dark Star segment looks like an anomaly
compared to full 25-minute performances.

---

## 3. Segues

A segue (notated `>` or `→` in setlists) means one song transitions directly
into the next without a break. Examples:

- China Cat Sunflower > I Know You Rider
- Scarlet Begonias > Fire on the Mountain
- Help on the Way > Slipknot! > Franklin's Tower

Segues are tracked per-track in the `segue` column (1 = this track segues into
the next). They matter for analysis because:

- Segued songs may have less distinct boundaries, making individual durations
  less precise
- Some song pairs are almost always played together (China Cat > Rider), so
  their combined duration may be more stable than either alone
- The transition itself takes real time that gets attributed to one song or the
  other depending on the source

---

## 4. Drums > Space

"Drums" and "Space" are improvisational segments that appeared in nearly every
second set from 1978 onward. They are treated as songs for timing purposes,
but they're qualitatively different:

- **Drums** — percussive, often featuring Mickey Hart and Bill Kreutzmann alone
- **Space** — ambient/experimental, often featuring the full band

Wikipedia listings may show these as:
- Separate tracks: "Drums" and "Space"
- Combined: "Drums/Space" or "Drums > Space"

The alias table maps "drums/space" and "rhythm devils" to the canonical "Drums"
entry. If Drums and Space should be analyzed separately, they need distinct
canonical entries and their combined listings need to be split or excluded.

---

## 5. Complete Shows vs Edited Releases

The `coverage` column on the `releases` table classifies each release into
one of three tiers for timing reliability.

### Coverage tiers

| Value | Meaning | Use for timing? | Examples |
|---|---|---|---|
| `complete` | Full unedited show — every song at actual performance length | Yes (best data) | Dick's Picks, Dave's Picks, One from the Vault, Cornell 5/8/77 |
| `unedited` | Individual songs are unedited full-length takes, but the release is not a complete show | Yes | Fallout from the Phil Zone, Road Trips, Europe '72 Vol. 2 |
| `edited` | Songs may be trimmed, faded, overdubbed, or crossfaded | **No** — exclude from timing | Live/Dead, Skull and Roses, Without a Net, Ready or Not, Dead Set |
| `unknown` | Not yet classified | Exclude until reviewed | Unrecognized releases from the catch-all live albums category |

### How coverage is determined

Coverage is assigned at scrape time from two sources:

**Wikipedia** (discovery + coverage metadata):
1. **Per-release override** — `RELEASE_COVERAGE_OVERRIDES` in `config.py`
   maps specific Wikipedia page titles to a coverage value. This handles
   one-off releases in the catch-all `Grateful Dead live albums` category.
2. **Category default** — `CATEGORY_COVERAGE` maps each Wikipedia category
   to a default. Dick's Picks, Dave's Picks, and Download Series default to
   `complete`. Road Trips defaults to `unedited`. The catch-all live albums
   category defaults to `unknown`.

**MusicBrainz** (timing data):
- `MUSICBRAINZ_SERIES_COVERAGE` in `config.py` maps series names to coverage
  values, mirroring the Wikipedia category defaults.

### Why "unedited" matters

Many official releases compile songs from multiple shows without a complete
setlist from any single night. Examples:

- **Fallout from the Phil Zone** — Phil Lesh's handpicked favorites spanning
  decades. Each track is a full unedited performance.
- **Road Trips** — typically compiled from a tour leg, but individual songs
  are full-length soundboard recordings.
- **Europe '72 Volume 2** — 20 tracks from the 1972 tour, no overlap with
  the original (overdubbed) Europe '72.

These are valid timing sources. A 25-minute Dark Star from *Fallout from the
Phil Zone* is just as reliable as one from a Dick's Picks complete show.

The key question is whether the **individual song** is unedited, not whether
the release presents a complete concert.

### Impact on analysis

For computing consensus song durations, only `complete` and `unedited`
releases should be used. An edited "Dark Star" from *Live/Dead* (16 minutes,
but originally 23+ minutes) would pull the median down. The analysis layer
should filter: `WHERE coverage IN ('complete', 'unedited')`.

## 6. Data Sources and Quality

The pipeline uses three data sources, scraped in order. Each fills a
different role.

### Source hierarchy

| Source | `source_type` | `quality_rank` | Role |
|---|---|---|---|
| **Wikipedia** | `wikipedia` | 500 | Release discovery, coverage metadata, timing for single-concert releases |
| **MusicBrainz** | `musicbrainz` | 500 | **Authoritative timing data** for official releases — millisecond precision, per-disc concert dates for box sets |
| **Archive.org** | `archive` | 100–300 | Audience/SBD recordings for shows without official releases |

### Why MusicBrainz is the timing authority

MusicBrainz has structured, machine-readable data for every official Grateful
Dead release:
- Millisecond-precision durations on every track (vs Wikipedia's inconsistent
  HTML tracklist parsing)
- Concert dates embedded in disc/media titles for box sets (Wikipedia often
  stores a single release with NULL `concert_date`)
- Series endpoints for systematic enumeration (Dick's Picks, Dave's Picks)
- Standalone box set support via `MUSICBRAINZ_STANDALONE_RELEASES` — six major
  multi-concert box sets (Pacific Northwest '73-'74, Fillmore West 1969,
  July 1978, Winterland June 1977, May 1977, Giants Stadium) that aren't in
  any MusicBrainz series are scraped by release group MBID

Wikipedia remains valuable for:
- **Release discovery** — enumerating the catalog of official releases
- **Coverage classification** — `RELEASE_COVERAGE_OVERRIDES` and
  `CATEGORY_COVERAGE` are keyed to Wikipedia page titles/categories
- **Timing fallback** — single-concert releases where MusicBrainz hasn't been
  scraped yet

### Pipeline order

1. `--source wikipedia` — discovers releases, assigns coverage, inserts timing
   data as a baseline
2. `--source musicbrainz` — adds/overrides with authoritative timing data,
   splits box sets into per-concert-date releases
3. `--source archive` — adds audience/SBD recordings (lower quality_rank)

When both Wikipedia and MusicBrainz provide timing for the same concert date,
the `ROW_NUMBER()` tiebreaker picks the release with the longer duration,
which is typically the MusicBrainz entry (millisecond precision vs rounded
Wikipedia times).

### Quality ranks

The `quality_rank` field supports filtering and tiebreaking:

| Rank | Type | Notes |
|---|---|---|
| 500 | Official (Wikipedia, MusicBrainz) | Professionally mastered, most trustworthy |
| 300 | SBD (Archive.org soundboard) | Good quality, may have tape issues |
| 200 | MTX (Archive.org matrix) | Audience + soundboard blend |
| 100 | AUD (Archive.org audience) | Variable quality |

---

## 7. Multi-Night Runs

Many releases cover multiple nights at the same venue (e.g., "three nights at
the Fillmore"). These appear differently depending on the source:

**Wikipedia**: May appear as one page per night (separate releases — ideal) or
one page covering all nights (single release). In the latter case, the
`concert_date` captures only the first date from the "Recorded" infobox, so
all tracks get the same date.

**MusicBrainz**: Multi-night box sets have per-disc titles with embedded dates
(e.g., "Winterland Arena - 12/31/78"). The MusicBrainz scraper parses these
and creates **one release record per concert date**, solving the Wikipedia
single-date problem. This is the primary motivation for using MusicBrainz as
the timing authority for box sets.

---

## 8. Outlier Detection

`analyze.py` flags individual track durations as outliers if they're more than
3 standard deviations from the mean for that song. This catches:

- **Data errors** — wrong duration parsed, duration from a different song
- **Genuinely unusual performances** — a 5-minute "Dark Star" or a 30-minute
  "Playing in the Band"

Outlier detection runs **after** sandwich detection and per-show aggregation
(see section 2), since a single segment of a split song will look anomalously
short compared to full performances.

**Important**: The `best_performances` view does **not** filter on
`is_outlier`. Outlier flags are retained in the `tracks` and
`all_performances` tables for data-quality analysis, but genuine long
performances (e.g., the ~46-minute PITB from 1974-05-21) must not be excluded
from visualizations. The 3-sigma threshold is too aggressive for songs with
high natural variability.
