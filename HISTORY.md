# Project History

A human-readable log of significant problems, breakthroughs, and design
decisions as the project evolved.  Complements `git log` with the *why*
behind the changes.

---

## 2026-02-19 — Bootstrap: Wikipedia scraper + Archive.org

Started from a simple question: how long did Grateful Dead songs actually
last in concert, and how did that change over 30 years?

**Wikipedia scraper** came first.  Parsed HTML tracklists from ~220
official release pages (Dick's Picks, Dave's Picks, Road Trips, etc.).
Immediately ran into the problem that Wikipedia markup is wildly
inconsistent — some pages use `<ol>`, some use plain text, some have
nested tables.  The `strip_tags` function had a bug where `<br>` tags
weren't converted to newlines, causing song titles to merge.

**Coverage classification** was the first real design decision.  Not all
official releases are usable for timing analysis — *Live/Dead* and
*Europe '72* were studio-overdubbed with fades and edits.  Created a
three-tier system (`complete` / `unedited` / `edited`) so the analysis
layer can filter appropriately.  The coverage overrides dict in
`config.py` grew to 30+ entries as we classified the full catalog.

**Archive.org scraper** added ~18,000 audience and soundboard recordings,
exploding the dataset from ~8K tracks to ~370K.  Used the Archive.org
scrape API with cursor-based pagination (their search API caps at 10K
results).  Built a two-phase pipeline: Phase 1 fetches metadata JSON into
a local cache (`~/.gdtimings/cache/`), Phase 2 parses the cache into
SQLite.  This means rebuilds after code changes are fast — no network
needed for the archive step once the cache is warm.

Switched from pip to **uv** on the same evening.  Never looked back.

---

## 2026-02-20 — First visualizations + the sandwich problem

**10 initial plots** generated from the SQLite data: terrain/ridgeline
chart, polar plots, geographic heatmaps, envelope charts, and
space-filling curves (Hilbert and Gosper).  The Gosper flowsnake spiral
with sunflower packing was the most visually striking — each hexagonal
tile represents one performance, sized by duration.

**The sandwich problem** surfaced immediately in the plots.  Songs like
Playing in the Band and Dark Star were frequently performed as "Drums
sandwiches" — the song opens, Drums/Space plays in the middle, then the
song resumes.  Archive.org stores each segment as a separate track:

    PITB (20 min) → Drums (10 min) → Space (5 min) → PITB (15 min)

Naive averaging across tracks produced misleading mid-range durations
instead of the true 35-minute performance.  First fix used
`MAX(duration)` per release to grab the longest segment.  Later replaced
with proper sandwich detection in `analyze.py` that sums all segments.

**Taper inflation** was the other major data quality bug.  A single
concert might have 5-10 different recordings on Archive.org (different
tapers, transfers, formats).  Without deduplication, a show with 8
tapers counted 8x in every statistic.  Fixed with `ROW_NUMBER() OVER
(PARTITION BY concert_date ORDER BY quality_rank DESC)` to pick one
release per show, preferring official releases (rank 500) over
soundboards (300) over audience recordings (100).

---

## 2026-02-21 — Centralized views + sunflower visualizations

**DB views** (`best_performances`, `all_performances`) centralized the
dedup and filtering logic that had been copy-pasted across 10 plot
queries.  The `best_performances` view chains three filters: exclude
utility songs (Drums/Space/Jam), exclude edited releases, and deduplicate
tapers — one row per (song, concert_date).

**Duration sunflowers** (Hilbert and Gosper variants) became the
signature visualization.  Each tile is one performance, arranged on a
space-filling curve, with area proportional to duration.  Getting the
packing right took many iterations — the sunflower spiral formula
`r = c * sqrt(i)` needed a size-aware variant `(i+1)^0.7` to prevent
overlap when tile sizes vary 3:1.  Inverted the ordering (longest at
center) and tuned spacing coefficients until tiles just barely kiss
without overlapping.

**Parallel fetching with JSON cache** for Archive.org — replaced serial
requests with 64-worker thread pool.  First full cache population takes
~30 minutes but only happens once.

---

## 2026-02-22 — The great title cleaning + MusicBrainz

**Song count dropped from 7,537 to 996** through aggressive title
normalization.  The raw Archive.org metadata is chaotic — track titles
include reel markers (`d1t01`), timestamps (`[0:00]`), recording notes
(`[SBD>DAT>CDR]`), encore prefixes, footnote symbols, and every
conceivable formatting variation of song names.

Built a 30-pattern `clean_title()` pipeline that strips all this noise
before fuzzy matching.  Added `_is_non_song()` to classify tuning, crowd
noise, banter, tape flips, and other non-musical tracks as NULL (no
song_id).  Expanded the canonical song dictionary from ~217 to ~270
entries with aliases.  The fuzzy matcher auto-accepts above 0.85
similarity and flags for review above 0.65.  Rare songs (<3 tracks, not
in the canonical dictionary) are pruned after scraping.

**Era-segmented sunflowers** split the visualizations by touring era
(1965-1974 / 1975-1979 / 1980-1990 / 1991-1995), revealing how the
band's improvisational approach changed over time.

**MusicBrainz scraper** added as the authoritative timing source for
official releases.  Key advantages over Wikipedia: millisecond-precision
durations (vs. Wikipedia's inconsistent HTML parsing), and per-disc
concert dates embedded in media titles for box sets.  This solved the
long-standing problem where Wikipedia stored multi-concert box sets as a
single release with NULL `concert_date`.

Two discovery mechanisms:
- **Series enumeration** — Dick's Picks, Dave's Picks, Road Trips,
  Download Series, and Europe '72 Complete Recordings via MusicBrainz
  series API (`get_series_by_id` with `release-group-rels` includes)
- **Standalone box sets** — six major multi-concert releases (Pacific
  Northwest '73-'74, Fillmore West 1969, July 1978, Winterland June
  1977, May 1977, Giants Stadium) that aren't in any series, configured
  by release group MBID in `MUSICBRAINZ_STANDALONE_RELEASES`

The series API was a stumble — the `musicbrainzngs` library doesn't have
a `get_release_group_in_series()` method despite what the naming
convention suggests.  The correct approach uses the generic
`get_series_by_id()` with relationship includes.

**Publication date bug** — discovered while validating PITB statistics
for the viz module.  58 "Playing in the Band" performances appeared in
years 1997-2026, which is impossible (Jerry Garcia died in 1995).  The
root cause: for single-concert releases (Dick's Picks, Dave's Picks,
etc.), the MusicBrainz disc titles are just "Disc 1", "Disc 2" with no
embedded date.  The date parser returned None, and the fallback used
`release.get("date")` — which is the *publication date*, not the concert
date.  Dick's Picks Volume 4 (a 1970 concert) was filed under 1996, its
release year.  This affected 127 of 151 MusicBrainz releases.

The fix was simple: remove the release-date fallback entirely.  If no
date is parseable from disc titles, skip the release.  Single-concert
releases already have correct concert dates from the Wikipedia scraper;
MusicBrainz's value for those is timing precision, which isn't worth much
when filed under the wrong year.  Box sets with disc-level dates (the 23
releases that actually need MusicBrainz) continue to work perfectly.

This is a good example of how a "reasonable fallback" can silently poison
an entire dataset.  The bug was invisible in the scraper output — every
release looked correct — but showed up immediately when checking whether
the data matched real-world constraints (the Dead didn't play after 1995).

Final DB after rebuild: **18,287 releases, 368,484 tracks, 996 songs,
325 sandwiches.  Zero post-1995 data.**
