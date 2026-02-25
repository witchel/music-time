"""LivePhish.com scraper for Phish live releases.

Provides second-precision durations from the official LivePhish streaming
catalog (904 shows as of 2025).  No authentication required.

Two-phase pipeline (mirrors musicbrainz.py):
  Phase 1 — Fetch: catalog search → per-show detail JSON to local cache
  Phase 2 — Process: parse cached JSON into SQLite (no network required)

Duplicate handling: shows whose concert_date already has a release from
any source are skipped.  MB and phish.in run first → timing authorities.
"""

import os
import re

import requests

from gdtimings.cache import read_cache, write_cache
from gdtimings.http_utils import api_get_with_retry
from phishtimings import db
from phishtimings.config import (
    LP_CACHE_DIR,
    LP_API_BASE,
    LP_RATE_LIMIT,
    LP_USER_AGENT,
    CONCERT_YEAR_MIN,
    CONCERT_YEAR_MAX,
)
from phishtimings.normalize import normalize_song


# ── Helpers ──────────────────────────────────────────────────────────

def _parse_lp_date(date_str):
    """Convert LivePhish date "MM/DD/YYYY" → ISO "YYYY-MM-DD".

    Returns None if parsing fails or year is out of range.
    """
    if not date_str:
        return None
    m = re.match(r'(\d{1,2})/(\d{1,2})/(\d{4})', date_str)
    if not m:
        return None
    month, day, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if not (CONCERT_YEAR_MIN <= year <= CONCERT_YEAR_MAX):
        return None
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def _set_name_from_num(set_num):
    """Convert LivePhish numeric setNum to a display name.

    1→"Set 1", 2→"Set 2", 3→"Set 3", 4→"Encore",
    5+→"Encore N-3", 0/None→None.
    """
    if not set_num:
        return None
    n = int(set_num)
    if n <= 0:
        return None
    if n <= 3:
        return f"Set {n}"
    if n == 4:
        return "Encore"
    return f"Encore {n - 3}"


# ── Phase 1: Fetch to cache ─────────────────────────────────────────

def _fetch_catalog(session):
    """Fetch the full LivePhish catalog (single API call).

    Navigates the nested response structure:
      Response.catalogSearchTypeContainers[]
        .catalogSearchContainers[]
          .catalogSearchResultItems[]

    Filters to artistName == "Phish".
    Returns flat list of item dicts.
    """
    data = api_get_with_retry(
        session,
        LP_API_BASE,
        params={
            "method": "catalog.search",
            "searchStr": "phish",
            "containerType": "1",
            "pageSize": "5000",
        },
        rate_limit=LP_RATE_LIMIT,
    )

    items = []
    response = data.get("Response", data.get("response", {}))
    for type_container in response.get("catalogSearchTypeContainers", []):
        for search_container in type_container.get("catalogSearchContainers", []):
            for item in search_container.get("catalogSearchResultItems", []):
                if item.get("artistName", "").lower() == "phish":
                    items.append(item)
    return items


def _fetch_container_to_cache(session, container_id, cache_dir,
                              max_age_seconds=0, force=False):
    """Fetch show detail JSON and write to cache.

    Returns True if fetched from API, False if cache hit.
    """
    cache_key = str(container_id)

    if not force and read_cache(cache_dir, cache_key, max_age_seconds) is not None:
        return False

    data = api_get_with_retry(
        session,
        LP_API_BASE,
        params={
            "method": "catalog.container",
            "containerID": str(container_id),
            "vdisp": "1",
        },
        rate_limit=LP_RATE_LIMIT,
    )
    write_cache(cache_dir, cache_key, data)
    return True


# ── Phase 2: Process cache → DB ─────────────────────────────────────

