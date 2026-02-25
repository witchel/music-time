"""phish.in scraper for fan/audience Phish recordings.

Provides ms-precision durations from the free phish.in API (2,100+ shows).
No authentication required.

Two-phase pipeline (mirrors livephish.py):
  Phase 1 — Fetch: paginated show index → per-show detail JSON to local cache
  Phase 2 — Process: parse cached JSON into SQLite (no network required)

Duplicate handling: shows whose concert_date already has a release from
MusicBrainz or LivePhish are skipped.  Those sources have official recordings
and are timing authorities.
"""

import os
import time

import requests

from gdtimings.cache import read_cache, write_cache
from gdtimings.http_utils import api_get_with_retry
from phishtimings import db
from phishtimings.config import (
    PI_CACHE_DIR,
    PI_API_BASE,
    PI_RATE_LIMIT,
    CONCERT_YEAR_MIN,
    CONCERT_YEAR_MAX,
)
from phishtimings.normalize import normalize_song


# ── Phase 1: Fetch to cache ─────────────────────────────────────────

def _fetch_show_index(session):
    """Paginate GET /shows?per_page=250 to collect all shows with audio.

    Returns list of dicts: {date, venue_name, city, state}.
    Only includes shows with audio_status == "complete".
    """
    shows = []
    page = 1

    while True:
        data = api_get_with_retry(
            session,
            f"{PI_API_BASE}/shows",
            params={"per_page": "250", "page": str(page)},
            rate_limit=PI_RATE_LIMIT,
        )

        page_shows = data.get("shows", [])
        if not page_shows:
            break

        for show in page_shows:
            if show.get("audio_status") != "complete":
                continue

            venue_obj = show.get("venue", {}) or {}
            shows.append({
                "date": show.get("date"),
                "venue_name": show.get("venue_name") or venue_obj.get("name"),
                "city": venue_obj.get("city"),
                "state": venue_obj.get("state"),
            })

        # Check if there's a next page
        total_pages = data.get("total_pages", 1)
        if page >= total_pages:
            break
        page += 1

    return shows


def _fetch_show_to_cache(session, date_str, cache_dir,
                         max_age_seconds=0, force=False):
    """Fetch show detail JSON and write to cache.

    Returns True if fetched from API, False if cache hit.
    """
    if not force and read_cache(cache_dir, date_str, max_age_seconds) is not None:
        return False

    data = api_get_with_retry(
        session,
        f"{PI_API_BASE}/shows/{date_str}",
        rate_limit=PI_RATE_LIMIT,
    )
    write_cache(cache_dir, date_str, data)
    return True


# ── Phase 2: Process cache → DB ─────────────────────────────────────

def _process_show_from_cache(conn, cached_data, existing_dates, verbose=True):
    """Parse one cached phish.in show into the DB.

    Skips if:
      - source_id already in DB (re-run safe)
      - Any release already exists for this concert_date

    Returns (releases_added, tracks_added).
    """
    date_str = cached_data.get("date")
    if not date_str:
        return 0, 0

    # Validate year range
    try:
        year = int(date_str[:4])
    except (ValueError, IndexError):
        return 0, 0
    if not (CONCERT_YEAR_MIN <= year <= CONCERT_YEAR_MAX):
        if verbose:
            print(f"    Skipping {date_str}: year {year} out of range "
                  f"[{CONCERT_YEAR_MIN}-{CONCERT_YEAR_MAX}]")
        return 0, 0

    source_id = f"pi:{date_str}"

    # Already imported this exact show
    if db.release_exists(conn, source_id):
        return 0, 0

    # Skip if any source already has this date (MB/LP are timing authorities)
    if date_str in existing_dates:
        return 0, 0

    venue_obj = cached_data.get("venue", {}) or {}
    venue_name = cached_data.get("venue_name") or venue_obj.get("name")
    city = venue_obj.get("city")
    state = venue_obj.get("state")
    title = f"phish.in: {date_str}"

    release_id = db.insert_release(
        conn,
        source_type="phishin",
        source_id=source_id,
        title=title,
        concert_date=date_str,
        venue=venue_name,
        city=city,
        state=state,
        coverage="complete",
        recording_type="audience",
        quality_rank=300,
        source_url=f"https://phish.in/{date_str}",
    )

    tracks = cached_data.get("tracks", [])
    tracks_added = 0
    for track in tracks:
        raw_title = track.get("title", "")
        if not raw_title:
            continue

        duration_ms = track.get("duration")
        duration_seconds = duration_ms / 1000.0 if duration_ms is not None else None

        set_name = track.get("set_name")  # "Set 1", "Set 2", "Encore", etc.
        position = track.get("position", 0)

        song_id, _, _ = normalize_song(conn, raw_title)

        db.insert_track(
            conn,
            release_id=release_id,
            title_raw=raw_title,
            disc_number=1,
            track_number=position,
            song_id=song_id,
            duration_seconds=duration_seconds,
            set_name=set_name,
        )
        tracks_added += 1

    conn.commit()

    if verbose:
        print(f"    {title}: {tracks_added} tracks")

    # Track this date so subsequent shows in the same run don't duplicate
    existing_dates.add(date_str)

    return 1, tracks_added


