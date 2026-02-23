"""Internet Archive scraper for Grateful Dead live recordings.

Scraping pipeline:
1. Search the GratefulDead collection via advancedsearch API (~18,000 items)
2. Fetch /metadata/{identifier} for each item
3. Filter audio files (original source, recognized format, has title+length)
4. Parse recording type (SBD/AUD/MTX) from identifier or metadata
5. Extract concert date from identifier
6. Normalize song titles and store in DB
"""

import json
import os
import re
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from gdtimings.config import (
    ARCHIVE_CACHE_DIR,
    ARCHIVE_DEFAULT_WORKERS,
    ARCHIVE_METADATA_URL,
    ARCHIVE_RATE_LIMIT,
    ARCHIVE_SCRAPE_URL,
    ARCHIVE_USER_AGENT,
    QUALITY_RANKS,
)
from gdtimings.http_utils import api_get_with_retry, create_session, progress_line
from gdtimings import db
from gdtimings.location import parse_city_state
from gdtimings.normalize import normalize_song


def _session():
    return create_session(ARCHIVE_USER_AGENT)


def _cache_path(cache_dir, identifier):
    """Two-level cache path: cache_dir/prefix/identifier.json"""
    # Use first 4 chars of identifier as prefix subdirectory
    prefix = identifier[:4] if len(identifier) >= 4 else identifier
    return Path(cache_dir) / prefix / f"{identifier}.json"


def _read_cache(cache_dir, identifier, max_age_seconds=0):
    """Read cached JSON for an identifier. Returns dict or None."""
    path = _cache_path(cache_dir, identifier)
    if not path.exists():
        return None
    if max_age_seconds > 0:
        age = time.time() - path.stat().st_mtime
        if age > max_age_seconds:
            return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _write_cache(cache_dir, identifier, data):
    """Atomically write JSON to cache."""
    path = _cache_path(cache_dir, identifier)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Atomic write: write to temp file then rename
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


_thread_local = threading.local()


def _thread_session():
    """Get or create a thread-local requests.Session."""
    if not hasattr(_thread_local, "session"):
        _thread_local.session = _session()
    return _thread_local.session


def _api_get(session, url, params=None, max_retries=3):
    """Make an API request with rate limiting and retry."""
    return api_get_with_retry(session, url, params=params,
                              rate_limit=ARCHIVE_RATE_LIMIT,
                              max_retries=max_retries)


# ── Collection search ────────────────────────────────────────────────

def search_collection(session):
    """Enumerate all GratefulDead collection identifiers via scrape API.

    Uses the cursor-based scrape endpoint which supports >10k results
    (the advancedsearch API caps at 10,000).
    """
    identifiers = []
    cursor = None
    batch = 0

    while True:
        params = {
            "q": "collection:GratefulDead AND mediatype:etree",
            "fields": "identifier",
            "count": "10000",
        }
        if cursor:
            params["cursor"] = cursor

        data = _api_get(session, ARCHIVE_SCRAPE_URL, params=params)

        items = data.get("items", [])
        if not items:
            break

        for item in items:
            identifiers.append(item["identifier"])

        batch += 1
        total = data.get("total", "?")
        print(f"  Search batch {batch}: {len(items)} items "
              f"({len(identifiers)}/{total} total)")

        cursor = data.get("cursor")
        if not cursor:
            break

    return identifiers


# ── Identifier parsing ───────────────────────────────────────────────

def parse_recording_type(identifier, metadata=None):
    """Detect recording type (SBD/AUD/MTX) from identifier or metadata.

    Archive.org identifiers follow patterns like:
        gd1977-05-08.sbd.miller.32926.sbeok.shnf  (soundboard)
        gd1969-11-08.aud.unknown.12345.shnf        (audience)
        gd1990-03-29.mtx.seamons.12345.shnf        (matrix)
    """
    id_lower = identifier.lower()

    # Check identifier segments (split by ".")
    parts = id_lower.split(".")
    for part in parts[:4]:  # type is usually in first few segments
        if part == "sbd":
            return "SBD"
        if part == "mtx" or part == "matrix":
            return "MTX"
        if part == "aud":
            return "AUD"

    # Fall back to metadata source field
    if metadata:
        source = (metadata.get("source") or "").lower()
        if "soundboard" in source or "sbd" in source:
            return "SBD"
        if "matrix" in source:
            return "MTX"
        if "audience" in source or "aud" in source:
            return "AUD"

    return "AUD"  # default for live recordings


