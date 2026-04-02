"""Tests for transaction safety in scraper DB writes."""
import pytest
from unittest.mock import patch
from gdtimings import db
from gdtimings.archive_org import _process_from_cache


class TestArchiveTransactionSafety:

    @pytest.fixture
    def conn(self):
        c = db.get_connection(db_path=":memory:")
        yield c
        c.close()

    def test_failed_track_insert_rolls_back_release(self, conn):
        """If track insertion fails mid-way, the release should not persist."""
        data = {
            "metadata": {"title": "gd1977-05-08.test", "date": "1977-05-08"},
            "files": [
                {"source": "original", "format": "Flac", "length": "300",
                 "title": "Good Track", "track": "1"},
                {"source": "original", "format": "Flac", "length": "400",
                 "title": "Bad Track", "track": "2"},
            ],
        }
        call_count = 0
        original_normalize = __import__('gdtimings.normalize', fromlist=['normalize_song']).normalize_song

        def failing_normalize(conn, title):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("Simulated failure")
            return original_normalize(conn, title)

        with patch("gdtimings.archive_org.normalize_song", side_effect=failing_normalize):
            with pytest.raises(RuntimeError):
                _process_from_cache(conn, "gd1977-05-08.test", data)

        assert db.release_exists(conn, "archive:gd1977-05-08.test") is None

    def test_successful_scrape_commits(self, conn):
        """Successful scrape should persist both release and tracks."""
        data = {
            "metadata": {"title": "gd1977-05-08.test", "date": "1977-05-08"},
            "files": [
                {"source": "original", "format": "Flac", "length": "300",
                 "title": "Dark Star", "track": "1"},
            ],
        }
        release_id, track_count = _process_from_cache(conn, "gd1977-05-08.test", data)
        assert release_id is not None
        assert track_count == 1
        assert db.release_exists(conn, "archive:gd1977-05-08.test") is not None
