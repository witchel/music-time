"""Tests for DB helper functions."""
import pytest
from gdtimings import db
from tests.conftest import make_release


class TestInsertTrackUpsert:

    @pytest.fixture
    def conn(self):
        c = db.get_connection(db_path=":memory:")
        yield c
        c.close()

    def test_upsert_preserves_sandwich_duration(self, conn):
        rid = make_release(conn, source_id="r1", concert_date="1977-05-08")
        db.insert_track(conn, release_id=rid, title_raw="PITB",
                        disc_number=1, track_number=1, song_id=None,
                        duration_seconds=600)
        conn.commit()

        conn.execute(
            "UPDATE tracks SET sandwich_duration = 2100 "
            "WHERE release_id = ? AND track_number = 1", (rid,))
        conn.commit()

        db.insert_track(conn, release_id=rid, title_raw="PITB",
                        disc_number=1, track_number=1, song_id=None,
                        duration_seconds=600)
        conn.commit()

        row = conn.execute(
            "SELECT sandwich_duration FROM tracks "
            "WHERE release_id = ? AND track_number = 1", (rid,)
        ).fetchone()
        assert row["sandwich_duration"] == 2100

    def test_upsert_preserves_row_id(self, conn):
        rid = make_release(conn, source_id="r1", concert_date="1977-05-08")
        db.insert_track(conn, release_id=rid, title_raw="PITB",
                        disc_number=1, track_number=1, song_id=None,
                        duration_seconds=600)
        conn.commit()

        orig_id = conn.execute(
            "SELECT id FROM tracks WHERE release_id = ? AND track_number = 1",
            (rid,),
        ).fetchone()["id"]

        db.insert_track(conn, release_id=rid, title_raw="Playing in the Band",
                        disc_number=1, track_number=1, song_id=None,
                        duration_seconds=650)
        conn.commit()

        row = conn.execute(
            "SELECT id, title_raw, duration_seconds FROM tracks "
            "WHERE release_id = ? AND track_number = 1", (rid,)
        ).fetchone()
        assert row["id"] == orig_id
        assert row["title_raw"] == "Playing in the Band"
        assert row["duration_seconds"] == 650
