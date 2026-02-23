"""MusicBrainz scraper for Grateful Dead official releases.

Provides millisecond-precision durations and per-disc concert dates
for box sets where Wikipedia data is incomplete (NULL concert_date,
missing durations).

Pipeline:
1. Enumerate releases in known series (Dick's Picks, Dave's Picks, etc.)
2. For each release, fetch recordings with durations
3. Parse concert dates from media (disc) titles
4. Create one release record per concert date within multi-concert box sets
5. Insert tracks with MusicBrainz durations
"""

import re
import time

import musicbrainzngs

from gdtimings import db
from gdtimings.config import (
    MUSICBRAINZ_RATE_LIMIT,
    MUSICBRAINZ_SERIES_COVERAGE,
    MUSICBRAINZ_SERIES_IDS,
    MUSICBRAINZ_STANDALONE_RELEASES,
)
from gdtimings.normalize import normalize_song

# Set up the client once at import time
musicbrainzngs.set_useragent(
    "GDTimingsBot", "1.0", "https://github.com/gdtimings"
)


def _rate_limit():
    """Sleep to respect MusicBrainz rate limit."""
    if MUSICBRAINZ_RATE_LIMIT > 0:
        time.sleep(MUSICBRAINZ_RATE_LIMIT)


# ── Date parsing ──────────────────────────────────────────────────────

# Patterns for dates in media titles, e.g.:
#   "P.N.E. Coliseum -- Vancouver, B.C., Canada - 6/22/73"
#   "Boston Music Hall, Boston, MA 6/9/76"
#   "12/31/78"
#   "1974-05-21"
_DATE_PATTERNS = [
    # ISO: 1974-05-21
    re.compile(r'(\d{4})-(\d{1,2})-(\d{1,2})'),
    # US: 6/22/73 or 12/31/1978
    re.compile(r'(\d{1,2})/(\d{1,2})/(\d{2,4})'),
]


def parse_date_from_title(title):
    """Extract a concert date (YYYY-MM-DD) from a media/disc title.

    Returns None if no date is found.
    """
    if not title:
        return None

    for pat in _DATE_PATTERNS:
        m = pat.search(title)
        if not m:
            continue

        groups = m.groups()
        if '-' in m.group(0):
            # ISO format: YYYY-MM-DD
            year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
        else:
            # US format: M/D/YY or M/D/YYYY
            month, day, year = int(groups[0]), int(groups[1]), int(groups[2])
            if year < 100:
                year += 1900 if year >= 60 else 2000

        if 1965 <= year <= 1995 and 1 <= month <= 12 and 1 <= day <= 31:
            return f"{year:04d}-{month:02d}-{day:02d}"

    return None


# ── Series enumeration ────────────────────────────────────────────────

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


# ── Main scraping logic ──────────────────────────────────────────────

def scrape_series(conn, series_name, series_mbid, coverage, verbose=True):
    """Scrape all releases in a MusicBrainz series.

    Returns (releases_added, tracks_added).
    """
    if verbose:
        print(f"  Fetching {series_name} series from MusicBrainz...")

    releases_added = 0
    tracks_added = 0

    # Get release groups linked to this series
    _rate_limit()
    result = musicbrainzngs.get_series_by_id(
        series_mbid, includes=["release-group-rels"]
    )
    rels = result.get("series", {}).get("release_group-relation-list", [])

    if not rels:
        if verbose:
            print(f"    No release groups found in series {series_name}")
        return releases_added, tracks_added

    for rel in rels:
        rg = rel.get("release-group", {})
        rg_id = rg.get("id")
        if not rg_id:
            continue
        best_rel = _get_releases_for_release_group(rg_id)
        if not best_rel:
            continue
        r, t = _process_release(conn, best_rel["id"], coverage, verbose)
        releases_added += r
        tracks_added += t

    return releases_added, tracks_added


def _process_release(conn, release_mbid, coverage, verbose=True):
    """Process a single MusicBrainz release, creating per-date release records.

    For multi-concert box sets, creates one release per concert date.
    Returns (releases_added, tracks_added).
    """
    try:
        release = _get_release_details(release_mbid)
    except musicbrainzngs.WebServiceError as e:
        if verbose:
            print(f"    Error fetching release {release_mbid}: {e}")
        return 0, 0

    title = release.get("title", "")
    media_list = release.get("medium-list", [])

    if not media_list:
        return 0, 0

    # Group media (discs) by concert date
    # Each disc may have a title with an embedded date
    date_groups = {}  # date_str → [(medium, tracks)]

    for medium in media_list:
        medium_title = medium.get("title", "")
        disc_date = parse_date_from_title(medium_title)

        # Only use dates parsed from disc titles — never fall back to the
        # release-level date, which is the *publication* date (e.g. 1996 for
        # a Dick's Picks of a 1970 concert).  Single-concert releases without
        # disc-level dates rely on Wikipedia for the correct concert date.
        if disc_date is None:
            continue

        track_list = medium.get("track-list", [])
        if track_list:
            date_groups.setdefault(disc_date, []).append(
                (medium, track_list)
            )

    releases_added = 0
    tracks_added = 0

    for concert_date, media_tracks in date_groups.items():
        source_id = f"mb:{release_mbid}:{concert_date}"

        # Skip if already exists
        if db.release_exists(conn, source_id):
            continue

        release_id = db.insert_release(
            conn,
            source_type="musicbrainz",
            source_id=source_id,
            title=title,
            concert_date=concert_date,
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

                # Normalize the song title
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
            print(f"    {title} [{concert_date}]: {tracks_added} tracks")

    conn.commit()
    return releases_added, tracks_added


def scrape_all(conn, full=False, verbose=True):
    """Scrape all configured MusicBrainz series.

    Returns (total_releases, total_tracks).
    """
    total_releases = 0
    total_tracks = 0

    for series_name, series_mbid in MUSICBRAINZ_SERIES_IDS.items():
        coverage = MUSICBRAINZ_SERIES_COVERAGE.get(series_name, "unknown")
        r, t = scrape_series(conn, series_name, series_mbid, coverage, verbose)
        total_releases += r
        total_tracks += t

    # Standalone box sets not in any series
    for rg_mbid, coverage in MUSICBRAINZ_STANDALONE_RELEASES.items():
        best_rel = _get_releases_for_release_group(rg_mbid)
        if not best_rel:
            continue
        r, t = _process_release(conn, best_rel["id"], coverage, verbose)
        total_releases += r
        total_tracks += t

    if verbose:
        print(f"  MusicBrainz total: {total_releases} releases, {total_tracks} tracks")

    return total_releases, total_tracks
