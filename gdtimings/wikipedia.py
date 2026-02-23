"""Wikipedia scraper for Grateful Dead live releases.

Wikipedia is used for release discovery and coverage classification metadata.
MusicBrainz (musicbrainz.py) is the authoritative source for timing data.
Wikipedia timing data serves as a fallback for releases not yet in MusicBrainz.

Scraping pipeline:
1. Enumerate releases via Wikipedia category API
2. Fetch rendered HTML for each album page
3. Parse infobox for concert metadata
4. Parse track listings (two formats: numbered lists and tracklist tables)
5. Normalize song titles and store in DB
"""

import re
import time
import html as html_module
from html.parser import HTMLParser

import requests

from gdtimings.config import (
    CATEGORY_COVERAGE,
    RELEASE_COVERAGE_OVERRIDES,
    WIKIPEDIA_API,
    WIKIPEDIA_CATEGORIES,
    WIKIPEDIA_RATE_LIMIT,
    WIKIPEDIA_USER_AGENT,
)
from gdtimings import db
from gdtimings.location import is_us_state, normalize_state
from gdtimings.normalize import normalize_song


class _TagStripper(HTMLParser):
    """Strip HTML tags, keeping only text content."""

    _BLOCK_TAGS = frozenset(("br", "p", "div", "li", "tr"))

    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self._BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)

    def get_text(self):
        return "".join(self.parts)


def strip_tags(html_str):
    s = _TagStripper()
    s.feed(html_str)
    return s.get_text()


def _session():
    s = requests.Session()
    s.headers["User-Agent"] = WIKIPEDIA_USER_AGENT
    return s


def _api_get(session, params, max_retries=3):
    """Make a Wikipedia API request with rate limiting and retry."""
    params.setdefault("format", "json")
    for attempt in range(max_retries):
        resp = session.get(WIKIPEDIA_API, params=params)
        if resp.status_code == 429 or resp.status_code >= 500:
            retry_after = int(resp.headers.get("Retry-After", 2 ** attempt))
            print(f"    HTTP {resp.status_code}, retrying in {retry_after}s "
                  f"(attempt {attempt + 1}/{max_retries})")
            time.sleep(retry_after)
            continue
        resp.raise_for_status()
        time.sleep(WIKIPEDIA_RATE_LIMIT)
        return resp.json()
    # Final attempt — let it raise
    resp = session.get(WIKIPEDIA_API, params=params)
    resp.raise_for_status()
    time.sleep(WIKIPEDIA_RATE_LIMIT)
    return resp.json()


# ── Category enumeration ──────────────────────────────────────────────

def get_category_members(session, category):
    """Return list of page titles in a Wikipedia category."""
    titles = []
    params = {
        "action": "query",
        "list": "categorymembers",
        "cmtitle": category,
        "cmlimit": "500",
        "cmtype": "page",
    }
    while True:
        data = _api_get(session, params)
        for member in data.get("query", {}).get("categorymembers", []):
            titles.append(member["title"])
        if "continue" in data:
            params["cmcontinue"] = data["continue"]["cmcontinue"]
        else:
            break
    return titles


# ── Page fetching ─────────────────────────────────────────────────────

def fetch_page_html(session, title):
    """Fetch rendered HTML for a Wikipedia page."""
    data = _api_get(session, {
        "action": "parse",
        "page": title,
        "prop": "text",
        "disabletoc": "true",
    })
    return data.get("parse", {}).get("text", {}).get("*", "")


# ── Infobox parsing ──────────────────────────────────────────────────

def _extract_infobox_field(html_text, field_name):
    """Extract a field value from an infobox in the rendered HTML."""
    # Look for table row with the field name as header
    pattern = (
        r'<th[^>]*>\s*' + re.escape(field_name) + r'\s*</th>\s*'
        r'<td[^>]*>(.*?)</td>'
    )
    m = re.search(pattern, html_text, re.IGNORECASE | re.DOTALL)
    if m:
        return strip_tags(m.group(1)).strip()
    return None


def parse_infobox(html_text):
    """Extract album metadata from the infobox."""
    info = {}

    recorded = _extract_infobox_field(html_text, "Recorded")
    if recorded:
        info["recorded"] = recorded

    released = _extract_infobox_field(html_text, "Released")
    if released:
        info["released"] = released

    venue_text = _extract_infobox_field(html_text, "Venue")
    if venue_text:
        info["venue"] = venue_text

    label = _extract_infobox_field(html_text, "Label")
    if label:
        info["label"] = label

    length = _extract_infobox_field(html_text, "Length")
    if length:
        info["length"] = length

    return info