def _process_container_from_cache(conn, cached_data, existing_dates, verbose=True):
    """Parse one cached LivePhish show into the DB.

    Skips if:
      - source_id already in DB (re-run safe)
      - Any source already has a release for this concert_date

    Returns (releases_added, tracks_added).
    """
    response = cached_data.get("Response", cached_data.get("response", {}))
    container_id = response.get("containerID") or response.get("containerid")
    if not container_id:
        return 0, 0

    perf_date = response.get("performanceDate", "")
    concert_date = _parse_lp_date(perf_date)
    if not concert_date:
        return 0, 0

    source_id = f"lp:{container_id}"

    # Already imported this exact show
    if db.release_exists(conn, source_id):
        return 0, 0

    # Skip if any source already has this date (MB/phish.in are timing authorities)
    if concert_date in existing_dates:
        return 0, 0

    venue = response.get("venueName") or None
    city = response.get("venueCity") or None
    state = response.get("venueState") or None
    title = response.get("containerInfo", "") or f"LivePhish: {perf_date}"

    release_id = db.insert_release(
        conn,
        source_type="livephish",
        source_id=source_id,
        title=title,
        concert_date=concert_date,
        venue=venue,
        city=city,
        state=state,
        coverage="complete",
        recording_type="official",
        quality_rank=500,
        source_url=f"https://livephish.com/browse/music/0,{container_id}/",
    )

    tracks = response.get("tracks", [])
    tracks_added = 0
    for track in tracks:
        raw_title = track.get("songTitle", "")
        if not raw_title:
            continue

        duration = track.get("totalRunningTime")
        if duration is not None:
            duration = float(duration)

        set_num = track.get("setNum")
        set_name = _set_name_from_num(set_num)
        disc_num = int(track.get("discNum", 1) or 1)
        track_num = int(track.get("trackNum", 0) or 0)

        song_id, _, _ = normalize_song(conn, raw_title)

        db.insert_track(
            conn,
            release_id=release_id,
            title_raw=raw_title,
            disc_number=disc_num,
            track_number=track_num,
            song_id=song_id,
            duration_seconds=duration,
            set_name=set_name,
        )
        tracks_added += 1

    conn.commit()
    existing_dates.add(concert_date)

    if verbose:
        print(f"    {title} [{concert_date}]: {tracks_added} tracks")

    return 1, tracks_added


# ── Public entry point ───────────────────────────────────────────────

def scrape_all(conn, full=False, max_age_days=0, verbose=True):
    """Scrape all Phish shows from the LivePhish streaming catalog.

    Two-phase pipeline:
      Phase 1: Fetch catalog index + per-show detail JSON to local cache
      Phase 2: Parse cached JSON into SQLite (no network needed)

    Args:
        full: If True, ignore cache and re-fetch everything.
        max_age_days: Re-fetch cache entries older than this (0 = never expire).

    Returns (total_releases, total_tracks).
    """
    cache_dir = LP_CACHE_DIR
    os.makedirs(cache_dir, exist_ok=True)
    max_age_seconds = max_age_days * 86400 if max_age_days > 0 else 0

    session = requests.Session()
    session.headers["User-Agent"] = LP_USER_AGENT

    # ── Phase 1: Fetch catalog + show details to cache ───────────────
    if verbose:
        print("  Phase 1: Fetching LivePhish catalog...")

    catalog = _fetch_catalog(session)
    if verbose:
        print(f"  Found {len(catalog)} Phish shows in catalog")
        print("  Fetching show details to cache...")

    api_fetches = 0
    errors = 0
    for i, item in enumerate(catalog):
        cid = item.get("containerID")
        if not cid:
            continue
        try:
            fetched = _fetch_container_to_cache(
                session, cid, cache_dir,
                max_age_seconds=max_age_seconds,
                force=full,
            )
            if fetched:
                api_fetches += 1
        except (requests.RequestException, ValueError, KeyError) as e:
            errors += 1
            if verbose:
                print(f"    Error fetching container {cid}: {e}")

        if verbose and (i + 1) % 100 == 0:
            print(f"    Phase 1 progress: {i + 1}/{len(catalog)} "
                  f"({api_fetches} fetched from API, {errors} errors)")

    if verbose:
        print(f"  Phase 1 complete: {api_fetches} fetched from API, "
              f"{len(catalog) - api_fetches - errors} from cache, {errors} errors")

    # ── Phase 2: Process cache → DB ──────────────────────────────────
    if verbose:
        print("  Phase 2: Processing cached shows into DB...")

    existing_dates = db.dates_already_in_db(conn)
    total_releases = 0
    total_tracks = 0

    for i, item in enumerate(catalog):
        cid = item.get("containerID")
        if not cid:
            continue

        cached_data = read_cache(cache_dir, str(cid))
        if not cached_data:
            continue

        r, t = _process_container_from_cache(conn, cached_data, existing_dates, verbose=verbose)
        total_releases += r
        total_tracks += t

        if verbose and (i + 1) % 100 == 0:
            print(f"    Phase 2 progress: {i + 1}/{len(catalog)}, "
                  f"{total_releases} releases, {total_tracks} tracks")

    if verbose:
        print(f"  LivePhish total: {total_releases} releases, {total_tracks} tracks")

    return total_releases, total_tracks
