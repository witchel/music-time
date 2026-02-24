"""Tests for archive.org caching helpers."""

import json
import os
import time

import pytest

from gdtimings.archive_org import _extract_tracks, _process_from_cache
from gdtimings.cache import (
    cache_path as _cache_path,
    read_cache as _read_cache,
    write_cache as _write_cache,
)


class TestCachePath:
    """Tests for _cache_path() two-level directory structure."""

    def test_standard_identifier(self, tmp_path):
        path = _cache_path(str(tmp_path), "gd1977-05-08.sbd.miller.shnf")
        assert path.parent.name == "gd19"
        assert path.name == "gd1977-05-08.sbd.miller.shnf.json"

    def test_short_identifier(self, tmp_path):
        path = _cache_path(str(tmp_path), "ab")
        assert path.parent.name == "ab"
        assert path.name == "ab.json"


class TestReadWriteCache:
    """Tests for _read_cache() and _write_cache() roundtrip."""

    def test_roundtrip(self, tmp_path):
        data = {"metadata": {"title": "Test"}, "files": []}
        _write_cache(str(tmp_path), "test-id", data)
        result = _read_cache(str(tmp_path), "test-id")
        assert result == data

    def test_missing_returns_none(self, tmp_path):
        result = _read_cache(str(tmp_path), "nonexistent")
        assert result is None

    def test_corrupt_json_returns_none(self, tmp_path):
        path = _cache_path(str(tmp_path), "corrupt")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("not valid json {{{")
        result = _read_cache(str(tmp_path), "corrupt")
        assert result is None

    def test_max_age_fresh(self, tmp_path):
        data = {"metadata": {"title": "Fresh"}}
        _write_cache(str(tmp_path), "fresh-id", data)
        result = _read_cache(str(tmp_path), "fresh-id", max_age_seconds=3600)
        assert result == data

    def test_max_age_stale(self, tmp_path):
        data = {"metadata": {"title": "Stale"}}
        _write_cache(str(tmp_path), "stale-id", data)
        # Backdate the file modification time
        path = _cache_path(str(tmp_path), "stale-id")
        old_time = time.time() - 7200  # 2 hours ago
        os.utime(path, (old_time, old_time))
        result = _read_cache(str(tmp_path), "stale-id", max_age_seconds=3600)
        assert result is None


class TestProcessFromCache:
    """Tests for _process_from_cache()."""

    def test_valid_metadata_creates_release(self, conn):
        data = {
            "metadata": {
                "title": "Test Recording",
                "date": "1977-05-08",
                "venue": "Barton Hall",
                "coverage": "Ithaca, NY",
            },
            "files": [
                {
                    "source": "original",
                    "format": "Flac",
                    "length": "300",
                    "title": "Dark Star",
                    "track": "1",
                    "name": "gd77-05-08d1t01.flac",
                },
                {
                    "source": "original",
                    "format": "Flac",
                    "length": "240",
                    "title": "Estimated Prophet",
                    "track": "2",
                    "name": "gd77-05-08d1t02.flac",
                },
            ],
        }
        release_id, track_count = _process_from_cache(
            conn, "gd1977-05-08.sbd.test", data
        )
        assert release_id is not None
        assert track_count == 2

    def test_duplicate_returns_zero_tracks(self, conn):
        data = {
            "metadata": {
                "title": "Test Recording",
                "date": "1977-05-09",
            },
            "files": [
                {
                    "source": "original",
                    "format": "Flac",
                    "length": "300",
                    "title": "Sugaree",
                    "track": "1",
                    "name": "t01.flac",
                },
            ],
        }
        release_id1, count1 = _process_from_cache(
            conn, "gd1977-05-09.sbd.test", data
        )
        assert count1 == 1
        release_id2, count2 = _process_from_cache(
            conn, "gd1977-05-09.sbd.test", data
        )
        assert release_id2 == release_id1
        assert count2 == 0