def parse_concert_date(recorded_str):
    """Try to extract an ISO date from a 'Recorded' field.

    Handles formats like:
    - "November 8, 1969"
    - "May 2, 1970"
    - "February 13–14, 1970"  (returns first date)
    - "September 3 & 4, 1977"
    - Multi-line with multiple dates (returns first)
    """
    if not recorded_str:
        return None
    # Take first line / first date
    line = recorded_str.split("\n")[0].strip()
    # Try full date: "Month DD, YYYY"
    m = re.search(
        r"(January|February|March|April|May|June|July|August|September|"
        r"October|November|December)\s+(\d{1,2})(?:\s*[-–&,]\s*\d{1,2})?,?\s*(\d{4})",
        line,
    )
    if m:
        month_name, day, year = m.group(1), m.group(2), m.group(3)
        months = {
            "January": "01", "February": "02", "March": "03", "April": "04",
            "May": "05", "June": "06", "July": "07", "August": "08",
            "September": "09", "October": "10", "November": "11", "December": "12",
        }
        return f"{year}-{months[month_name]}-{day.zfill(2)}"
    return None


# ── Duration parsing ─────────────────────────────────────────────────

def parse_duration(text):
    """Parse a duration string like '5:32' or '12:05' into seconds."""
    if not text:
        return None
    text = text.strip()
    # Handle MM:SS or H:MM:SS
    m = re.match(r"(\d+):(\d{2}):(\d{2})", text)
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
    m = re.match(r"(\d+):(\d{2})", text)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    return None


# ── Track list parsing ───────────────────────────────────────────────

def _parse_tracklist_tables(html_text):
    """Parse {{tracklist}} template tables.

    These render as <table class="tracklist"> with rows containing
    track number, title, writers, and duration.
    """
    tracks = []
    disc = 1

    # Find all tracklist tables
    table_pattern = re.compile(
        r'<table[^>]*class="[^"]*tracklist[^"]*"[^>]*>(.*?)</table>',
        re.DOTALL | re.IGNORECASE,
    )

    for table_match in table_pattern.finditer(html_text):
        table_html = table_match.group(1)

        # Check for disc/side header just before this table (take last match
        # in window to avoid picking up a header from a previous table)
        pre_text = html_text[max(0, table_match.start() - 500):table_match.start()]
        disc_matches = re.findall(r'(?:Disc|Side|Set)\s*(\d+)', pre_text, re.IGNORECASE)
        if disc_matches:
            disc = int(disc_matches[-1])

        # Parse rows
        row_pattern = re.compile(r'<tr>(.*?)</tr>', re.DOTALL)
        track_num = 0
        for row_match in row_pattern.finditer(table_html):
            row_html = row_match.group(1)
            cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row_html, re.DOTALL)
            if len(cells) < 2:
                continue

            # Skip header rows
            first_text = strip_tags(cells[0]).strip().lower()
            if first_text in ("no.", "#", "no", "track", ""):
                continue

            # Try to get track number from first cell
            num_text = strip_tags(cells[0]).strip().rstrip(".")
            try:
                track_num = int(num_text)
            except ValueError:
                track_num += 1

            # Find title — usually the second cell, may contain quotes and links
            title_raw = strip_tags(cells[1]).strip().strip('"').strip()

            # Find duration — usually last cell, look for MM:SS pattern
            duration = None
            writers = None
            for cell in reversed(cells[2:]):
                cell_text = strip_tags(cell).strip()
                if duration is None and re.search(r'\d+:\d{2}', cell_text):
                    duration = parse_duration(cell_text)
                elif writers is None and cell_text and not re.search(r'\d+:\d{2}', cell_text):
                    writers = cell_text

            if title_raw:
                tracks.append({
                    "title_raw": title_raw,
                    "disc": disc,
                    "track": track_num,
                    "duration": duration,
                    "writers": writers,
                    "segue": 0,
                })

    return tracks