def parse_date_from_identifier(identifier):
    """Extract YYYY-MM-DD date from an archive.org identifier.

    Formats: gd1977-05-08..., gd77-05-08..., gd19770508...
    """
    # gd + 4-digit year with dashes
    m = re.search(r'gd(\d{4})-(\d{2})-(\d{2})', identifier)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

    # gd + 2-digit year with dashes
    m = re.search(r'gd(\d{2})-(\d{2})-(\d{2})', identifier)
    if m:
        year = int(m.group(1))
        full_year = 1900 + year if year >= 60 else 2000 + year
        return f"{full_year}-{m.group(2)}-{m.group(3)}"

    # Compact: gd19770508
    m = re.search(r'gd(\d{4})(\d{2})(\d{2})', identifier)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

    return None


# ── Track extraction ─────────────────────────────────────────────────

def _is_audio_format(fmt):
    """Check if an archive.org file format string indicates audio."""
    fmt_lower = fmt.lower()
    audio_keywords = ("flac", "mp3", "ogg", "shorten", "shn", "lossless",
                      "wav", "aiff", "m4a", "aac", "opus")
    return any(kw in fmt_lower for kw in audio_keywords)


def _extract_tracks(files):
    """Filter files to original audio tracks with title and length.

    Returns a sorted, deduplicated list of track dicts.
    """
    tracks = []
    seen_track_nums = set()

    for f in files:
        # Must be an original (not a derivative re-encoding)
        if f.get("source") != "original":
            continue

        # Must be an audio format
        fmt = f.get("format") or ""
        if not _is_audio_format(fmt):
            continue

        # Must have a length
        length = f.get("length")
        if not length:
            continue
        try:
            duration = float(length)
        except (ValueError, TypeError):
            continue
        if duration <= 0:
            continue

        # Get title (fall back to filename without extension)
        title = f.get("title") or ""
        if not title:
            name = f.get("name", "")
            title = re.sub(r'\.[^.]+$', '', name)  # strip extension
            if not title:
                continue

        # Get track number
        track_num = f.get("track")
        if track_num:
            try:
                track_num = int(str(track_num).split("/")[0])
            except (ValueError, TypeError):
                track_num = None

        # Deduplicate by track number (different formats of same track)
        if track_num and track_num in seen_track_nums:
            continue
        if track_num:
            seen_track_nums.add(track_num)

        tracks.append({
            "title_raw": title,
            "track": track_num,
            "duration": duration,
        })

    # Sort by track number (or by list order if no track numbers)
    tracks.sort(key=lambda t: (t["track"] or 999, t["title_raw"]))

    # Assign track numbers if missing
    for i, t in enumerate(tracks, 1):
        if t["track"] is None:
            t["track"] = i

    return tracks


# ── Item scraping ────────────────────────────────────────────────────

def _fetch_to_cache(identifier, cache_dir, max_age_seconds=0):
    """Fetch metadata for one identifier and write to cache.

    Returns (identifier, True) on success, (identifier, False) on failure.
    """
    # Check cache first
    if _read_cache(cache_dir, identifier, max_age_seconds) is not None:
        return identifier, True

    url = ARCHIVE_METADATA_URL.format(identifier=identifier)
    try:
        data = _api_get(_thread_session(), url)
        if data:
            _write_cache(cache_dir, identifier, data)
            return identifier, True
    except Exception:
        pass
    return identifier, False


