"""Shared HTTP utilities for scrapers."""

import time

import requests


def create_session(user_agent):
    """Create a requests.Session with a User-Agent header."""
    s = requests.Session()
    s.headers["User-Agent"] = user_agent
    return s


def api_get_with_retry(session, url, params=None, rate_limit=0.5, max_retries=3):
    """Make an API request with rate limiting and retry on 429/5xx.

    Args:
        session: requests.Session to use
        url: Request URL
        params: Optional query parameters
        rate_limit: Seconds to wait between successful requests
        max_retries: Number of retry attempts before a final raise
    """
    for attempt in range(max_retries):
        resp = session.get(url, params=params)
        if resp.status_code == 429 or resp.status_code >= 500:
            retry_after = int(resp.headers.get("Retry-After", 2 ** attempt))
            print(f"    HTTP {resp.status_code}, retrying in {retry_after}s "
                  f"(attempt {attempt + 1}/{max_retries})")
            time.sleep(retry_after)
            continue
        resp.raise_for_status()
        time.sleep(rate_limit)
        return resp.json()
    # Final attempt — let it raise
    resp = session.get(url, params=params)
    resp.raise_for_status()
    time.sleep(rate_limit)
    return resp.json()


def progress_line(done, total, elapsed):
    """Format a progress string like ``[done/total pct% elapsed_s eta eta_s]``."""
    pct = done * 100 // total if total else 0
    rate = done / elapsed if elapsed > 0 else 0
    eta = (total - done) / rate if rate > 0 else 0
    return f"[{done}/{total} {pct:>3}% {elapsed:.0f}s eta {eta:.0f}s]"
