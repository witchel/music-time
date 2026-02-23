# Future Fixes

Known issues and improvements for future scrapes and schema changes.

## 1. Parse set_name from archive.org filenames

**Impact: High** — fills 99.3% empty `set_name` values (currently only 2,543 / 367,933 tracks have set info, from Wikipedia and MusicBrainz).

Archive.org filenames often encode disc/set information:
- `gd1977-05-08d1t01.shn` — disc 1, track 1 (typically Set 1)
- `gd1977-05-08d2t01.shn` — disc 2, track 1 (typically Set 2)
- `gd1977-05-08d3t01.shn` — disc 3, track 1 (often Encore or Set 2 continued)

The mapping isn't always exact (some shows are split differently), but disc 1 ≈ Set 1 and disc 2 ≈ Set 2 is a reasonable default. This would make the polar plot (plot 3) much more useful.

**Where to implement**: `gdtimings/archive_org.py` in `_extract_tracks()` — parse `d(\d+)t(\d+)` from filenames.

## 2. Concerts table (explicit show dedup)

**Impact: High** — eliminates the `ROW_NUMBER() OVER (PARTITION BY concert_date ORDER BY quality_rank DESC)` dedup pattern that every viz query currently needs.

Currently, 2,252 unique concert dates have 18,039 archive.org releases (mean ~8 releases per show). The same 1977-05-08 concert appears as 20+ separate releases from different tapers.

A `concerts` table keyed by `(concert_date, venue)` with a foreign key from `releases` would:
- Make "one row per show" the default
- Let you pick a "preferred release" per concert (highest quality_rank)
- Simplify all viz queries from 3-level nested subqueries to simple JOINs
- Enable proper show-level metadata (setlist, venue, weather, etc.)

**Schema sketch**:
```sql
CREATE TABLE concerts (
    id           INTEGER PRIMARY KEY,
    concert_date TEXT NOT NULL,
    venue        TEXT,
    city         TEXT,
    state        TEXT,
    UNIQUE(concert_date, venue)
);

ALTER TABLE releases ADD COLUMN concert_id INTEGER REFERENCES concerts(id);
```

**Trade-off**: This is a significant schema change requiring migration of all existing data. The `ROW_NUMBER` dedup works well enough for now.

## 3. Non-US location handling

**Impact: Low-Medium** — 576 releases have non-US state values (England, Germany, Ontario, etc.).

The `state` column stores a mix of US states (full names), Canadian provinces, and countries. This works for viz (non-US values just fall through `to_abbr()` as `None`) but is semantically messy.

Options:
- Add a `country` column (default "US") and restrict `state` to US/Canada provinces
- Rename `state` to `region` to be less US-centric
- Add a `country_code` column (ISO 3166-1 alpha-2)

The European shows (England, Germany, France, etc.) are well-known tour legs (Europe '72, etc.) so they're worth keeping queryable.

## 4. Duration outlier handling in archive.org data

**Impact: Medium** — some archive.org tracks have incorrect `length` metadata.

The `is_outlier` flag in `tracks` is populated by `gdtimings analyze`. Outlier
flags are **informational only** — `best_performances` does not filter on
`is_outlier` because the 3-sigma threshold excludes genuine long performances
(e.g., ~46-min PITB from 1974-05-21). The flags are useful for data-quality
auditing but should not be used in visualization filters.

Consider adding a basic sanity check in `_extract_tracks()`:
- Flag tracks < 10 seconds (likely applause/tuning fragments)
- Flag tracks > 60 minutes (likely concatenated or mislabeled)

## 5. Segue detection from archive.org

**Impact: Medium** — the `segue` column in tracks is 0 for all archive.org data.

Archive.org filenames sometimes indicate segues via `>` in titles (e.g., "Dark Star > St. Stephen"). Parsing this would enable segue analysis across the full dataset, not just official releases.

## 6. Song alias consolidation

**Impact: Low** — 48 tracks currently have `song_id IS NULL` (unmatched).

The fuzzy matching in `normalize_song()` catches most variants, but some archive.org titles are too creative (e.g., "DS" for Dark Star, "PITB" for Playing in the Band). A manual alias table or community-sourced mapping would close the gap.