def _parse_numbered_lists(html_text):
    """Parse numbered list format track listings.

    Format: "Title" (writers) – MM:SS
    Found in Dick's Picks, Dave's Picks, etc.
    """
    tracks = []
    disc = 1
    track_num = 0
    set_name = None

    # Split into lines for processing
    # First, find the track listing section
    # Look for ordered lists (but NOT reference lists)
    li_pattern = re.compile(r'<li[^>]*>(.*?)</li>', re.DOTALL)

    # Also detect disc/set headers in the surrounding HTML
    # Process the HTML sequentially to track disc numbers
    segments = re.split(r'(<ol[^>]*>.*?</ol>)', html_text, flags=re.DOTALL)

    for segment in segments:
        # Check for disc/set headers
        disc_m = re.search(
            r'(?:<[^>]+>)*\s*(?:Disc|Volume|Part)\s+(\d+|[Oo]ne|[Tt]wo|[Tt]hree|[Ff]our)',
            segment, re.IGNORECASE,
        )
        if disc_m:
            disc_text = disc_m.group(1)
            disc_map = {"one": 1, "two": 2, "three": 3, "four": 4}
            disc = disc_map.get(disc_text.lower(), None)
            if disc is None:
                try:
                    disc = int(disc_text)
                except ValueError:
                    disc = 1
            track_num = 0  # reset track numbering

        set_m = re.search(
            r'(?:<[^>]+>)*\s*(?:Set|Encore)\s*(\d*)',
            segment, re.IGNORECASE,
        )
        if set_m and not re.search(r'<ol', segment):
            name_m = re.search(r'(Set\s*\d+|Encore\s*\d*)', segment, re.IGNORECASE)
            if name_m:
                set_name = name_m.group(1).strip()

        if not re.search(r'<ol', segment):
            continue

        # Skip reference/footnote lists
        if re.search(r'<ol[^>]*class="[^"]*references[^"]*"', segment, re.IGNORECASE):
            continue

        # Extract the content inside <ol>...</ol>
        ol_match = re.search(r'<ol[^>]*>(.*?)</ol>', segment, re.DOTALL)
        if not ol_match:
            continue
        ol_html = ol_match.group(1)

        for li_match in li_pattern.finditer(ol_html):
            li_html = li_match.group(1)
            li_text = strip_tags(li_html).strip()
            li_text = html_module.unescape(li_text)

            # Skip footnote/reference items (start with ^ or citation markers)
            if li_text.startswith("^") or li_text.startswith(".mw-parser"):
                continue
            # Skip items that look like references (contain "Retrieved" or "Archived")
            if re.search(r'\bRetrieved\b|\bArchived\b|\bAllMusic\b', li_text):
                continue

            track_num += 1

            # Detect segue marker (→ or > in text, or &gt; in raw HTML)
            segue = 1 if ("→" in li_text or ">" in li_text.rstrip() or
                          "&gt;" in li_html) else 0

            # Try to parse: "Title" (writers) – MM:SS
            # or: "Title" – MM:SS
            # or: Title (writers) – MM:SS
            title = None
            writers = None
            duration = None

            # Extract duration from end
            dur_m = re.search(r'[–\-—]\s*(\d+:\d{2}(?::\d{2})?)\s*$', li_text)
            if dur_m:
                duration = parse_duration(dur_m.group(1))
                li_text = li_text[:dur_m.start()].strip()

            # Extract title and writers
            # Pattern 1: "Title" (writers)
            m = re.match(r'["\u201c](.+?)["\u201d]\s*(?:[>→])?\s*\((.+?)\)\s*$', li_text)
            if m:
                title = m.group(1)
                writers = m.group(2)
            else:
                # Pattern 2: "Title"
                m = re.match(r'["\u201c](.+?)["\u201d]\s*(?:[>→])?\s*$', li_text)
                if m:
                    title = m.group(1)
                else:
                    # Pattern 3: bare title (possibly with parenthetical writers)
                    m = re.match(r'(.+?)\s*\((.+?)\)\s*$', li_text)
                    if m:
                        title = m.group(1).strip()
                        writers = m.group(2)
                    else:
                        title = li_text.strip()

            if title:
                title = title.strip().strip('"').strip()
                tracks.append({
                    "title_raw": title,
                    "disc": disc,
                    "track": track_num,
                    "duration": duration,
                    "writers": writers,
                    "segue": segue,
                    "set_name": set_name,
                })

    return tracks


def parse_tracks(html_text):
    """Parse track listings from album page HTML.

    Tries tracklist tables first, falls back to numbered lists.
    Returns list of track dicts.
    """
    # Try tracklist tables first
    tracks = _parse_tracklist_tables(html_text)
    if tracks:
        return tracks

    # Fall back to numbered lists
    tracks = _parse_numbered_lists(html_text)
    return tracks


