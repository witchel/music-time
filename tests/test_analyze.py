"""Tests for per-show duration aggregation and outlier detection."""

import statistics

import pytest

from gdtimings import db
from gdtimings.analyze import classify_song_types, compute_song_stats, _per_show_durations
from tests.conftest import make_release, make_track


class TestPerShowDurations:
    """Tests for the SQL-based per-show aggregation."""

    def test_single_track_per_show(self, conn):
        """Basic case: one track per release per date."""
        song_id = db.get_or_create_song(conn, "Dark Star")
        rid = make_release(conn, source_id="r1", concert_date="1977-05-08")
        make_track(conn, release_id=rid, song_id=song_id, duration=1200, track_num=1)
        conn.commit()

        data = _per_show_durations(conn)
        assert song_id in data
        assert len(data[song_id]) == 1
        assert data[song_id][0] == ("1977-05-08", 1200)

    def test_split_song_uses_max(self, conn):
        """Split song (e.g. Dark Star V1 + V2) should take MAX per release."""
        song_id = db.get_or_create_song(conn, "Dark Star")
        rid = make_release(conn, source_id="r1", concert_date="1977-05-08")
        make_track(conn, release_id=rid, song_id=song_id, duration=600, track_num=1)
        make_track(conn, release_id=rid, song_id=song_id, duration=1400, track_num=5)
        conn.commit()

        data = _per_show_durations(conn)
        # Should take the MAX (1400), not sum or average
        assert len(data[song_id]) == 1
        assert data[song_id][0][1] == 1400

    def test_multiple_tapers_picks_best(self, conn):
        """Multiple releases of the same date should pick highest quality_rank."""
        song_id = db.get_or_create_song(conn, "Dark Star")
        # AUD taper (quality 100) — shorter duration due to tape issues
        rid1 = make_release(conn, source_id="r1", concert_date="1977-05-08",
                            quality_rank=100)
        make_track(conn, release_id=rid1, song_id=song_id, duration=1100, track_num=1)
        # SBD taper (quality 300) — better, longer recording
        rid2 = make_release(conn, source_id="r2", concert_date="1977-05-08",
                            quality_rank=300)
        make_track(conn, release_id=rid2, song_id=song_id, duration=1200, track_num=1)
        conn.commit()

        data = _per_show_durations(conn)
        assert len(data[song_id]) == 1
        # Should pick SBD (quality_rank=300) release's duration
        assert data[song_id][0][1] == 1200

    def test_different_dates_separate(self, conn):
        """Different concert dates produce separate entries."""
        song_id = db.get_or_create_song(conn, "Dark Star")
        rid1 = make_release(conn, source_id="r1", concert_date="1977-05-08")
        make_track(conn, release_id=rid1, song_id=song_id, duration=1200, track_num=1)
        rid2 = make_release(conn, source_id="r2", concert_date="1978-01-22")
        make_track(conn, release_id=rid2, song_id=song_id, duration=900, track_num=1)
        conn.commit()

        data = _per_show_durations(conn)
        assert len(data[song_id]) == 2

    def test_null_song_id_excluded(self, conn):
        """Tracks with song_id=NULL should not appear."""
        rid = make_release(conn, source_id="r1", concert_date="1977-05-08")
        make_track(conn, release_id=rid, song_id=None, duration=1200, track_num=1)
        conn.commit()

        data = _per_show_durations(conn)
        assert len(data) == 0


