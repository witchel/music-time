"""Tests for song name normalization and alias resolution."""

import pytest

from gdtimings.normalize import clean_title, normalize_song


class TestCleanTitle:
    """Tests for the clean_title() regex pipeline."""

    def test_plain_title(self):
        assert clean_title("Dark Star") == "Dark Star"

    def test_strip_track_number_dot(self):
        assert clean_title("1. Dark Star") == "Dark Star"
        assert clean_title("01. Dark Star") == "Dark Star"

    def test_strip_track_number_paren(self):
        assert clean_title("3) Truckin'") == "Truckin'"

    def test_strip_numbered_dash(self):
        assert clean_title("02 - Sugar Magnolia") == "Sugar Magnolia"
        assert clean_title("14 \u2013 Eyes of the World") == "Eyes of the World"

    def test_strip_disc_track_prefix(self):
        assert clean_title("d1t01 - Dark Star") == "Dark Star"
        assert clean_title("d2t05. Truckin'") == "Truckin'"

    def test_strip_identifier_prefix(self):
        assert clean_title("gd77-05-08d1t01 - Dark Star") == "Dark Star"
        assert clean_title("gd1977-05-08d1t01 - Dark Star") == "Dark Star"
        # Space-separated set/track: "gd81-12-28 s2t07 Drums"
        assert clean_title("gd81-12-28 s2t07 Drums") == "Drums"
        assert clean_title("gd83-10-11 s2t03 I Need A Miracle") == "I Need A Miracle"
        # Space between set and track: "gd79-07-01 s1 t02 Title"
        assert clean_title("gd79-07-01 s1 t02 Franklin's Tower") == "Franklin's Tower"
        # Track-only, no disc/set: "gd73-06-22 t01 Bertha"
        assert clean_title("gd73-06-22 t01 Bertha") == "Bertha"

    def test_strip_disc_track_comma(self):
        """Disc01,Track01 format from some archive.org releases."""
        assert clean_title("Disc01,Track01 Hell In A Bucket") == "Hell In A Bucket"
        assert clean_title("Disc02,Track03 Truckin'") == "Truckin'"
        assert clean_title("Disc01,Track01 Tuning") == "Tuning"

    def test_bare_disc_track_code_dropped(self):
        """Bare D1T12 codes with no song name are dropped."""
        assert clean_title("D1T12") == ""
        assert clean_title("D2T05") == ""

    def test_spelled_out_disc_track(self):
        """Spelled-out disc/track prefixes."""
        assert clean_title('Disc five, track seven: "Jam into Days Between') == "Jam into Days Between"
        assert clean_title('Disc two, track two: "Beautiful Jam') == "Beautiful Jam"

    def test_strip_duration_suffix(self):
        assert clean_title("Dark Star \u2013 14:35") == "Dark Star"
        assert clean_title("Truckin' - 5:32") == "Truckin'"
        assert clean_title("Drums \u2014 1:05:32") == "Drums"

    def test_strip_segue_markers(self):
        assert clean_title("Dark Star >") == "Dark Star"
        assert clean_title("Dark Star \u2192") == "Dark Star"
        assert clean_title("St. Stephen >  ") == "St. Stephen"
        # Arrow variants: -> should also be stripped
        assert clean_title("Dark Star ->") == "Dark Star"
        assert clean_title("Let The Good Times Roll ->") == "Let The Good Times Roll"

    def test_strip_set_annotations(self):
        assert clean_title("Dark Star [Set 1]") == "Dark Star"
        assert clean_title("Truckin' (Disc 2)") == "Truckin'"
        assert clean_title("Morning Dew [Encore]") == "Morning Dew"

    def test_strip_segment_labels(self):
        assert clean_title("Dark Star V1") == "Dark Star"
        assert clean_title("Dark Star (V2)") == "Dark Star"
        assert clean_title("Playing in the Band part 1") == "Playing in the Band"
        assert clean_title("Space (continued)") == "Space"

    def test_preserve_reprise(self):
        """Reprise is a distinct song (Category A), not a segment."""
        assert clean_title("Playing in the Band Reprise") == "Playing in the Band Reprise"

    def test_strip_footnote_markers(self):
        assert clean_title("Dark Star [a]") == "Dark Star"
        assert clean_title("Truckin' [1]") == "Truckin'"

    def test_strip_surrounding_quotes(self):
        assert clean_title('"Dark Star"') == "Dark Star"
        assert clean_title("'Dark Star'") == "Dark Star"

    def test_preserve_trailing_apostrophe(self):
        """Truckin' should keep its apostrophe (not treated as a quote)."""
        assert clean_title("Truckin'") == "Truckin'"

    def test_normalize_fancy_quotes(self):
        assert clean_title("\u201cDark Star\u201d") == "Dark Star"
        # \u2019 (right single quote) is normalized to straight apostrophe
        assert clean_title("Truckin\u2019") == "Truckin'"

    def test_strip_writer_credits(self):
        assert clean_title('"Dark Star" (Garcia, Lesh, Hart)') == "Dark Star"

    def test_multiline_takes_first(self):
        assert clean_title("Dark Star\nSome venue info") == "Dark Star"

    def test_empty_and_whitespace(self):
        assert clean_title("") == ""
        assert clean_title("   ") == ""

    def test_strip_trailing_backslash(self):
        assert clean_title("Gimme Some Lovin\\") == "Gimme Some Lovin"

    def test_strip_bracketed_metadata(self):
        assert clean_title("[crowd]") == ""

    def test_multi_song_combo_dropped(self):
        """Multi-song combo tracks are dropped (return empty)."""
        assert clean_title("Alligator > Drums > Jam") == ""
        assert clean_title("Help On The Way > Slipknot! > Franklin's Tower") == ""
        assert clean_title("Me & My Uncle > Mexicali Blues") == ""
        assert clean_title("Drums > Space") == ""
        assert clean_title("Drums->Space") == ""
        assert clean_title("Lazy Lightning -> Supplication") == ""
        assert clean_title("Good Lovin' > La Bamba > Good Lovin") == ""
        # Trailing apostrophe before segue
        assert clean_title("Lazy Lightnin' > Supplication") == ""
        assert clean_title("Truckin' > Spoonful Jam") == ""

    def test_dotted_tape_flip_names_cleaned(self):
        """Tape-flip dotted names like Dru..ms are cleaned of dots."""
        # The > is preserved (tape-flip annotation, not a segue)
        result = clean_title("Dru..ms > (Tape Flip)")
        assert "Drums" in result
        assert ".." not in result
        result = clean_title("S..pace > (Tape Flip Near Start)")
        assert "Space" in result
        assert ".." not in result

    def test_tape_flip_annotation_preserved(self):
        """Tape-flip annotations with > are single songs, not combos."""
        assert clean_title("Dru..ms > (Tape Flip)") != ""
        assert clean_title("S..pace > (Tape Flip Near Start)") != ""

    def test_simple_segue_preserved(self):
        """Single segue marker (not a sequence) is handled by existing logic."""
        assert clean_title("Scarlet Begonias") == "Scarlet Begonias"

    def test_combined_stripping(self):
        """Multiple cleanup steps at once."""
        assert clean_title('01. "Dark Star" (Garcia) \u2013 14:35 >') == "Dark Star"


