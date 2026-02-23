"""Tests for MusicBrainz date parsing and release processing."""

from gdtimings.musicbrainz import parse_date_from_title


class TestParseDateFromTitle:
    """Tests for extracting concert dates from MusicBrainz media titles."""

    def test_us_format_short_year(self):
        """US date with 2-digit year: 6/22/73 → 1973-06-22."""
        title = "P.N.E. Coliseum -- Vancouver, B.C., Canada - 6/22/73"
        assert parse_date_from_title(title) == "1973-06-22"

    def test_us_format_full_year(self):
        """US date with 4-digit year: 12/31/1978 → 1978-12-31."""
        title = "Winterland Arena - 12/31/1978"
        assert parse_date_from_title(title) == "1978-12-31"

    def test_iso_format(self):
        """ISO date: 1974-05-21."""
        title = "Seattle Center Arena, Seattle, WA 1974-05-21"
        assert parse_date_from_title(title) == "1974-05-21"

    def test_bare_us_date(self):
        """Bare US date without surrounding text."""
        assert parse_date_from_title("5/21/74") == "1974-05-21"

    def test_no_date(self):
        """Titles without dates should return None."""
        assert parse_date_from_title("Disc 1") is None
        assert parse_date_from_title("") is None
        assert parse_date_from_title(None) is None

    def test_out_of_range_year(self):
        """Years outside 1965-1995 should not match (not GD era)."""
        assert parse_date_from_title("2020-01-15") is None

    def test_ambiguous_date_in_long_title(self):
        """Extract date from a full venue description."""
        title = "Boston Music Hall, Boston, MA 6/9/76"
        assert parse_date_from_title(title) == "1976-06-09"

    def test_single_digit_month_day(self):
        """Single-digit month and day: 3/1/73."""
        assert parse_date_from_title("3/1/73") == "1973-03-01"

    def test_bullet_separator(self):
        """Bullet separator in Pacific Northwest box set disc titles."""
        title = "P.N.E. Coliseum -- Vancouver, B.C., Canada \u2022 6/22/73"
        assert parse_date_from_title(title) == "1973-06-22"

    def test_dash_separator_with_city_state(self):
        """Dash separator: Winterland Arena, San Francisco, CA - 6/7/77."""
        title = "Winterland Arena, San Francisco, CA - 6/7/77"
        assert parse_date_from_title(title) == "1977-06-07"