# ── Venue / location parsing ─────────────────────────────────────────

def parse_venue_location(venue_text):
    """Parse Wikipedia venue field into (venue_name, city, state).

    The venue field (after strip_tags fix) may contain:
        "Boston Garden\nBoston, Massachusetts"        → <br> separated
        "Barton Hall (Ithaca, New York)"              → parenthesized location
        "Avalon Ballroom in San Francisco, California" → "in" pattern
        "Madison Square Garden"                        → venue only, no location

    Returns (venue, city, state) — any may be None.
    """
    if not venue_text:
        return None, None, None

    venue_text = venue_text.strip()

    # Multi-venue with semicolons: take only the first venue
    if ";" in venue_text:
        venue_text = venue_text.split(";")[0].strip()

    # Pattern 1: newline-separated (from <br> fix)
    if "\n" in venue_text:
        lines = [ln.strip() for ln in venue_text.split("\n") if ln.strip()]
        venue_name = lines[0].rstrip(",").strip() if lines else None
        city, state = None, None
        # Look for a "City, State" line — skip lines that look like another venue
        for ln in lines[1:]:
            # Strip surrounding parentheses: "(Pembroke Pines, Florida)" → "Pembroke Pines, Florida"
            ln = re.sub(r'^\((.+)\)$', r'\1', ln).strip()
            if "," in ln:
                parts = ln.split(",", 1)
                candidate_state = parts[1].strip()
                # Only accept if the state part is a recognized US state
                # (avoids "Community War Memorial, Rochester, New York" being parsed
                # as city="Community War Memorial", state="Rochester, New York")
                if is_us_state(candidate_state):
                    city = parts[0].strip() or None
                    state = normalize_state(candidate_state)
                    break
            elif not city:
                # Single word/phrase without comma — could be a city name (e.g. "Lake Tahoe")
                # Skip lines that look like another venue name
                venue_words = ("theatre", "theater", "arena", "hall", "coliseum",
                               "auditorium", "stadium", "center", "centre", "field",
                               "ballroom", "garden", "pavilion", "amphitheatre")
                if not any(w in ln.lower() for w in venue_words):
                    city = ln
        return venue_name, city, state

    # Pattern 2: parenthesized location — "Barton Hall (Ithaca, New York)"
    m = re.match(r'^(.+?)\s*\(([^)]+)\)\s*$', venue_text)
    if m:
        venue_name = m.group(1).strip()
        loc = m.group(2).strip()
        if "," in loc:
            parts = loc.split(",", 1)
            return venue_name, parts[0].strip(), normalize_state(parts[1].strip())
        return venue_name, loc, None

    # Pattern 3: "in" separator — "Avalon Ballroom in San Francisco, California"
    m = re.match(r'^(.+?)\s+in\s+(.+)$', venue_text, re.IGNORECASE)
    if m:
        venue_name = m.group(1).strip()
        loc = m.group(2).strip()
        if "," in loc:
            parts = loc.split(",", 1)
            return venue_name, parts[0].strip(), normalize_state(parts[1].strip())
        return venue_name, loc, None

    # Pattern 4: comma-separated with embedded state
    # "Selland Arena, Fresno, California, USA" → venue=Selland Arena, city=Fresno, state=California
    # "Capitol Theatre, Passaic, NJ" → venue=Capitol Theatre, city=Passaic, state=New Jersey
    if "," in venue_text:
        parts = [p.strip() for p in venue_text.split(",")]
        for i, part in enumerate(parts):
            if is_us_state(part):
                venue_name = ", ".join(parts[:i - 1]) if i > 1 else None
                city = parts[i - 1] if i > 0 else None
                state = normalize_state(part)
                return venue_name, city, state

    # Fallback: venue name only
    return venue_text, None, None


# ── Main scraping logic ──────────────────────────────────────────────

