"""Tests for phishtimings.musicbrainz date and location parsing."""

from phishtimings.musicbrainz import (
    parse_date_from_title,
    _parse_location_from_title,
    _process_release_from_cache,
)


class TestParseDateFromTitle:
    """Test date extraction from MusicBrainz title strings."""

    # ISO format
    def test_iso_date(self):
        assert parse_date_from_title("2003-07-25: Some Show") == "2003-07-25"

    def test_iso_date_only(self):
        assert parse_date_from_title("2003-07-25") == "2003-07-25"

    # US format
    def test_us_short_year(self):
        assert parse_date_from_title("Live Phish 7/25/03") == "2003-07-25"

    def test_us_full_year(self):
        assert parse_date_from_title("Live Phish 12/31/2003") == "2003-12-31"

    # Year range (Phish: 1983-2026)
    def test_year_min_boundary(self):
        assert parse_date_from_title("1983-12-02: Debut") == "1983-12-02"

    def test_year_max_boundary(self):
        assert parse_date_from_title("2026-01-01: Future") == "2026-01-01"

    def test_year_below_min(self):
        assert parse_date_from_title("1982-12-31: Too Early") is None

    def test_year_above_max(self):
        assert parse_date_from_title("2027-01-01: Too Late") is None

    # Short year pivot: >= 60 → 1900s, < 60 → 2000s
    def test_short_year_60(self):
        """60 -> 1960, below min_year 1983 -> None."""
        assert parse_date_from_title("Live Phish 1/1/60") is None

    def test_short_year_83(self):
        """83 -> 1983 (min year), valid."""
        assert parse_date_from_title("Live Phish 12/2/83") == "1983-12-02"

    def test_short_year_99(self):
        """99 -> 1999, valid."""
        assert parse_date_from_title("Live Phish 12/31/99") == "1999-12-31"

    def test_short_year_00(self):
        """00 -> 2000, valid."""
        assert parse_date_from_title("Live Phish 1/1/00") == "2000-01-01"

    def test_short_year_25(self):
        """25 -> 2025, valid."""
        assert parse_date_from_title("Live Phish 6/15/25") == "2025-06-15"

    # No date / empty / None
    def test_no_date(self):
        assert parse_date_from_title("Just a Title") is None

    def test_empty_string(self):
        assert parse_date_from_title("") is None

    def test_none(self):
        assert parse_date_from_title(None) is None


class TestParseLocationFromTitle:
    """Test venue/city/state extraction from MB title strings."""

    def test_full_with_country(self):
        """Standard format: 'DATE: Venue, City, ST, Country'."""
        venue, city, state = _parse_location_from_title(
            "2003-07-25: Verizon Wireless Amphitheatre, Charlotte, NC, USA"
        )
        assert venue == "Verizon Wireless Amphitheatre"
        assert city == "Charlotte"
        assert state is not None  # normalize_state may return full or abbr

    def test_without_country(self):
        """Format without trailing country: 'DATE: Venue, City, ST'."""
        venue, city, state = _parse_location_from_title(
            "1999-12-31: Big Cypress Seminole Reservation, Big Cypress, FL"
        )
        assert venue == "Big Cypress Seminole Reservation"
        assert city == "Big Cypress"
        assert state is not None

    def test_no_match(self):
        """Title without location pattern returns None tuple."""
        assert _parse_location_from_title("Live Phish Vol. 1") == (None, None, None)

    def test_empty_string(self):
        assert _parse_location_from_title("") == (None, None, None)

    def test_none(self):
        assert _parse_location_from_title(None) == (None, None, None)


class TestProcessReleaseFromCacheDateDedup:
    """Test date-dedup in _process_release_from_cache."""

    def _make_cached_release(self, rg_id="rg-1", release_mbid="rel-1",
                              title="2003-07-25: MSG, New York, NY, USA",
                              disc_date="2003-07-25"):
        """Build minimal cached MB release data."""
        return {
            "rg_id": rg_id,
            "rg_title": title,
            "release": {
                "id": release_mbid,
                "title": title,
                "medium-list": [{
                    "position": "1",
                    "title": disc_date,
                    "track-list": [{
                        "position": "1",
                        "recording": {
                            "title": "Tweezer",
                            "length": "420000",
                        },
                    }],
                }],
            },
        }

    def test_skips_existing_date(self, conn):
        """Release whose concert_date is already in DB is skipped."""
        cached = self._make_cached_release()
        existing_dates = {"2003-07-25"}
        r, t = _process_release_from_cache(
            conn, cached, coverage="complete",
            existing_dates=existing_dates, verbose=False,
        )
        assert (r, t) == (0, 0)

    def test_inserts_new_date(self, conn):
        """Release with fresh date is inserted."""
        cached = self._make_cached_release()
        existing_dates = set()
        r, t = _process_release_from_cache(
            conn, cached, coverage="complete",
            existing_dates=existing_dates, verbose=False,
        )
        assert r == 1
        assert t == 1

    def test_adds_date_to_set(self, conn):
        """After insert, date is added to existing_dates."""
        cached = self._make_cached_release()
        existing_dates = set()
        _process_release_from_cache(
            conn, cached, coverage="complete",
            existing_dates=existing_dates, verbose=False,
        )
        assert "2003-07-25" in existing_dates

    def test_multi_date_release_partial_dedup(self, conn):
        """Multi-date release: only non-duplicate dates are inserted."""
        cached = {
            "rg_id": "rg-multi",
            "rg_title": "Box Set",
            "release": {
                "id": "rel-multi",
                "title": "Box Set",
                "medium-list": [
                    {
                        "position": "1",
                        "title": "2003-07-25",
                        "track-list": [{"position": "1", "recording": {
                            "title": "Tweezer", "length": "300000"}}],
                    },
                    {
                        "position": "2",
                        "title": "2003-07-26",
                        "track-list": [{"position": "1", "recording": {
                            "title": "Stash", "length": "400000"}}],
                    },
                ],
            },
        }
        # 07-25 already exists, 07-26 is new
        existing_dates = {"2003-07-25"}
        r, t = _process_release_from_cache(
            conn, cached, coverage="complete",
            existing_dates=existing_dates, verbose=False,
        )
        assert r == 1  # only 07-26 inserted
        assert t == 1
        assert "2003-07-26" in existing_dates
