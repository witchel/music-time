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
        assert clean_title("14 – Eyes of the World") == "Eyes of the World"

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

    def test_bare_disc_track_code_dropped(self):
        """Bare D1T12 codes with no song name are dropped."""
        assert clean_title("D1T12") == ""
        assert clean_title("D2T05") == ""

    def test_spelled_out_disc_track(self):
        """Spelled-out disc/track prefixes."""
        assert clean_title('Disc five, track seven: "Jam into Days Between') == "Jam into Days Between"
        assert clean_title('Disc two, track two: "Beautiful Jam') == "Beautiful Jam"

    def test_strip_duration_suffix(self):
        assert clean_title("Dark Star – 14:35") == "Dark Star"
        assert clean_title("Truckin' - 5:32") == "Truckin'"
        assert clean_title("Drums — 1:05:32") == "Drums"

    def test_strip_segue_markers(self):
        assert clean_title("Dark Star >") == "Dark Star"
        assert clean_title("Dark Star →") == "Dark Star"
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
        assert clean_title('01. "Dark Star" (Garcia) – 14:35 >') == "Dark Star"

    # ── New patterns: reel markers ──

    def test_strip_reel_markers(self):
        """Leading // reel markers stripped."""
        assert clean_title("//St. Stephen") == "St. Stephen"
        assert clean_title("// Gimme Some Lovin'") == "Gimme Some Lovin'"
        assert clean_title("//CC Rider") == "CC Rider"
        assert clean_title("//Caution") == "Caution"

    # ── New patterns: encore prefix ──

    def test_strip_encore_prefix(self):
        """e: and Encore: prefixes stripped."""
        assert clean_title("e: Keep Your Day Job") == "Keep Your Day Job"
        assert clean_title("Encore: U.S. Blues") == "U.S. Blues"
        assert clean_title("** E: U. S. Blues") == "U. S. Blues"

    # ── New patterns: timestamp prefix ──

    def test_strip_timestamp_prefix(self):
        """Leading timestamp ##:##] stripped."""
        assert clean_title("01:16] Polka Tuning") == ""  # "Polka Tuning" is a non-song
        assert clean_title("03:39] Pre Dark Star Tuning") == ""  # also non-song
        # Timestamp prefix with real song
        assert clean_title("10:16.41| Wharf Rat") == "Wharf Rat"
        assert clean_title("1:03] Deal") == "Deal"

    # ── New patterns: bare track number ──

    def test_strip_bare_track_number(self):
        """Bare track number 'NN Song' stripped."""
        assert clean_title("01 Hell In A Bucket") == "Hell In A Bucket"
        assert clean_title("14 Drumz") == "Drumz"
        assert clean_title("01 Gimme Some Lovin'") == "Gimme Some Lovin'"
        assert clean_title("01 Rain") == "Rain"

    def test_bare_track_number_preserves_numbered_songs(self):
        """Songs with numbers in the title should not be mangled."""
        # "29 Rainy Day Women #12 And #35" — the "29" is a track number
        # but the song name itself starts with "Rainy"
        result = clean_title("29 Rainy Day Women #12 And #35")
        assert "Rainy Day Women" in result

    # ── New patterns: Disc###-Song ──

    def test_strip_disc_dash_format(self):
        """Disc103-CC Rider format stripped."""
        assert clean_title("Disc103-CC Rider") == "CC Rider"
        assert clean_title("Disc301-Iko Iko") == "Iko Iko"
        assert clean_title("Disc110-Hell In A Bucket") == "Hell In A Bucket"

    # ── New patterns: t01.Song ──

    def test_strip_t_dot_format(self):
        """t01.Song format stripped."""
        assert clean_title("t01.Set Up") == ""  # "Set Up" is a non-song
        assert clean_title("t03.CC Rider") == "CC Rider"
        assert clean_title("t07.C C Rider") == "C C Rider"

    # ── New patterns: trailing symbols ──

    def test_strip_trailing_asterisks(self):
        """Trailing asterisks stripped."""
        assert clean_title("Wang Dang Doodle *") == "Wang Dang Doodle"
        assert clean_title("All Along The Watchtower*") == "All Along The Watchtower"
        assert clean_title("Ain't Superstitious*") == "Ain't Superstitious"

    def test_strip_trailing_segue_plus_asterisk(self):
        """Trailing ->* and >* combinations stripped."""
        assert clean_title("All Along The Watchtower ->*") == "All Along The Watchtower"
        assert clean_title("All Along The Watchtower >*") == "All Along The Watchtower"

    def test_strip_trailing_tildes(self):
        """Trailing tildes stripped."""
        assert clean_title("encore break~~") == ""  # non-song

    def test_strip_trailing_hash(self):
        """Trailing # stripped."""
        assert clean_title("/Sing Me Back Home*#") == "Sing Me Back Home"

    # ── New patterns: tape flip annotations ──

    def test_strip_tape_flip_annotation(self):
        """(Tape Flip After Song) and similar annotations stripped."""
        assert clean_title("Mexicali Blues (Tape Flip After Song)") == "Mexicali Blues"
        assert clean_title("Althea (Tape Flip After Song)") == "Althea"
        assert clean_title("Althea (tape flip)") == "Althea"
        assert clean_title("Big River (Tape Flip Directly After Song)") == "Big River"
        assert clean_title("BirdSong (Tape Flip Inside)") == "BirdSong"

    # ── New patterns: recording metadata ──

    def test_strip_recording_metadata(self):
        """(AUD), (2 AUD Matrix), (audience recording) stripped."""
        assert clean_title("(I Can't get No) Satisfaction **(2 AUD Matrix)") == "(I Can't get No) Satisfaction"
        assert clean_title("Bertha (Aud patch)") == "Bertha"
        assert clean_title("(X)Casey Jones(audience recording)") == "Casey Jones"

    # ── New patterns: duration in brackets ──

    def test_strip_duration_brackets(self):
        """[6:05] duration annotations stripped."""
        assert clean_title("Bertha [4:52] ;") == "Bertha"
        assert clean_title("Bertha [6:10]") == "Bertha"
        assert clean_title("Bertha [7:03]") == "Bertha"

    # ── New patterns: trailing Set Break ──

    def test_strip_trailing_set_break(self):
        """', Set Break' suffix stripped."""
        assert clean_title("Deal, Set Break") == "Deal"
        assert clean_title("Bird Song, Set Break") == "Bird Song"
        assert clean_title("Bertha, Set Break") == "Bertha"

    # ── New patterns: reel metadata ──

    def test_strip_reel_metadata(self):
        """Parenthetical reel metadata stripped."""
        assert clean_title("Turn On Your Lovelight (reel #2 side B; 8-track 15 ips)") == "Turn On Your Lovelight"

    # ── Non-song classification ──

    def test_non_song_tuning(self):
        """Tuning variants classified as non-song."""
        assert clean_title("Tuning") == ""
        assert clean_title("tuning") == ""
        assert clean_title("01 Tuning") == ""  # after track number stripped

    def test_non_song_crowd(self):
        assert clean_title("crowd") == ""
        assert clean_title("Crowd") == ""
        assert clean_title("01 crowd") == ""

    def test_non_song_encore_break(self):
        assert clean_title("encore break") == ""
        assert clean_title("- encore break -") == ""

    def test_non_song_banter(self):
        assert clean_title("banter") == ""
        assert clean_title("Stage Banter") == ""
        assert clean_title("02 Stage Banter") == ""

    def test_non_song_dead_air(self):
        assert clean_title("dead air") == ""
        assert clean_title("--dead air--") == ""

    def test_non_song_compound(self):
        """Compound non-songs like 'crowd/tuning' are classified."""
        assert clean_title("crowd/tuning") == ""
        assert clean_title("Crowd & Tuning") == ""
        assert clean_title("Encore Break/Crowd/Tuning") == ""
        assert clean_title("crowd and tuning") == ""

    def test_non_song_intro(self):
        assert clean_title("Introduction") == ""
        assert clean_title("intro") == ""
        assert clean_title("01 Introduction") == ""

    def test_non_song_applause(self):
        assert clean_title("applause") == ""

    def test_non_song_set_break(self):
        assert clean_title("set break") == ""
        assert clean_title("Set Break") == ""

    def test_non_song_tape_flip(self):
        assert clean_title("tape flip") == ""
        assert clean_title("tape break") == ""

    def test_non_song_setup(self):
        assert clean_title("Set Up") == ""
        assert clean_title("setup") == ""

    def test_non_song_announcements(self):
        assert clean_title("Announcements") == ""
        assert clean_title("announcement") == ""

    def test_non_song_preserves_real_songs(self):
        """Real songs that contain non-song words are preserved."""
        assert clean_title("Dark Star") == "Dark Star"
        assert clean_title("Drums") == "Drums"
        assert clean_title("Space") == "Space"
        assert clean_title("Feedback") == "Feedback"
        assert clean_title("Take a Step Back") == "Take a Step Back"

    def test_non_song_timestamp_tuning(self):
        """Timestamp-prefixed non-songs cleaned and classified."""
        assert clean_title("00:11] tuning/dead air") == ""
        assert clean_title("01:16] crowd and tuning") == ""

    def test_disc_comma_track_tuning(self):
        """Disc,Track-prefixed tuning classified as non-song."""
        assert clean_title("Disc01,Track01 Tuning") == ""


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

    # ── New canonical songs ──

    def test_hell_in_a_bucket(self, conn):
        song_id, name, _ = normalize_song(conn, "Hell in a Bucket")
        assert name == "Hell in a Bucket"

    def test_cc_rider_aliases(self, conn):
        """All C.C. Rider variants resolve to one song."""
        id1, name1, _ = normalize_song(conn, "C.C. Rider")
        id2, name2, _ = normalize_song(conn, "CC Rider")
        id3, name3, _ = normalize_song(conn, "C C Rider")
        assert name1 == "C.C. Rider"
        assert name2 == "C.C. Rider"
        assert name3 == "C.C. Rider"
        assert id1 == id2 == id3

    def test_saint_stephen_aliases(self, conn):
        """All St. Stephen variants resolve to one song."""
        id1, name1, _ = normalize_song(conn, "Saint Stephen")
        id2, name2, _ = normalize_song(conn, "St. Stephen")
        id3, name3, _ = normalize_song(conn, "St Stephen")
        assert name1 == "Saint Stephen"
        assert name2 == "Saint Stephen"
        assert name3 == "Saint Stephen"
        assert id1 == id2 == id3

    def test_satisfaction_aliases(self, conn):
        """Satisfaction variants resolve."""
        _, name, _ = normalize_song(conn, "Satisfaction")
        assert name == "(I Can't Get No) Satisfaction"

    def test_mighty_quinn_aliases(self, conn):
        """Quinn/Mighty Quinn aliases resolve."""
        id1, name1, _ = normalize_song(conn, "The Mighty Quinn")
        id2, name2, _ = normalize_song(conn, "Quinn the Eskimo")
        assert name1 == "Quinn the Eskimo"
        assert id1 == id2

    def test_lovelight_alias(self, conn):
        _, name, _ = normalize_song(conn, "Lovelight")
        assert name == "Turn On Your Lovelight"

    def test_masterpiece_alias(self, conn):
        _, name, _ = normalize_song(conn, "Masterpiece")
        assert name == "When I Paint My Masterpiece"

    def test_pitb_alias(self, conn):
        _, name, _ = normalize_song(conn, "PITB")
        assert name == "Playing in the Band"

    def test_nfa_alias(self, conn):
        _, name, _ = normalize_song(conn, "NFA")
        assert name == "Not Fade Away"

    def test_biodtl_alias(self, conn):
        _, name, _ = normalize_song(conn, "BIODTL")
        assert name == "Beat It On Down the Line"

    def test_day_job_alias(self, conn):
        _, name, _ = normalize_song(conn, "Day Job")
        assert name == "Keep Your Day Job"

    def test_mississippi_half_step_alias(self, conn):
        _, name, _ = normalize_song(conn, "Mississippi Half Step")
        assert name == "Half-Step Mississippi Uptown Toodleloo"

    def test_drumz_alias(self, conn):
        _, name, _ = normalize_song(conn, "drumz")
        assert name == "Drums"

    def test_wang_dang_doodle(self, conn):
        _, name, _ = normalize_song(conn, "Wang Dang Doodle")
        assert name == "Wang Dang Doodle"

    def test_caution_alias(self, conn):
        _, name, _ = normalize_song(conn, "Caution")
        assert name == "Caution (Do Not Stop on Tracks)"

    def test_row_jimmy_row_alias(self, conn):
        _, name, _ = normalize_song(conn, "Row Jimmy Row")
        assert name == "Row Jimmy"

    def test_non_song_returns_none(self, conn):
        """Non-song tracks return None."""
        song_id, name, match = normalize_song(conn, "tuning")
        assert song_id is None
        assert name is None

    def test_non_song_compound_returns_none(self, conn):
        """Compound non-song tracks return None."""
        song_id, name, match = normalize_song(conn, "crowd/tuning")
        assert song_id is None

    def test_non_song_with_track_number(self, conn):
        """Track-number-prefixed non-songs return None."""
        song_id, name, match = normalize_song(conn, "01 crowd")
        assert song_id is None

    def test_reel_marker_resolves(self, conn):
        """Reel-marker-prefixed titles resolve to the real song."""
        _, name, _ = normalize_song(conn, "//St. Stephen")
        assert name == "Saint Stephen"

    def test_encore_prefix_resolves(self, conn):
        """Encore-prefixed titles resolve."""
        _, name, _ = normalize_song(conn, "e: Keep Your Day Job")
        assert name == "Keep Your Day Job"

    def test_disc_dash_format_resolves(self, conn):
        """Disc103-CC Rider resolves to C.C. Rider."""
        _, name, _ = normalize_song(conn, "Disc103-CC Rider")
        assert name == "C.C. Rider"

    def test_bare_track_number_resolves(self, conn):
        """'01 Hell In A Bucket' resolves correctly."""
        _, name, _ = normalize_song(conn, "01 Hell In A Bucket")
        assert name == "Hell in a Bucket"
