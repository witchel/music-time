"""MusicBrainz scraper for Phish live releases.

Provides millisecond-precision durations for official LivePhish releases.

Two-phase pipeline (mirrors gdtimings archive.org scraper):
  Phase 1 — Fetch: browse release groups, download release JSON to local cache
  Phase 2 — Process: parse cached JSON into SQLite (no network required)

Key differences from gdtimings/musicbrainz.py:
- Browse by artist instead of enumerating series
- Year range: 1983-2026 (not 1965-1995)
- Date fallback: try release group title and release title
- Venue/city/state parsed from title when available
"""

import re
import time

import musicbrainzngs

from gdtimings.cache import read_cache, write_cache
from gdtimings.location import normalize_state
from phishtimings import db
from phishtimings.config import (
    MB_CACHE_DIR,
    MUSICBRAINZ_ARTIST_ID,
    MUSICBRAINZ_RATE_LIMIT,
    CONCERT_YEAR_MIN,
    CONCERT_YEAR_MAX,
)
from phishtimings.normalize import normalize_song

# Set up the client once at import time
musicbrainzngs.set_useragent(
    "PhishTimingsBot", "1.0", "https://github.com/phishtimings"
)


def _rate_limit():
    """Sleep to respect MusicBrainz rate limit."""
    if MUSICBRAINZ_RATE_LIMIT > 0:
        time.sleep(MUSICBRAINZ_RATE_LIMIT)


# ── Date parsing ──────────────────────────────────────────────────────

_DATE_PATTERNS = [
    # ISO: 2003-07-25
    re.compile(r'(\d{4})-(\d{1,2})-(\d{1,2})'),
    # US: 7/25/03 or 12/31/2003
    re.compile(r'(\d{1,2})/(\d{1,2})/(\d{2,4})'),
]


def parse_date_from_title(title, min_year=CONCERT_YEAR_MIN, max_year=CONCERT_YEAR_MAX):
    """Extract a concert date (YYYY-MM-DD) from a title string.

    Returns None if no valid date is found.
    """
    if not title:
        return None

    for pat in _DATE_PATTERNS:
        m = pat.search(title)
        if not m:
            continue

        groups = m.groups()
        if '-' in m.group(0):
            year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
        else:
            month, day, year = int(groups[0]), int(groups[1]), int(groups[2])
            if year < 100:
                year += 1900 if year >= 60 else 2000

        if min_year <= year <= max_year and 1 <= month <= 12 and 1 <= day <= 31:
            return f"{year:04d}-{month:02d}-{day:02d}"

    return None


# ── Title parsing for venue/city/state ────────────────────────────────

# Pattern: "YYYY-MM-DD: Venue, City, State, Country"
# or       "YYYY-MM-DD: Venue, City, State"
_TITLE_LOCATION_PATTERN = re.compile(
    r'\d{4}-\d{2}-\d{2}:\s*(.+?),\s*(.+?),\s*([A-Z]{2}(?:\s*,\s*\w+)?)\s*$'
)


def _parse_location_from_title(title):
    """Extract (venue, city, state) from a release group or release title.

    Handles format: "2003-07-25: Verizon Wireless Amphitheatre, Charlotte, NC, USA"
    Returns (venue, city, state) or (None, None, None).
    """
    if not title:
        return None, None, None

    m = _TITLE_LOCATION_PATTERN.search(title)
    if not m:
        return None, None, None

    venue = m.group(1).strip()
    city = m.group(2).strip()
    state_raw = m.group(3).strip()
    # Strip trailing ", USA" or ", Country"
    state_raw = state_raw.split(",")[0].strip()
    state = normalize_state(state_raw)
    return venue, city, state


# ── Release group browsing ────────────────────────────────────────────