def _process_from_cache(conn, identifier, data):
    """Process cached metadata JSON and insert into DB.

    Returns (release_id, track_count) or (None, 0) if skipped.
    """
    source_id = f"archive:{identifier}"
    existing_id = db.release_exists(conn, source_id)
    if existing_id:
        return existing_id, 0

    if not data or "metadata" not in data:
        return None, 0

    metadata = data["metadata"]
    files = data.get("files", [])

    tracks = _extract_tracks(files)
    if not tracks:
        return None, 0

    concert_date = parse_date_from_identifier(identifier)
    if not concert_date:
        meta_date = metadata.get("date", "")
        m = re.match(r'(\d{4}-\d{2}-\d{2})', meta_date)
        if m:
            concert_date = m.group(1)

    rec_type = parse_recording_type(identifier, metadata)
    quality_rank = QUALITY_RANKS.get(rec_type, 100)

    venue = metadata.get("venue", "") or None
    city, state = parse_city_state(metadata.get("coverage", ""))

    taper = metadata.get("taper", "") or None
    lineage = metadata.get("lineage", "") or None
    source_detail = metadata.get("source", "") or None

    title = metadata.get("title", identifier)

    release_id = db.insert_release(
        conn,
        source_type="archive.org",
        source_id=source_id,
        title=title,
        concert_date=concert_date,
        venue=venue,
        city=city,
        state=state,
        coverage="unedited",
        recording_type=rec_type,
        quality_rank=quality_rank,
        source_url=f"https://archive.org/details/{identifier}",
        taper=taper,
        lineage=lineage,
        source_detail=source_detail,
    )

    for t in tracks:
        song_id, _, _ = normalize_song(conn, t["title_raw"])
        db.insert_track(
            conn,
            release_id=release_id,
            title_raw=t["title_raw"],
            disc_number=1,
            track_number=t["track"],
            song_id=song_id,
            duration_seconds=t["duration"],
            segue=0,
        )
    conn.commit()

    return release_id, len(tracks)


def scrape_item(conn, session, identifier, cache_dir=None):
    """Scrape a single archive.org item and store in DB.

    Returns (release_id, track_count) or (None, 0) if skipped/failed.
    """
    source_id = f"archive:{identifier}"
    existing_id = db.release_exists(conn, source_id)
    if existing_id:
        return existing_id, 0

    if cache_dir:
        data = _read_cache(cache_dir, identifier)
        if data is None:
            url = ARCHIVE_METADATA_URL.format(identifier=identifier)
            data = _api_get(session, url)
            if data:
                _write_cache(cache_dir, identifier, data)
        if data:
            return _process_from_cache(conn, identifier, data)
        return None, 0

    # Original behavior: fetch and process inline
    url = ARCHIVE_METADATA_URL.format(identifier=identifier)
    data = _api_get(session, url)
    return _process_from_cache(conn, identifier, data) if data else (None, 0)


# ── Main entry point ─────────────────────────────────────────────────

