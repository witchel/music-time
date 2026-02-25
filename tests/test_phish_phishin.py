"""Tests for phishtimings.phishin module."""

import pytest
from phishtimings.db import dates_already_in_db
from phishtimings.phishin import _process_show_from_cache
from tests.conftest import make_release


class TestDatesAlreadyInDb:
    """Test dates_already_in_db helper."""

    def test_empty_db(self, conn):
        """Empty DB returns empty set."""
        assert dates_already_in_db(conn) == set()

    def test_multi_source_dates(self, conn):
        """Returns dates from all source types."""
        make_release(conn, source_id="mb:r1:2003-07-25",
                     concert_date="2003-07-25", quality_rank=500)
        make_release(conn, source_id="lp:12345",
                     concert_date="2004-06-20", quality_rank=500)
        make_release(conn, source_id="pi:1999-12-31",
                     concert_date="1999-12-31", quality_rank=300)
        conn.commit()
        dates = dates_already_in_db(conn)
        assert dates == {"2003-07-25", "2004-06-20", "1999-12-31"}

    def test_null_date_excluded(self, conn):
        """Releases with NULL concert_date are excluded."""
        make_release(conn, source_id="test-null", concert_date=None)
        conn.commit()
        assert dates_already_in_db(conn) == set()


class TestProcessShowFromCache:
    """Test _process_show_from_cache with various cached data structures."""

    def _make_cached_show(self, date="2003-07-25", venue_name="Madison Square Garden",
                          city="New York", state="NY", tracks=None):
        """Build a minimal cached phish.in show dict."""
        if tracks is None:
            tracks = [
                {"title": "Tweezer", "duration": 420500,
                 "set_name": "Set 1", "position": 1},
                {"title": "Bathtub Gin", "duration": 600000,
                 "set_name": "Set 1", "position": 2},
            ]
        return {
            "date": date,
            "venue_name": venue_name,
            "venue": {"name": venue_name, "city": city, "state": state},
            "tracks": tracks,
        }

    def test_happy_path(self, conn):
        """Valid show inserts release + tracks."""
        data = self._make_cached_show()
        existing_dates = set()
        r, t = _process_show_from_cache(conn, data, existing_dates, verbose=False)
        assert r == 1
        assert t == 2

    def test_source_id_dedup(self, conn):
        """Same date skips on second import (same source_id)."""
        data = self._make_cached_show()
        existing_dates = set()
        _process_show_from_cache(conn, data, existing_dates, verbose=False)
        # Reset existing_dates to test source_id check, not date check
        r, t = _process_show_from_cache(conn, data, set(), verbose=False)
        assert (r, t) == (0, 0)

    def test_date_dedup(self, conn):
        """Shows whose date is in existing_dates are skipped."""
        data = self._make_cached_show(date="2003-07-25")
        existing_dates = {"2003-07-25"}
        r, t = _process_show_from_cache(conn, data, existing_dates, verbose=False)
        assert (r, t) == (0, 0)

    def test_date_added_to_set(self, conn):
        """After successful insert, date is added to existing_dates."""
        data = self._make_cached_show()
        existing_dates = set()
        _process_show_from_cache(conn, data, existing_dates, verbose=False)
        assert "2003-07-25" in existing_dates

    def test_ms_to_seconds_conversion(self, conn):
        """Duration in ms is correctly converted to seconds."""
        data = self._make_cached_show(tracks=[
            {"title": "Tweezer", "duration": 420500,
             "set_name": "Set 1", "position": 1},
        ])
        _process_show_from_cache(conn, data, set(), verbose=False)
        row = conn.execute("SELECT duration_seconds FROM tracks").fetchone()
        assert row["duration_seconds"] == pytest.approx(420.5)

    def test_null_duration(self, conn):
        """Tracks with null duration are stored as None."""
        data = self._make_cached_show(tracks=[
            {"title": "Tweezer", "duration": None,
             "set_name": "Set 1", "position": 1},
        ])
        _process_show_from_cache(conn, data, set(), verbose=False)
        row = conn.execute("SELECT duration_seconds FROM tracks").fetchone()
        assert row["duration_seconds"] is None

    def test_missing_date(self, conn):
        """Shows without date are skipped."""
        data = {"tracks": [{"title": "Tweezer", "duration": 300000}]}
        r, t = _process_show_from_cache(conn, data, set(), verbose=False)
        assert (r, t) == (0, 0)

    def test_recording_type_audience(self, conn):
        """phish.in releases are stored as 'audience' recording type."""
        data = self._make_cached_show()
        _process_show_from_cache(conn, data, set(), verbose=False)
        row = conn.execute("SELECT recording_type FROM releases").fetchone()
        assert row["recording_type"] == "audience"

    def test_source_url_format(self, conn):
        """source_url follows phish.in URL pattern."""
        data = self._make_cached_show(date="2003-07-25")
        _process_show_from_cache(conn, data, set(), verbose=False)
        row = conn.execute("SELECT source_url FROM releases").fetchone()
        assert row["source_url"] == "https://phish.in/2003-07-25"