def scrape_album(conn, session, page_title, category=None, source_url=None):
    """Scrape a single album page and store in DB.

    Args:
        category: Wikipedia category this page belongs to (used to determine
                  whether the release is a complete show or possibly edited).

    Returns (release_id, track_count) or (None, 0) if skipped/failed.
    """
    # Check if already scraped
    existing_id = db.release_exists(conn, page_title)
    if existing_id:
        return existing_id, 0

    html_text = fetch_page_html(session, page_title)
    if not html_text:
        return None, 0

    # Parse infobox
    info = parse_infobox(html_text)
    concert_date = parse_concert_date(info.get("recorded"))
    # Per-release override takes priority, then category default
    coverage = RELEASE_COVERAGE_OVERRIDES.get(
        page_title, CATEGORY_COVERAGE.get(category, "unknown")
    )

    # Parse venue into structured fields
    venue_name, city, state = parse_venue_location(info.get("venue"))

    if not source_url:
        safe_title = page_title.replace(" ", "_")
        source_url = f"https://en.wikipedia.org/wiki/{safe_title}"

    # Insert release
    release_id = db.insert_release(
        conn,
        source_type="wikipedia",
        source_id=page_title,
        title=page_title,
        concert_date=concert_date,
        venue=venue_name,
        city=city,
        state=state,
        coverage=coverage,
        recording_type="official",
        quality_rank=500,
        release_date=info.get("released"),
        label=info.get("label"),
        source_url=source_url,
    )

    # Parse and insert tracks
    tracks = parse_tracks(html_text)
    for t in tracks:
        song_id, _, _ = normalize_song(conn, t["title_raw"])
        db.insert_track(
            conn,
            release_id=release_id,
            title_raw=t["title_raw"],
            disc_number=t.get("disc", 1),
            track_number=t["track"],
            song_id=song_id,
            set_name=t.get("set_name"),
            duration_seconds=t.get("duration"),
            writers=t.get("writers"),
            segue=t.get("segue", 0),
        )
    conn.commit()

    return release_id, len(tracks)


def scrape_all(conn, full=False, verbose=True):
    """Scrape all Wikipedia categories.

    Args:
        conn: DB connection
        full: If True, re-scrape everything (ignore scrape_state)
        verbose: Print progress
    """
    session = _session()
    total_releases = 0
    total_tracks = 0

    # Phase 1: enumerate all pages across categories
    # Collect (category, page_title) pairs, deduplicating across categories
    work = []  # list of (category, page_title)
    seen_pages = set()
    categories_to_mark = []

    for category in WIKIPEDIA_CATEGORIES:
        state_key = f"category_done:{category}"
        if not full and db.get_scrape_state(conn, state_key):
            if verbose:
                print(f"  Skipping {category} (already scraped)")
            continue

        if verbose:
            print(f"  Fetching category: {category} ...", end=" ", flush=True)

        try:
            pages = get_category_members(session, category)
        except Exception as e:
            print(f"ERROR: {e}")
            continue

        cat_count = 0
        for page_title in pages:
            if page_title in seen_pages:
                continue
            seen_pages.add(page_title)
            if page_title.startswith("Category:") or page_title.startswith("List of"):
                continue
            work.append((category, page_title))
            cat_count += 1

        categories_to_mark.append(state_key)
        if verbose:
            print(f"{cat_count} pages")

    if not work:
        if verbose:
            print("  Nothing to scrape.")
        return 0, 0

    if verbose:
        print(f"\n  Total: {len(work)} pages to process\n")

    # Phase 2: scrape each page with progress reporting
    t_start = time.monotonic()
    for i, (category, page_title) in enumerate(work, 1):
        pct = i * 100 // len(work)
        elapsed = time.monotonic() - t_start
        rate = i / elapsed if elapsed > 0 else 0
        eta = (len(work) - i) / rate if rate > 0 else 0
        prefix = f"  [{i}/{len(work)} {pct:>3}% {elapsed:.0f}s eta {eta:.0f}s]"

        try:
            release_id, track_count = scrape_album(conn, session, page_title,
                                                       category=category)
            if track_count > 0:
                total_releases += 1
                total_tracks += track_count
                if verbose:
                    print(f"{prefix} {page_title}: {track_count} tracks "
                          f"(total: {total_releases} releases, {total_tracks} tracks)")
            elif release_id:
                if verbose:
                    print(f"{prefix} {page_title}: already in DB")
            else:
                if verbose:
                    print(f"{prefix} {page_title}: no tracks found")
        except Exception as e:
            print(f"{prefix} ERROR on {page_title}: {e}")
            continue

    # Mark all categories as done
    for state_key in categories_to_mark:
        db.set_scrape_state(conn, state_key, "done")

    if verbose:
        print(f"\n  Done: {total_releases} new releases, {total_tracks} tracks")

    return total_releases, total_tracks
