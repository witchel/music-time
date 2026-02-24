"""Shared JSON caching helpers (two-level directory, atomic writes)."""

import json
import os
import tempfile
import time
from pathlib import Path


def cache_path(cache_dir, identifier):
    """Two-level cache path: cache_dir/prefix/identifier.json"""
    # Use first 4 chars of identifier as prefix subdirectory
    prefix = identifier[:4] if len(identifier) >= 4 else identifier
    return Path(cache_dir) / prefix / f"{identifier}.json"


def read_cache(cache_dir, identifier, max_age_seconds=0):
    """Read cached JSON for an identifier. Returns dict or None."""
    path = cache_path(cache_dir, identifier)
    if not path.exists():
        return None
    if max_age_seconds > 0:
        age = time.time() - path.stat().st_mtime
        if age > max_age_seconds:
            return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def write_cache(cache_dir, identifier, data):
    """Atomically write JSON to cache."""
    path = cache_path(cache_dir, identifier)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Atomic write: write to temp file then rename
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