def _browse_live_release_groups(verbose=True):
    """Browse all live release groups for Phish via paginated API.

    Returns list of release group dicts.
    """
    release_groups = []
    offset = 0
    limit = 100

    while True:
        _rate_limit()
        result = musicbrainzngs.browse_release_groups(
            artist=MUSICBRAINZ_ARTIST_ID,
            release_type=["live"],
            limit=limit,
            offset=offset,
        )
        rg_list = result.get("release-group-list", [])
        rg_count = int(result.get("release-group-count", 0))

        release_groups.extend(rg_list)
        if verbose:
            print(f"    Browsed {len(release_groups)}/{rg_count} release groups...")

        offset += limit
        if offset >= rg_count or not rg_list:
            break

    return release_groups


# ── Release fetching ──────────────────────────────────────────────────

def _get_release_details(release_mbid):
    """Fetch full release details including media, tracks, and recordings."""
    _rate_limit()
    return musicbrainzngs.get_release_by_id(
        release_mbid,
        includes=["recordings", "media"],
    )["release"]


def _get_releases_for_release_group(rg_mbid):
    """Get all releases in a release group, return the 'best' one."""
    _rate_limit()
    result = musicbrainzngs.browse_releases(
        release_group=rg_mbid,
        includes=[],
        limit=100,
    )
    releases = result.get("release-list", [])
    if not releases:
        return None
    # Prefer the one with the most media (likely the most complete)
    return max(releases, key=lambda r: int(r.get("medium-count", 1)))


# ── Phase 1: Fetch to cache ──────────────────────────────────────────

def _fetch_rg_to_cache(rg, cache_dir, max_age_seconds=0, force=False, verbose=True):
    """Fetch release data for one release group and write to cache.

    Args:
        force: If True, ignore cache and always re-fetch from API.
        max_age_seconds: Re-fetch if cached file is older than this (0 = never expire).

    Returns True if fetched from API, False if cache hit or failure.
    """
    rg_id = rg.get("id")
    rg_title = rg.get("title", "")
    if not rg_id:
        return False

    # Check cache first (unless forced)
    if not force and read_cache(cache_dir, rg_id, max_age_seconds) is not None:
        return False

    try:
        best_rel = _get_releases_for_release_group(rg_id)
        if not best_rel:
            return False

        release = _get_release_details(best_rel["id"])
        write_cache(cache_dir, rg_id, {
            "rg_id": rg_id,
            "rg_title": rg_title,
            "release": release,
        })
        return True
    except musicbrainzngs.WebServiceError as e:
        if verbose:
            print(f"    Error fetching RG {rg_id} ({rg_title}): {e}")
        return False


# ── Phase 2: Process cache → DB ─────────────────────────────────────

def _process_release_from_cache(conn, cached_data, coverage, verbose=True):
    """Process cached release data, creating per-date release records.

    For multi-concert releases, creates one release per concert date.
    Falls back to release group title for date/location when disc titles lack dates.

    Returns (releases_added, tracks_added).
    """
    rg_title = cached_data.get("rg_title", "")
    release = cached_data.get("release", {})
    release_mbid = release.get("id", "")

    title = release.get("title", "")
    media_list = release.get("medium-list", [])

    if not media_list:
        return 0, 0

    # Group media (discs) by concert date
    date_groups = {}  # date_str → [(medium, tracks)]

    for medium in media_list:
        medium_title = medium.get("title", "")
        disc_date = parse_date_from_title(medium_title)

        if disc_date is not None:
            track_list = medium.get("track-list", [])
            if track_list:
                date_groups.setdefault(disc_date, []).append(
                    (medium, track_list)
                )

    # Fallback: if no dates found in disc titles, try release title,
    # then release group title
    if not date_groups:
        fallback_date = parse_date_from_title(title) or parse_date_from_title(rg_title)
        if fallback_date:
            all_tracks = []
            for medium in media_list:
                track_list = medium.get("track-list", [])
                if track_list:
                    all_tracks.append((medium, track_list))
            if all_tracks:
                date_groups[fallback_date] = all_tracks

    # Parse location from release group title or release title
    venue, city, state = _parse_location_from_title(rg_title)
    if not venue:
        venue, city, state = _parse_location_from_title(title)

    releases_added = 0
    tracks_added = 0

    for concert_date, media_tracks in date_groups.items():
        source_id = f"mb:{release_mbid}:{concert_date}"

        if db.release_exists(conn, source_id):
            continue

        release_id = db.insert_release(
            conn,
            source_type="musicbrainz",
            source_id=source_id,
            title=title,
            concert_date=concert_date,
            venue=venue,
            city=city,
            state=state,
            coverage=coverage,
            recording_type="official",
            quality_rank=500,
            source_url=f"https://musicbrainz.org/release/{release_mbid}",
        )
        releases_added += 1

        # Insert tracks from all media for this date
        global_track_num = 0
        for medium, track_list in media_tracks:
            disc_num = int(medium.get("position", 1))
            for track in track_list:
                global_track_num += 1
                recording = track.get("recording", {})
                track_title = recording.get("title", track.get("title", ""))
                length_ms = track.get("length") or recording.get("length")

                duration_secs = None
                if length_ms:
                    duration_secs = int(length_ms) / 1000.0

                song_id, _, _ = normalize_song(conn, track_title)

                db.insert_track(
                    conn,
                    release_id=release_id,
                    title_raw=track_title,
                    disc_number=disc_num,
                    track_number=global_track_num,
                    song_id=song_id,
                    duration_seconds=duration_secs,
                )
                tracks_added += 1

        if verbose:
            print(f"    {title} [{concert_date}]: {global_track_num} tracks")

    conn.commit()
    return releases_added, tracks_added