class TestComputeSongStats:
    """Tests for the full stats computation pipeline."""

    def _setup_song(self, conn, name, date_durations, quality_rank=100):
        """Helper: create a song with tracks across multiple dates.

        date_durations: list of (date_str, [dur1, dur2, ...]) tuples.
        Multiple durations per date simulate split songs.
        """
        song_id = db.get_or_create_song(conn, name)
        for i, (date, durs) in enumerate(date_durations):
            rid = make_release(conn, source_id=f"{name}-r{i}",
                               concert_date=date, quality_rank=quality_rank)
            for j, dur in enumerate(durs):
                make_track(conn, release_id=rid, song_id=song_id,
                           duration=dur, track_num=j + 1)
        conn.commit()
        return song_id

    def test_basic_stats(self, conn):
        """Stats should be computed from per-show MAX durations."""
        song_id = self._setup_song(conn, "Dark Star", [
            ("1977-05-08", [1200]),
            ("1977-05-09", [900]),
            ("1977-05-10", [1500]),
        ])
        compute_song_stats(conn, verbose=False)

        row = conn.execute(
            "SELECT * FROM songs WHERE id = ?", (song_id,)
        ).fetchone()
        assert row["times_played"] == 3
        assert row["first_played"] == "1977-05-08"
        assert row["last_played"] == "1977-05-10"
        expected_mean = statistics.mean([1200, 900, 1500])
        assert abs(row["mean_duration"] - expected_mean) < 0.01

    def test_split_song_stats(self, conn):
        """Split songs: stats use MAX(duration) per show, not raw tracks."""
        song_id = self._setup_song(conn, "Dark Star", [
            # Show 1: split into V1 (600s) + V2 (1400s) → MAX = 1400
            ("1977-05-08", [600, 1400]),
            # Show 2: single track
            ("1977-05-09", [900]),
            # Show 3: split into V1 (800s) + V2 (1200s) → MAX = 1200
            ("1977-05-10", [800, 1200]),
        ])
        compute_song_stats(conn, verbose=False)

        row = conn.execute(
            "SELECT * FROM songs WHERE id = ?", (song_id,)
        ).fetchone()
        # Should count 3 shows, not 5 tracks
        assert row["times_played"] == 3
        # Stats on [1400, 900, 1200], not [600, 1400, 900, 800, 1200]
        expected = [1400, 900, 1200]
        assert abs(row["mean_duration"] - statistics.mean(expected)) < 0.01
        assert abs(row["median_duration"] - statistics.median(expected)) < 0.01

    def test_taper_dedup_stats(self, conn):
        """Multiple tapers of same show should not inflate times_played."""
        song_id = db.get_or_create_song(conn, "Dark Star")
        # Same date, two tapers
        rid1 = make_release(conn, source_id="aud", concert_date="1977-05-08",
                            quality_rank=100)
        make_track(conn, release_id=rid1, song_id=song_id, duration=1100, track_num=1)
        rid2 = make_release(conn, source_id="sbd", concert_date="1977-05-08",
                            quality_rank=300)
        make_track(conn, release_id=rid2, song_id=song_id, duration=1200, track_num=1)
        conn.commit()

        compute_song_stats(conn, verbose=False)
        row = conn.execute(
            "SELECT * FROM songs WHERE id = ?", (song_id,)
        ).fetchone()
        assert row["times_played"] == 1
        # Should use SBD recording (higher quality_rank)
        assert abs(row["mean_duration"] - 1200) < 0.01

    def test_outlier_detection(self, conn):
        """Extreme durations should be flagged as outliers."""
        # Many normal shows to anchor the stats, + 1 extreme outlier.
        # With enough normal data, the std is small and 3000 is clearly > 3 sigma.
        normal_dates = [(f"1977-05-{d:02d}", [600]) for d in range(1, 21)]
        song_id = self._setup_song(conn, "Test Song", [
            *normal_dates,
            ("1977-06-01", [3000]),  # way outside 3 sigma
        ])
        _, outliers_found = compute_song_stats(conn, verbose=False)

        assert outliers_found > 0
        # The track from the extreme show should be marked
        outlier_tracks = conn.execute(
            """SELECT t.id, r.concert_date FROM tracks t
               JOIN releases r ON t.release_id = r.id
               WHERE t.song_id = ? AND t.is_outlier = 1""",
            (song_id,),
        ).fetchall()
        assert any(t["concert_date"] == "1977-06-01" for t in outlier_tracks)

    def test_no_data_is_safe(self, conn):
        """Songs with no tracks shouldn't cause errors."""
        db.get_or_create_song(conn, "Empty Song")
        conn.commit()
        updated, outliers = compute_song_stats(conn, verbose=False)
        # Empty song has no data — shouldn't be updated
        assert updated == 0

    def test_single_show_no_std(self, conn):
        """A song with one show should have std_duration = 0."""
        song_id = self._setup_song(conn, "Rare Song", [
            ("1977-05-08", [600]),
        ])
        compute_song_stats(conn, verbose=False)

        row = conn.execute(
            "SELECT * FROM songs WHERE id = ?", (song_id,)
        ).fetchone()
        assert row["times_played"] == 1
        assert row["std_duration"] == 0.0


