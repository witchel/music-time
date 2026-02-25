"""Tests for phishtimings.normalize — clean_title and normalize_song."""

import pytest

from phishtimings.normalize import clean_title, normalize_song


class TestCleanTitle:
    """Test clean_title stripping and filtering."""

    # Passthrough
    def test_simple_title(self):
        assert clean_title("Tweezer") == "Tweezer"

    def test_title_with_spaces(self):
        assert clean_title("You Enjoy Myself") == "You Enjoy Myself"

    # Segment labels
    def test_strip_part_number(self):
        assert clean_title("Tweezer part 1") == "Tweezer"

    def test_strip_part_paren(self):
        assert clean_title("Tweezer (Part 2)") == "Tweezer"

    def test_strip_v_number(self):
        assert clean_title("Fluffhead V1") == "Fluffhead"

    def test_strip_verse(self):
        assert clean_title("Fluffhead verse 3") == "Fluffhead"

    def test_strip_continued(self):
        assert clean_title("Tweezer continued") == "Tweezer"

    def test_strip_continued_paren(self):
        assert clean_title("Tweezer (continued)") == "Tweezer"

    # Segue markers
    def test_strip_segue_arrow(self):
        assert clean_title("Gin >") == "Gin"

    def test_strip_segue_dash_arrow(self):
        assert clean_title("Gin ->") == "Gin"

    def test_strip_unicode_arrow(self):
        assert clean_title("Gin \u2192") == "Gin"

    def test_strip_segue_with_space(self):
        """Trailing space after segue arrow is also stripped."""
        assert clean_title("Bathtub Gin > ") == "Bathtub Gin"

    # Non-songs
    def test_tuning(self):
        assert clean_title("Tuning") == ""

    def test_crowd_noise(self):
        assert clean_title("Crowd Noise") == ""

    def test_banter(self):
        assert clean_title("Banter") == ""

    def test_set_break(self):
        assert clean_title("Set Break") == ""

    def test_soundcheck(self):
        assert clean_title("Soundcheck") == ""

    # Whitespace
    def test_leading_trailing_spaces(self):
        assert clean_title("  Tweezer  ") == "Tweezer"

    def test_internal_whitespace(self):
        """Multiple internal spaces are collapsed to one."""
        assert clean_title("You  Enjoy   Myself") == "You Enjoy Myself"

    # Empty/short
    def test_empty_string(self):
        assert clean_title("") == ""

    def test_single_letter(self):
        assert clean_title("x") == ""

    def test_numbers_only(self):
        assert clean_title("123") == ""

    # Combined patterns
    def test_segue_and_part(self):
        """Segue arrow is stripped but segment label remains (regex order)."""
        # clean_title strips segment labels first (anchored to $), then segue
        # markers. When both are present, the segment regex doesn't match
        # because the arrow follows it; only the arrow gets stripped.
        assert clean_title("  Tweezer part 1 ->  ") == "Tweezer part 1"


class TestNormalizeSong:
    """Test normalize_song DB integration."""

    def test_new_song_creation(self, conn):
        """First encounter creates a new song."""
        song_id, name, match_type = normalize_song(conn, "Tweezer")
        assert song_id is not None
        assert name == "Tweezer"
        assert match_type == "new"

    def test_alias_lookup_second_call(self, conn):
        """Second call finds the alias created by the first."""
        sid1, _, _ = normalize_song(conn, "Tweezer")
        sid2, name2, match2 = normalize_song(conn, "Tweezer")
        assert sid2 == sid1
        assert match2 == "alias"

    def test_case_insensitive_match(self, conn):
        """Different casing matches existing canonical name."""
        sid1, _, _ = normalize_song(conn, "Tweezer")
        sid2, name2, match2 = normalize_song(conn, "tweezer")
        assert sid2 == sid1
        # Could be "alias" (from alias table) or "exact" (from canonical match)
        assert match2 in ("alias", "exact")

    def test_non_song_returns_none(self, conn):
        """Non-song titles return None tuple."""
        assert normalize_song(conn, "Tuning") == (None, None, None)

    def test_empty_title_returns_none(self, conn):
        """Empty string returns None tuple."""
        assert normalize_song(conn, "") == (None, None, None)

    def test_fuzzy_match(self, conn):
        """Fuzzy match works when song has >= 10 tracks."""
        from tests.conftest import make_release, make_track

        # Create a song with 10+ tracks so fuzzy matching activates
        sid, _, _ = normalize_song(conn, "Bathtub Gin")
        rid = make_release(conn, source_id="fuzzy-test", concert_date="2000-01-01")
        for i in range(10):
            make_track(conn, release_id=rid, song_id=sid, duration=300, track_num=i + 1)
        conn.commit()

        # Now a close variant should fuzzy-match
        sid2, name2, match2 = normalize_song(conn, "Bathtub Ginn")
        assert sid2 == sid
        assert name2 == "Bathtub Gin"
        assert match2 == "fuzzy"
