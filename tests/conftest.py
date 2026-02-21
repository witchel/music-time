"""Shared fixtures for gdtimings tests."""

import pytest

from gdtimings import db


@pytest.fixture
def conn():
    """Fresh in-memory database with schema applied."""
    c = db.get_connection(db_path=":memory:")
    yield c
    c.close()


def make_release(conn, *, source_id, concert_date=None, quality_rank=100,
                 recording_type="AUD", state=None, coverage="complete"):
    """Insert a minimal release and return its id."""
    return db.insert_release(
        conn,
        source_type="test",
        source_id=source_id,
        concert_date=concert_date,
        quality_rank=quality_rank,
        recording_type=recording_type,
        state=state,
        coverage=coverage,
    )


def make_track(conn, *, release_id, song_id, duration, disc=1, track_num,
               set_name=None):
    """Insert a minimal track."""
    db.insert_track(
        conn,
        release_id=release_id,
        title_raw="test",
        disc_number=disc,
        track_number=track_num,
        song_id=song_id,
        duration_seconds=duration,
        set_name=set_name,
    )
