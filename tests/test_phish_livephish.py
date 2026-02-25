"""Tests for phishtimings.livephish module."""

import pytest
from phishtimings.livephish import _parse_lp_date, _set_name_from_num, _process_container_from_cache
from tests.conftest import make_release


class TestParseLpDate:
    """Test LivePhish MM/DD/YYYY -> ISO date conversion."""

    def test_valid_date(self):
        assert _parse_lp_date("07/25/2003") == "2003-07-25"

    def test_single_digit_month(self):
        assert _parse_lp_date("7/25/2003") == "2003-07-25"

    def test_single_digit_day(self):
        assert _parse_lp_date("07/5/2003") == "2003-07-05"

    def test_year_min_boundary(self):
        assert _parse_lp_date("12/31/1983") == "1983-12-31"

    def test_year_max_boundary(self):
        assert _parse_lp_date("01/01/2026") == "2026-01-01"

    def test_year_below_min(self):
        assert _parse_lp_date("01/01/1982") is None

    def test_year_above_max(self):
        assert _parse_lp_date("01/01/2027") is None

    def test_empty_string(self):
        assert _parse_lp_date("") is None

    def test_none(self):
        assert _parse_lp_date(None) is None

    def test_iso_format_rejected(self):
        """ISO format should not match MM/DD/YYYY pattern."""
        assert _parse_lp_date("2003-07-25") is None

    def test_invalid_month(self):
        assert _parse_lp_date("13/25/2003") is None

    def test_invalid_day(self):
        assert _parse_lp_date("07/32/2003") is None


class TestSetNameFromNum:
    """Test LivePhish set number -> name conversion."""

    def test_set_1(self):
        assert _set_name_from_num(1) == "Set 1"

    def test_set_2(self):
        assert _set_name_from_num(2) == "Set 2"

    def test_set_3(self):
        assert _set_name_from_num(3) == "Set 3"

    def test_encore(self):
        assert _set_name_from_num(4) == "Encore"

    def test_encore_2(self):
        assert _set_name_from_num(5) == "Encore 2"

    def test_encore_3(self):
        assert _set_name_from_num(6) == "Encore 3"

    def test_zero(self):
        assert _set_name_from_num(0) is None

    def test_none(self):
        assert _set_name_from_num(None) is None

    def test_string_input(self):
        """LivePhish JSON may have string numbers."""
        assert _set_name_from_num("2") == "Set 2"


class TestProcessContainerFromCache:
    """Test _process_container_from_cache with various cached data structures."""

    def _make_cached_show(self, container_id="12345", perf_date="07/25/2003",
                          venue="Madison Square Garden", city="New York",
                          state="NY", tracks=None):
        """Build a minimal cached LivePhish show dict."""
        if tracks is None:
            tracks = [
                {"songTitle": "Tweezer", "totalRunningTime": "420.5",
                 "setNum": 1, "discNum": 1, "trackNum": 1},
                {"songTitle": "Bathtub Gin", "totalRunningTime": "600.0",
                 "setNum": 1, "discNum": 1, "trackNum": 2},
            ]
        return {
            "Response": {
                "containerID": container_id,
                "performanceDate": perf_date,
                "containerInfo": f"LivePhish: {perf_date}",
                "venueName": venue,
                "venueCity": city,
                "venueState": state,
                "tracks": tracks,
            }
        }

    def test_happy_path(self, conn):
        """Valid show inserts release + tracks."""
        data = self._make_cached_show()
        existing_dates = set()
        r, t = _process_container_from_cache(conn, data, existing_dates, verbose=False)
        assert r == 1
        assert t == 2

    def test_source_id_dedup(self, conn):
        """Same container_id skips on second import."""
        data = self._make_cached_show()
        existing_dates = set()
        _process_container_from_cache(conn, data, existing_dates, verbose=False)
        r, t = _process_container_from_cache(conn, data, existing_dates, verbose=False)
        assert (r, t) == (0, 0)

    def test_date_dedup_across_sources(self, conn):
        """Shows whose date already exists in DB from ANY source are skipped.
        This validates the bug fix -- previously only checked MusicBrainz.
        """
        # Insert a phish.in release for this date
        make_release(conn, source_id="pi:2003-07-25",
                     concert_date="2003-07-25", quality_rank=300)
        conn.commit()

        data = self._make_cached_show(perf_date="07/25/2003")
        existing_dates = {"2003-07-25"}  # pre-populated with the phishin date
        r, t = _process_container_from_cache(conn, data, existing_dates, verbose=False)
        assert (r, t) == (0, 0)

    def test_date_added_to_set_after_insert(self, conn):
        """After successful insert, concert_date is added to existing_dates."""
        data = self._make_cached_show()
        existing_dates = set()
        _process_container_from_cache(conn, data, existing_dates, verbose=False)
        assert "2003-07-25" in existing_dates

    def test_invalid_date(self, conn):
        """Shows with unparseable dates are skipped."""
        data = self._make_cached_show(perf_date="invalid")
        r, t = _process_container_from_cache(conn, data, set(), verbose=False)
        assert (r, t) == (0, 0)

    def test_missing_container_id(self, conn):
        """Shows without containerID are skipped."""
        data = {"Response": {"performanceDate": "07/25/2003"}}
        r, t = _process_container_from_cache(conn, data, set(), verbose=False)
        assert (r, t) == (0, 0)

    def test_duration_parsing(self, conn):
        """totalRunningTime string is parsed as float seconds."""
        data = self._make_cached_show(tracks=[
            {"songTitle": "Tweezer", "totalRunningTime": "420.5",
             "setNum": 1, "discNum": 1, "trackNum": 1},
        ])
        _process_container_from_cache(conn, data, set(), verbose=False)
        row = conn.execute("SELECT duration_seconds FROM tracks").fetchone()
        assert row["duration_seconds"] == pytest.approx(420.5)

    def test_set_name_mapping(self, conn):
        """setNum is correctly mapped to set_name."""
        data = self._make_cached_show(tracks=[
            {"songTitle": "Tweezer", "totalRunningTime": "300",
             "setNum": 4, "discNum": 1, "trackNum": 1},
        ])
        _process_container_from_cache(conn, data, set(), verbose=False)
        row = conn.execute("SELECT set_name FROM tracks").fetchone()
        assert row["set_name"] == "Encore"