# ── Two-phase scrape ────────────────────────────────────────────────

def scrape_all(conn, full=False, max_age_days=0, verbose=True):
    """Scrape all Phish live releases from MusicBrainz.

    Two-phase pipeline:
      Phase 1: Browse release groups, fetch release JSON to local cache
      Phase 2: Parse cached JSON into SQLite (no network needed)

    Args:
        full: If True, ignore cache and re-fetch everything.
        max_age_days: Re-fetch cache entries older than this (0 = never expire).

    Returns (total_releases, total_tracks).
    """
    cache_dir = MB_CACHE_DIR
    max_age_seconds = max_age_days * 86400 if max_age_days > 0 else 0

    # ── Phase 1: Browse + fetch-to-cache ─────────────────────────────
    if verbose:
        print("  Phase 1: Browsing Phish live release groups on MusicBrainz...")

    release_groups = _browse_live_release_groups(verbose)

    if verbose:
        print(f"  Found {len(release_groups)} live release groups")
        print("  Fetching release details to cache...")

    api_fetches = 0
    for i, rg in enumerate(release_groups):
        fetched = _fetch_rg_to_cache(
            rg, cache_dir,
            max_age_seconds=max_age_seconds,
            force=full,
            verbose=verbose,
        )
        if fetched:
            api_fetches += 1

        if verbose and (i + 1) % 50 == 0:
            print(f"    Phase 1 progress: {i + 1}/{len(release_groups)} "
                  f"({api_fetches} fetched from API)")

    if verbose:
        print(f"  Phase 1 complete: {api_fetches} fetched from API, "
              f"{len(release_groups) - api_fetches} from cache")

    # ── Phase 2: Process cache → DB ──────────────────────────────────
    if verbose:
        print("  Phase 2: Processing cached releases into DB...")

    total_releases = 0
    total_tracks = 0

    for i, rg in enumerate(release_groups):
        rg_id = rg.get("id")
        if not rg_id:
            continue

        cached_data = read_cache(cache_dir, rg_id)
        if not cached_data:
            continue

        r, t = _process_release_from_cache(
            conn, cached_data, coverage="complete", verbose=verbose
        )
        total_releases += r
        total_tracks += t

        if verbose and (i + 1) % 50 == 0:
            print(f"    Phase 2 progress: {i + 1}/{len(release_groups)}, "
                  f"{total_releases} releases, {total_tracks} tracks")

    if verbose:
        print(f"  MusicBrainz total: {total_releases} releases, {total_tracks} tracks")

    return total_releases, total_tracks
