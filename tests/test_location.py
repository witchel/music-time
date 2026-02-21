"""Tests for location parsing and state normalization."""

from gdtimings.location import normalize_state, parse_city_state, is_us_state


class TestNormalizeState:

    def test_abbreviation(self):
        assert normalize_state("CA") == "California"
        assert normalize_state("NY") == "New York"

    def test_full_name_passthrough(self):
        assert normalize_state("California") == "California"

    def test_dotted_abbreviation(self):
        assert normalize_state("R.I.") == "Rhode Island"
        assert normalize_state("D.C.") == "District of Columbia"

    def test_informal_abbreviation(self):
        assert normalize_state("Mass") == "Massachusetts"
        assert normalize_state("Calif") == "California"

    def test_trailing_punctuation(self):
        assert normalize_state("CT.") == "Connecticut"
        assert normalize_state("PA,") == "Pennsylvania"

    def test_non_us_passthrough(self):
        assert normalize_state("England") == "England"
        assert normalize_state("Ontario") == "Ontario"

    def test_none_and_empty(self):
        assert normalize_state(None) is None
        assert normalize_state("") is None
        assert normalize_state("   ") is None


class TestParseCityState:

    def test_city_state_abbreviation(self):
        assert parse_city_state("Philadelphia, PA") == ("Philadelphia", "Pennsylvania")

    def test_city_state_full(self):
        assert parse_city_state("New York, New York") == ("New York", "New York")

    def test_non_us(self):
        assert parse_city_state("London, England") == ("London", "England")

    def test_city_only(self):
        assert parse_city_state("Philadelphia") == ("Philadelphia", None)

    def test_empty(self):
        assert parse_city_state("") == (None, None)
        assert parse_city_state(None) == (None, None)


class TestIsUsState:

    def test_abbreviation(self):
        assert is_us_state("CA") is True

    def test_full_name(self):
        assert is_us_state("California") is True

    def test_non_us(self):
        assert is_us_state("England") is False

    def test_empty(self):
        assert is_us_state("") is False
        assert is_us_state(None) is False
