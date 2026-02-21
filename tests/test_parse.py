"""Tests for archive.org identifier parsing and track extraction."""

import pytest

from gdtimings.archive_org import (
    parse_date_from_identifier,
    parse_recording_type,
    _extract_tracks,
    _is_audio_format,
)


class TestParseDateFromIdentifier:
    """Tests for the 3 date format variants."""

    def test_four_digit_year_with_dashes(self):
        assert parse_date_from_identifier("gd1977-05-08.sbd.miller.shnf") == "1977-05-08"

    def test_two_digit_year_with_dashes(self):
        assert parse_date_from_identifier("gd77-05-08.aud.shnf") == "1977-05-08"

    def test_two_digit_year_2000s(self):
        # 2-digit years < 60 → 2000s (unlikely for GD but tests the logic)
        assert parse_date_from_identifier("gd03-07-04.aud.shnf") == "2003-07-04"

    def test_compact_format(self):
        assert parse_date_from_identifier("gd19770508.sbd.shnf") == "1977-05-08"

    def test_no_date(self):
        assert parse_date_from_identifier("grateful_dead_misc") is None

    def test_extra_prefix(self):
        """Identifier with extra text before the gd prefix."""
        assert parse_date_from_identifier("gd1969-11-08.aud.unknown.12345") == "1969-11-08"

    def test_boundary_year_60(self):
        assert parse_date_from_identifier("gd60-01-15.aud") == "1960-01-15"

    def test_boundary_year_59(self):
        assert parse_date_from_identifier("gd59-12-31.aud") == "2059-12-31"


class TestParseRecordingType:
    """Tests for SBD/AUD/MTX detection from identifiers and metadata."""

    def test_sbd_in_identifier(self):
        assert parse_recording_type("gd1977-05-08.sbd.miller.shnf") == "SBD"

    def test_aud_in_identifier(self):
        assert parse_recording_type("gd1969-11-08.aud.unknown.shnf") == "AUD"

    def test_mtx_in_identifier(self):
        assert parse_recording_type("gd1990-03-29.mtx.seamons.shnf") == "MTX"

    def test_matrix_in_identifier(self):
        assert parse_recording_type("gd1990-03-29.matrix.seamons.shnf") == "MTX"

    def test_fallback_to_metadata_sbd(self):
        assert parse_recording_type(
            "gd1977-05-08.shnf",
            metadata={"source": "Soundboard > Master Reel"}
        ) == "SBD"

    def test_fallback_to_metadata_aud(self):
        assert parse_recording_type(
            "gd1977-05-08.shnf",
            metadata={"source": "Audience recording"}
        ) == "AUD"

    def test_default_aud(self):
        assert parse_recording_type("gd1977-05-08.shnf") == "AUD"

    def test_type_only_in_first_four_segments(self):
        """Type detection checks first 4 dot-segments."""
        assert parse_recording_type("gd1977-05-08.a.b.c.sbd") == "AUD"  # sbd is 5th


class TestIsAudioFormat:

    def test_flac(self):
        assert _is_audio_format("Flac") is True

    def test_mp3(self):
        assert _is_audio_format("VBR MP3") is True

    def test_shorten(self):
        assert _is_audio_format("Shorten") is True

    def test_non_audio(self):
        assert _is_audio_format("Text") is False
        assert _is_audio_format("JPEG") is False
        assert _is_audio_format("Metadata") is False


class TestExtractTracks:
    """Tests for the file filtering/dedup/sort pipeline."""

    def _file(self, *, title="Dark Star", length="600", track=None,
              fmt="Flac", source="original", name="gd77d1t01.flac"):
        f = {"title": title, "length": length, "format": fmt,
             "source": source, "name": name}
        if track is not None:
            f["track"] = str(track)
        return f

    def test_basic_extraction(self):
        files = [self._file(title="Dark Star", length="600", track=1)]
        tracks = _extract_tracks(files)
        assert len(tracks) == 1
        assert tracks[0]["title_raw"] == "Dark Star"
        assert tracks[0]["duration"] == 600.0
        assert tracks[0]["track"] == 1

    def test_filters_derivatives(self):
        files = [self._file(source="derivative")]
        assert _extract_tracks(files) == []

    def test_filters_non_audio(self):
        files = [self._file(fmt="Text")]
        assert _extract_tracks(files) == []

    def test_filters_no_length(self):
        files = [self._file(length=None)]
        assert _extract_tracks(files) == []

    def test_filters_zero_duration(self):
        files = [self._file(length="0")]
        assert _extract_tracks(files) == []

    def test_dedup_by_track_number(self):
        """Same track in multiple formats should only appear once."""
        files = [
            self._file(title="Dark Star", length="600", track=1,
                       fmt="Flac", name="gd77d1t01.flac"),
            self._file(title="Dark Star", length="600", track=1,
                       fmt="VBR MP3", name="gd77d1t01.mp3"),
        ]
        tracks = _extract_tracks(files)
        assert len(tracks) == 1

    def test_sorted_by_track_number(self):
        files = [
            self._file(title="Song B", track=2, length="300", name="t02.flac"),
            self._file(title="Song A", track=1, length="600", name="t01.flac"),
        ]
        tracks = _extract_tracks(files)
        assert tracks[0]["title_raw"] == "Song A"
        assert tracks[1]["title_raw"] == "Song B"

    def test_fallback_to_filename(self):
        """If no title, use filename without extension."""
        files = [self._file(title="", name="gd77-dark_star.flac",
                            length="600", track=1)]
        tracks = _extract_tracks(files)
        assert tracks[0]["title_raw"] == "gd77-dark_star"

    def test_assigns_missing_track_numbers(self):
        files = [
            self._file(title="Song A", length="300", name="a.flac"),
            self._file(title="Song B", length="400", name="b.flac"),
        ]
        tracks = _extract_tracks(files)
        assert tracks[0]["track"] == 1
        assert tracks[1]["track"] == 2

    def test_track_number_slash_format(self):
        """Archive.org sometimes uses '3/12' format for track numbers."""
        files = [self._file(track="3/12", length="300")]
        tracks = _extract_tracks(files)
        assert tracks[0]["track"] == 3