class TestNormalizeSong:
    """Tests for the full normalize_song() resolution pipeline."""

    def test_exact_canonical_match(self, conn):
        song_id, name, match = normalize_song(conn, "Dark Star")
        assert name == "Dark Star"
        assert match in ("exact", "alias")
        assert song_id is not None

    def test_known_alias(self, conn):
        song_id, name, match = normalize_song(conn, "playin' in the band")
        assert name == "Playing in the Band"

    def test_case_insensitive(self, conn):
        song_id, name, _ = normalize_song(conn, "dark star")
        assert name == "Dark Star"

    def test_alias_persists_in_db(self, conn):
        """Second lookup should hit the DB alias table."""
        song_id1, name1, match1 = normalize_song(conn, "Iko Iko")
        song_id2, name2, match2 = normalize_song(conn, "iko iko")
        assert song_id1 == song_id2
        assert name1 == "Aiko-Aiko"
        assert match2 == "alias"  # found via DB alias table on second call

    def test_fuzzy_match(self, conn):
        song_id, name, match = normalize_song(conn, "Sugare")  # close to "Sugaree"
        assert name == "Sugaree"
        assert match == "fuzzy"

    def test_new_song_creation(self, conn):
        song_id, name, match = normalize_song(conn, "A Song That Does Not Exist")
        assert match == "new"
        assert name == "A Song That Does Not Exist"
        assert song_id is not None

    def test_empty_title(self, conn):
        song_id, name, match = normalize_song(conn, "")
        assert song_id is None
        assert name is None

    def test_garbage_name_rejected(self, conn):
        song_id, name, match = normalize_song(conn, "-")
        assert song_id is None
        assert name is None

    def test_punctuation_only_rejected(self, conn):
        song_id, name, match = normalize_song(conn, "?")
        assert song_id is None
        assert name is None

    def test_cleaning_before_lookup(self, conn):
        """Titles with track numbers etc. should still resolve."""
        song_id, name, _ = normalize_song(conn, '01. "Dark Star" > ')
        assert name == "Dark Star"