# ── Public entry point ───────────────────────────────────────────────

def scrape_all(conn, full=False, max_age_days=0, verbose=True):
    """Scrape Phish fan recordings from phish.in.

    Two-phase pipeline:
      Phase 1: Fetch show index + per-show detail JSON to local cache
      Phase 2: Parse cached JSON into SQLite (no network needed)

    Shows whose concert_date already exists in the DB (from any source)
    are skipped entirely — MusicBrainz and LivePhish are timing authorities.

    Args:
        full: If True, ignore cache and re-fetch everything.
        max_age_days: Re-fetch cache entries older than this (0 = never expire).

    Returns (total_releases, total_tracks).
    """
    cache_dir = PI_CACHE_DIR
    os.makedirs(cache_dir, exist_ok=True)
    max_age_seconds = max_age_days * 86400 if max_age_days > 0 else 0

    session = requests.Session()
    session.headers["User-Agent"] = "PhishTimingsBot/1.0 (https://github.com/phishtimings)"

    # ── Phase 1: Fetch show index + details to cache ─────────────────
    if verbose:
        print("  Phase 1: Fetching phish.in show index...")

    index = _fetch_show_index(session)
    if verbose:
        print(f"  Found {len(index)} shows with audio on phish.in")

    # Pre-load known dates so we can skip fetching detail for them
    existing_dates = db.dates_already_in_db(conn)
    to_fetch = [s for s in index if s["date"] not in existing_dates]

    if verbose:
        print(f"  {len(index) - len(to_fetch)} already in DB, "
              f"{len(to_fetch)} need detail fetch")
        if to_fetch:
            print("  Fetching show details to cache...")

    api_fetches = 0
    errors = 0
    t0 = time.time()
    for i, show in enumerate(to_fetch):
        date_str = show["date"]
        if not date_str:
            continue
        try:
            fetched = _fetch_show_to_cache(
                session, date_str, cache_dir,
                max_age_seconds=max_age_seconds,
                force=full,
            )
            if fetched:
                api_fetches += 1
        except (requests.RequestException, ValueError, KeyError) as e:
            errors += 1
            if verbose:
                print(f"    Error fetching show {date_str}: {e}")

        if verbose and (i + 1) % 100 == 0:
            elapsed = time.time() - t0
            print(f"    Phase 1 progress: {i + 1}/{len(to_fetch)} "
                  f"({api_fetches} fetched from API, {errors} errors, {elapsed:.0f}s)")

    if verbose:
        print(f"  Phase 1 complete: {api_fetches} fetched from API, "
              f"{len(to_fetch) - api_fetches - errors} from cache, {errors} errors")

    # ── Phase 2: Process cache → DB ──────────────────────────────────
    if verbose:
        print("  Phase 2: Processing cached shows into DB...")

    total_releases = 0
    total_tracks = 0

    # Re-load existing dates (phase 1 didn't change DB, but be safe)
    existing_dates = db.dates_already_in_db(conn)

    for i, show in enumerate(to_fetch):
        date_str = show["date"]
        if not date_str:
            continue

        cached_data = read_cache(cache_dir, date_str)
        if not cached_data:
            continue

        r, t = _process_show_from_cache(conn, cached_data, existing_dates,
                                        verbose=verbose)
        total_releases += r
        total_tracks += t

        if verbose and (i + 1) % 100 == 0:
            print(f"    Phase 2 progress: {i + 1}/{len(to_fetch)}, "
                  f"{total_releases} releases, {total_tracks} tracks")

    if verbose:
        print(f"  phish.in total: {total_releases} releases, {total_tracks} tracks")

    return total_releases, total_tracks
