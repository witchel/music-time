# Grateful Dead Timings: Key Concepts

This document describes domain concepts that shape how data is scraped,
stored, and analyzed. Understanding these is essential before changing the
pipeline.

---

## 1. Song Name Aliases

A single song can appear under many different names across releases:

| Canonical name | Variants seen on Wikipedia |
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

## 2. Split Songs and Reprises

**This is the most important unsolved problem in the current codebase.**

The Grateful Dead frequently split a song across a show, performing part of it
in one slot and returning to it later. For timing purposes, these segments
must be **summed per show** to get the total time spent on the song.

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

#### Category B: Same song, multiple segments — aggregate per show

These are a single song that gets interrupted (usually by Drums > Space) and
resumed later. The segments are **labeled parts of one performance** and their
durations must be **summed per show** to get the total time.

| Song | How segments appear | Notes |
|---|---|---|
| Dark Star | "Dark Star" ... Drums > Space ... "Dark Star" | Sometimes labeled V1/V2 or "verse 1"/"verse 2". A show with two 10-minute segments = 20 minutes of Dark Star. |
| The Other One | "The Other One" ... Drums > Space ... "The Other One" | Same pattern as Dark Star. |
| Playing in the Band | Rarely: PITB ... other songs ... PITB (not "Reprise") | When the same title appears twice without "Reprise", the segments should be summed. |

### What "20 minutes of Dark Star" means

If a show has:
- Track 5: "Dark Star" — 10:32
- Track 9: "Dark Star" — 9:48

The **per-show duration** of Dark Star is **20:20**, not two separate 10-minute
data points. Currently, `analyze.py` treats each track row as an independent
sample, which **understates** typical song durations for split songs and
**overstates** the number of times played.

### Segment label normalization

The scraper needs to recognize that labeled segments all resolve to the
**same canonical song** so they can be aggregated:

- `"Dark Star V1"`, `"Dark Star V2"` → Dark Star
- `"Dark Star (verse 1)"` → Dark Star
- `"The Other One (Part 2)"` → The Other One
- `"Dark Star (continued)"` → Dark Star

These suffixes (`V1`, `V2`, `verse N`, `Part N`, `continued`) should be
stripped in `clean_title` before alias matching. Contrast with "Reprise"
which should **not** be stripped — it indicates a distinct song (Category A).

### How to fix analysis

The analysis layer should aggregate Category B durations by (song_id,
release_id) before computing statistics:

```sql
-- Per-show total duration for each song
SELECT song_id, release_id,
       SUM(duration_seconds) AS show_duration,
       COUNT(*)              AS segment_count
FROM tracks
WHERE duration_seconds IS NOT NULL
GROUP BY song_id, release_id
```

Songs with `segment_count > 1` are split performances. The `show_duration` is
the meaningful number for timing statistics. Category A songs (PITB vs PITB
Reprise) already have different `song_id` values, so the GROUP BY naturally
keeps them separate — no special handling needed.

### Why outlier detection order matters

Outlier detection should run **after** per-show aggregation. Without
aggregation, every 10-minute Dark Star segment looks like an anomaly compared
to full 25-minute performances.

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
one of three tiers for timing reliability. This is stored at scrape time
based on the Wikipedia category and per-release overrides in `config.py`.

### Coverage tiers

| Value | Meaning | Use for timing? | Examples |
|---|---|---|---|
| `complete` | Full unedited show — every song at actual performance length | Yes (best data) | Dick's Picks, Dave's Picks, One from the Vault, Cornell 5/8/77 |
| `unedited` | Individual songs are unedited full-length takes, but the release is not a complete show | Yes | Fallout from the Phil Zone, Road Trips, Europe '72 Vol. 2 |
| `edited` | Songs may be trimmed, faded, overdubbed, or crossfaded | **No** — exclude from timing | Live/Dead, Skull and Roses, Without a Net, Ready or Not, Dead Set |
| `unknown` | Not yet classified | Exclude until reviewed | Unrecognized releases from the catch-all live albums category |

### How coverage is determined

The scraper resolves coverage in two steps (see `scrape_album` in
`wikipedia.py`):

1. **Per-release override** — `RELEASE_COVERAGE_OVERRIDES` in `config.py`
   maps specific Wikipedia page titles to a coverage value. This handles
   one-off releases in the catch-all `Grateful Dead live albums` category.
2. **Category default** — `CATEGORY_COVERAGE` maps each Wikipedia category
   to a default. Dick's Picks, Dave's Picks, and Download Series default to
   `complete`. Road Trips defaults to `unedited` (songs are unedited but
   often compiled from multiple shows). The catch-all live albums category
   defaults to `unknown`.

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

### Future sources

Wikipedia is the first data source, but others (e.g., Internet Archive) will
follow. Each source will need its own coverage classification. The `coverage`
column applies at the release level regardless of source.

### Impact on analysis

For computing consensus song durations, only `complete` and `unedited`
releases should be used. An edited "Dark Star" from *Live/Dead* (16 minutes,
but originally 23+ minutes) would pull the median down. The analysis layer
should filter: `WHERE coverage IN ('complete', 'unedited')`.

## 6. Recording Sources and Quality

Not all duration data is equally trustworthy:

| Source | Quality | Notes |
|---|---|---|
| Dick's Picks | High | Official release, professionally mastered, times from liner notes |
| Dave's Picks | High | Same as Dick's Picks |
| Road Trips | High | Official multi-disc releases |
| Download Series | High | Official digital releases |
| Other live albums | Medium | May be compilations or partial shows |

The `quality_rank` field in `releases` (500 = official) supports filtering.
When computing consensus timings, higher-quality sources should be preferred,
or at minimum the source quality should be available for weighting.

---

## 7. Multi-Night Runs

Many releases cover multiple nights at the same venue (e.g., "three nights at
the Fillmore"). These may appear as:
- One Wikipedia page per night (separate releases) — ideal
- One page covering all nights (single release, multiple discs) — disc numbers
  map to nights

The `concert_date` field captures the first date from the "Recorded" infobox
field. For multi-night releases, this means all tracks get the same date, which
is imprecise but usually acceptable for timing analysis.

---

## 8. Outlier Detection

`analyze.py` flags individual track durations as outliers if they're more than
3 standard deviations from the mean for that song. This catches:

- **Data errors** — wrong duration parsed, duration from a different song
- **Genuinely unusual performances** — a 5-minute "Dark Star" or a 30-minute
  "Playing in the Band"

Outlier detection should run **after** split-song aggregation (see section 2),
since a single segment of a split song will look anomalously short compared to
full performances.
