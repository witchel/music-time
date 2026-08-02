# music-time

## Architecture as-is

- `gdtimings/` — Grateful Dead scraper/CLI; `phishtimings/` — Phish
  counterpart; `viz/` — matplotlib visualizations (`uv run --extra viz
  python -m viz`).
- DB: `~/.gdtimings/gdtimings.db` (SQLite). Core tables: `tracks`
  (song_id, release_id, duration_seconds, sandwich_duration, title_raw),
  `songs` (canonical_name), `releases` (concert_date, concert_year,
  state, venue, source_type).
- Domain concepts (aliases, sandwiches, segues, data-source hierarchy,
  outliers) are in `CONCEPTS.md` — read it before changing the pipeline.

## Landmines / gotchas

- **GD scope is 1965–1995 only.** No reunion bands (Dead & Co, The Other
  Ones, Further, Ratdog, Phil & Friends). Jerry Garcia died 1995-08-09;
  the last GD show was 1995-07-09. Any `concert_year > 1995` in the
  gdtimings DB is either a scraper bug (publication date used as concert
  date) or reunion-era data to exclude.
- `releases.state` holds full state names ("California"); convert with
  the helpers in `gdtimings/location.py` (`normalize_state`,
  `parse_city_state`) when 2-letter codes are needed.

## DB rebuild procedure

To rebuild with clean data (e.g., after changing normalization):

1. `uv run python -m gdtimings scrape --source archive --full` —
   populates `~/.gdtimings/cache/` with all ~18k JSON files (parallel,
   ~30 min first time; later rebuilds reuse the cache, `--max-age DAYS`
   expires stale entries)
2. `rm ~/.gdtimings/gdtimings.db`
3. `uv run python -m gdtimings scrape --source wikipedia` — official
   releases first (baseline songs/aliases + coverage metadata)
4. `uv run python -m gdtimings scrape --source musicbrainz` —
   authoritative timings (ms precision, per-disc dates)
5. `uv run python -m gdtimings scrape --source archive` — from cache,
   no network
6. `uv run python -m gdtimings analyze` — sandwiches + song stats
7. `uv run python -m gdtimings status` — verify counts

## Project History

`HISTORY.md` is this repo's why-archive; the global Repository Memory policy
applies.