class TestClassifySongTypes:
    """Tests for song type classification and view filtering."""

    def test_classify_marks_utility(self, conn):
        """Drums and Space should be classified as utility."""
        db.get_or_create_song(conn, "Drums")
        db.get_or_create_song(conn, "Space")
        db.get_or_create_song(conn, "Dark Star")
        conn.commit()

        classify_song_types(conn, verbose=False)

        drums = conn.execute(
            "SELECT song_type FROM songs WHERE canonical_name = 'Drums'"
        ).fetchone()
        assert drums["song_type"] == "utility"

        star = conn.execute(
            "SELECT song_type FROM songs WHERE canonical_name = 'Dark Star'"
        ).fetchone()
        assert star["song_type"] == "song"

    def test_best_performances_excludes_utility(self, conn):
        """best_performances view should not include utility songs."""
        drums_id = db.get_or_create_song(conn, "Drums")
        star_id = db.get_or_create_song(conn, "Dark Star")
        conn.commit()
        classify_song_types(conn, verbose=False)

        rid = make_release(conn, source_id="r1", concert_date="1977-05-08")
        make_track(conn, release_id=rid, song_id=drums_id, duration=600, track_num=1)
        make_track(conn, release_id=rid, song_id=star_id, duration=1200, track_num=2)
        conn.commit()

        rows = conn.execute("SELECT song FROM best_performances").fetchall()
        songs = {r["song"] for r in rows}
        assert "Dark Star" in songs
        assert "Drums" not in songs

    def test_best_performances_excludes_edited(self, conn):
        """best_performances view should not include edited releases."""
        song_id = db.get_or_create_song(conn, "Dark Star")
        conn.commit()

        rid = make_release(conn, source_id="r1", concert_date="1977-05-08",
                           coverage="edited")
        make_track(conn, release_id=rid, song_id=song_id, duration=1200, track_num=1)
        conn.commit()

        rows = conn.execute("SELECT song FROM best_performances").fetchall()
        assert len(rows) == 0

    def test_best_performances_excludes_outliers(self, conn):
        """best_performances view should not include outlier tracks."""
        song_id = db.get_or_create_song(conn, "Dark Star")
        conn.commit()

        rid = make_release(conn, source_id="r1", concert_date="1977-05-08")
        # Insert track, then mark it as outlier
        db.insert_track(conn, release_id=rid, title_raw="Dark Star",
                        disc_number=1, track_number=1, song_id=song_id,
                        duration_seconds=9999)
        track = conn.execute(
            "SELECT id FROM tracks WHERE release_id = ? AND track_number = 1",
            (rid,),
        ).fetchone()
        db.mark_outlier(conn, track["id"], 1)
        conn.commit()

        rows = conn.execute("SELECT song FROM best_performances").fetchall()
        assert len(rows) == 0

    def test_best_performances_includes_clean(self, conn):
        """best_performances should include complete, non-utility, non-outlier tracks."""
        song_id = db.get_or_create_song(conn, "Dark Star")
        conn.commit()

        rid = make_release(conn, source_id="r1", concert_date="1977-05-08",
                           coverage="complete")
        make_track(conn, release_id=rid, song_id=song_id, duration=1200, track_num=1)
        conn.commit()

        rows = conn.execute("SELECT * FROM best_performances").fetchall()
        assert len(rows) == 1
        assert rows[0]["song"] == "Dark Star"
        assert abs(rows[0]["dur_min"] - 20.0) < 0.01

    def test_all_performances_retains_everything(self, conn):
        """all_performances should include utility, edited, and outlier rows."""
        drums_id = db.get_or_create_song(conn, "Drums")
        star_id = db.get_or_create_song(conn, "Dark Star")
        conn.commit()
        classify_song_types(conn, verbose=False)

        # Utility song on a complete release
        rid1 = make_release(conn, source_id="r1", concert_date="1977-05-08")
        make_track(conn, release_id=rid1, song_id=drums_id, duration=600, track_num=1)
        # Regular song on an edited release
        rid2 = make_release(conn, source_id="r2", concert_date="1977-05-09",
                            coverage="edited")
        make_track(conn, release_id=rid2, song_id=star_id, duration=1200, track_num=1)
        conn.commit()

        rows = conn.execute("SELECT song FROM all_performances").fetchall()
        songs = {r["song"] for r in rows}
        assert "Drums" in songs
        assert "Dark Star" in songs

    def test_unedited_passes_filter(self, conn):
        """Releases with coverage='unedited' should appear in best_performances."""
        song_id = db.get_or_create_song(conn, "Dark Star")
        conn.commit()

        rid = make_release(conn, source_id="r1", concert_date="1977-05-08",
                           coverage="unedited")
        make_track(conn, release_id=rid, song_id=song_id, duration=1200, track_num=1)
        conn.commit()

        rows = conn.execute("SELECT song FROM best_performances").fetchall()
        assert len(rows) == 1
