"""Shared location parsing for venue/city/state extraction."""

# 50 US states + DC: abbreviation → full name
US_STATE_ABBREV = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
}

# Reverse lookup: full name → full name (for pass-through)
_FULL_STATE_NAMES = {v: v for v in US_STATE_ABBREV.values()}


def normalize_state(raw):
    """Convert state abbreviation to full name, or pass through full names.

    Returns None if input is None/empty.
    Non-US locations (e.g. "Ontario") are passed through unchanged.
    """
    if not raw:
        return None
    raw = raw.strip()
    upper = raw.upper()
    if upper in US_STATE_ABBREV:
        return US_STATE_ABBREV[upper]
    if raw in _FULL_STATE_NAMES:
        return raw
    # Non-US or unrecognized — pass through as-is
    return raw


def is_us_state(text):
    """Return True if text is a US state name or abbreviation."""
    if not text:
        return False
    text = text.strip()
    return text.upper() in US_STATE_ABBREV or text in _FULL_STATE_NAMES


def parse_city_state(text):
    """Split 'City, State' into (city, state_full_name).

    Handles:
        "Philadelphia, PA"       → ("Philadelphia", "Pennsylvania")
        "San Francisco, CA"      → ("San Francisco", "California")
        "New York, New York"     → ("New York", "New York")
        "London, England"        → ("London", "England")
        "Philadelphia"           → ("Philadelphia", None)
        ""                       → (None, None)

    Returns (city, state) tuple. State is normalized to full name for US states.
    """
    if not text or not text.strip():
        return None, None

    text = text.strip()
    if "," in text:
        parts = text.split(",", 1)
        city = parts[0].strip() or None
        state = normalize_state(parts[1].strip()) if parts[1].strip() else None
        return city, state

    # No comma — treat as city only
    return text, None