def scrape_all(conn, full=False, verbose=True, workers=None, use_cache=True,
               max_age_days=0):
    """Scrape all Grateful Dead recordings from archive.org.

    Args:
        conn: DB connection
        full: If True, re-scrape everything (ignore DB state)
        verbose: Print progress
        workers: Number of parallel fetch workers (default: config value)
        use_cache: If True, use local JSON cache (Phase 1 + Phase 2)
        max_age_days: Max cache age in days (0 = never expire)
    """
    session = _session()

    if verbose:
        print("  Searching archive.org GratefulDead collection...")

    identifiers = search_collection(session)

    if verbose:
        print(f"  Found {len(identifiers)} recordings\n")

    if not identifiers:
        return 0, 0

    if workers is None:
        workers = ARCHIVE_DEFAULT_WORKERS

    max_age_seconds = max_age_days * 86400

    # ── Pre-filter: skip identifiers already in DB (unless --full) ──
    if not full:
        existing = set()
        for ident in identifiers:
            source_id = f"archive:{ident}"
            if db.release_exists(conn, source_id):
                existing.add(ident)
        if existing and verbose:
            print(f"  Skipping {len(existing)} identifiers already in DB")
        identifiers = [i for i in identifiers if i not in existing]

    if not identifiers:
        if verbose:
            print("  Nothing to scrape.")
        return 0, 0

    if not use_cache:
        # ── No-cache fallback: original sequential behavior ──
        return _scrape_sequential(conn, session, identifiers, verbose)

    cache_dir = ARCHIVE_CACHE_DIR

    # ── Phase 1: Parallel fetch to cache ──
    to_fetch = [i for i in identifiers
                if _read_cache(cache_dir, i, max_age_seconds) is None]

    if verbose:
        print(f"  Phase 1: {len(to_fetch)} to fetch, "
              f"{len(identifiers) - len(to_fetch)} already cached")

    if to_fetch:
        fetched = 0
        errors = 0
        t_start = time.monotonic()

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(_fetch_to_cache, ident, cache_dir, max_age_seconds): ident
                for ident in to_fetch
            }
            for future in as_completed(futures):
                ident = futures[future]
                try:
                    _, ok = future.result()
                    if ok:
                        fetched += 1
                    else:
                        errors += 1
                except Exception:
                    errors += 1

                done = fetched + errors
                if verbose and done % 100 == 0:
                    elapsed = time.monotonic() - t_start
                    print(f"    {progress_line(done, len(to_fetch), elapsed)} "
                          f"{fetched} fetched, {errors} errors")

        elapsed = time.monotonic() - t_start
        if verbose:
            print(f"  Phase 1 done: {fetched} fetched, {errors} errors "
                  f"({elapsed:.0f}s)\n")

    # ── Phase 2: Serial DB processing from cache ──
    if verbose:
        print(f"  Phase 2: Processing {len(identifiers)} items from cache...")

    total_releases = 0
    total_tracks = 0
    skipped = 0
    errors = 0

    t_start = time.monotonic()
    for i, identifier in enumerate(identifiers, 1):
        data = _read_cache(cache_dir, identifier)
        if data is None:
            errors += 1
            continue

        try:
            release_id, track_count = _process_from_cache(conn, identifier, data)
            if track_count > 0:
                total_releases += 1
                total_tracks += track_count
                if verbose and total_releases % 100 == 0:
                    elapsed = time.monotonic() - t_start
                    print(f"    {progress_line(i, len(identifiers), elapsed)} "
                          f"{total_releases} releases, {total_tracks} tracks")
            elif release_id:
                skipped += 1
        except Exception as e:
            errors += 1
            if verbose:
                print(f"    ERROR on {identifier}: {e}")

    elapsed = time.monotonic() - t_start
    if verbose:
        print(f"\n  Done: {total_releases} new releases, {total_tracks} tracks "
              f"({skipped} skipped, {errors} errors, {elapsed:.0f}s)")

    return total_releases, total_tracks


def _scrape_sequential(conn, session, identifiers, verbose):
    """Original sequential scrape loop (used with --no-cache)."""
    total_releases = 0
    total_tracks = 0
    skipped = 0
    errors = 0

    t_start = time.monotonic()
    for i, identifier in enumerate(identifiers, 1):
        elapsed = time.monotonic() - t_start
        prefix = f"  {progress_line(i, len(identifiers), elapsed)}"

        try:
            release_id, track_count = scrape_item(conn, session, identifier)
            if track_count > 0:
                total_releases += 1
                total_tracks += track_count
                if verbose:
                    print(f"{prefix} {identifier}: {track_count} tracks "
                          f"(total: {total_releases} releases, {total_tracks} tracks)")
            elif release_id:
                skipped += 1
                if verbose and skipped % 1000 == 0:
                    print(f"{prefix} ...{skipped} already in DB")
        except Exception as e:
            errors += 1
            if verbose:
                print(f"{prefix} ERROR on {identifier}: {e}")

    elapsed = time.monotonic() - t_start
    if verbose:
        print(f"\n  Done: {total_releases} new releases, {total_tracks} tracks "
              f"({skipped} skipped, {errors} errors, {elapsed:.0f}s)")

    return total_releases, total_tracks
