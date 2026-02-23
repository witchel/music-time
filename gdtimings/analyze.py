"""Outlier detection, sandwich detection, and consensus timing statistics.

Stats are computed per *show* (concert date), not per raw track:
1. MAX(duration) within each release handles split songs (e.g. Dark Star V1/V2)
2. Drums sandwiches (Song → Drums → Space → Song) are summed via detect_sandwiches()
3. Best release per concert date (highest quality_rank) avoids taper inflation
4. Outliers are flagged on the aggregated per-show durations, then propagated
   back to the individual tracks that contributed to outlier shows.
"""

import statistics

from gdtimings import db
from gdtimings.config import OUTLIER_STD_MULTIPLIER, MIN_SAMPLES_FOR_STATS, UTILITY_SONGS


def classify_song_types(conn, verbose=True):
    """Mark utility songs (Drums, Space, Jam) as song_type='utility'."""
    updated = 0
    for name in UTILITY_SONGS:
        cur = conn.execute(
            "UPDATE songs SET song_type = 'utility' WHERE canonical_name = ?",
            (name,),
        )
        updated += cur.rowcount
    conn.commit()
    if verbose:
        print(f"  Classified {updated} utility songs")
    return updated


def detect_sandwiches(conn, verbose=True):
    """Detect Drums/Space sandwich patterns and set sandwich_duration.

    A sandwich occurs when the same song appears before AND after a
    contiguous Drums/Space sequence within a single release:
        Song X → Drums → Space → Song X

    For each sandwich found:
    - The first X segment gets sandwich_duration = sum of all X segments
    - Continuation X segments get sandwich_duration = 0
    """
    # Look up Drums and Space song_ids
    drums_space_ids = set()
    for name in ("Drums", "Space"):
        row = conn.execute(
            "SELECT id FROM songs WHERE canonical_name = ?", (name,)
        ).fetchone()
        if row:
            drums_space_ids.add(row["id"])

    if not drums_space_ids:
        if verbose:
            print("  No Drums/Space songs found — skipping sandwich detection")
        return 0

    # Reset all sandwich_duration to NULL
    conn.execute("UPDATE tracks SET sandwich_duration = NULL")

    # Get all releases with their ordered tracklists
    releases = conn.execute("SELECT DISTINCT release_id FROM tracks").fetchall()
    sandwiches_found = 0

    for rel_row in releases:
        release_id = rel_row["release_id"]
        tracks = conn.execute(
            """SELECT id, song_id, duration_seconds, disc_number, track_number
               FROM tracks
               WHERE release_id = ?
               ORDER BY disc_number, track_number""",
            (release_id,),
        ).fetchall()

        track_list = [(t["id"], t["song_id"], t["duration_seconds"],
                        t["disc_number"], t["track_number"]) for t in tracks]

        # Scan for sandwich patterns
        # Build groups: sequences of the same song_id interrupted only by Drums/Space
        i = 0
        while i < len(track_list):
            tid, song_id, dur, _, _ = track_list[i]

            # Skip Drums/Space/NULL/no-duration tracks as starting points
            if song_id is None or song_id in drums_space_ids or dur is None:
                i += 1
                continue

            # Found a real song. Scan forward for a sandwich pattern:
            # collect this segment, then look for Drums/Space, then same song again
            segments = [(tid, dur)]  # (track_id, duration) for this song
            j = i + 1
            in_drums_space = False

            while j < len(track_list):
                jtid, jsong_id, jdur, _, _ = track_list[j]

                if jsong_id in drums_space_ids:
                    in_drums_space = True
                    j += 1
                    continue

                if jsong_id == song_id and in_drums_space and jdur is not None:
                    # Found a continuation of the same song after Drums/Space
                    segments.append((jtid, jdur))
                    in_drums_space = False
                    j += 1
                    continue

                # Different song (not Drums/Space) — end of pattern
                break

            if len(segments) > 1:
                # This is a sandwich — sum all segment durations
                total_dur = sum(d for _, d in segments)
                # First segment gets the total
                conn.execute(
                    "UPDATE tracks SET sandwich_duration = ? WHERE id = ?",
                    (total_dur, segments[0][0]),
                )
                # Continuation segments get 0 (excluded from MAX)
                for seg_id, _ in segments[1:]:
                    conn.execute(
                        "UPDATE tracks SET sandwich_duration = ? WHERE id = ?",
                        (0, seg_id),
                    )
                sandwiches_found += 1

            # Advance past the segments we consumed
            if len(segments) > 1:
                i = j
            else:
                i += 1

    conn.commit()
    if verbose:
        print(f"  Detected {sandwiches_found} Drums/Space sandwiches")
    return sandwiches_found


def _per_show_durations(conn):
    """Return per-show durations for every song, deduped by concert date.

    For each (song_id, concert_date):
    - MAX(effective_duration) within each release, where effective_duration
      prefers sandwich_duration (summed Drums-sandwich) over raw duration
    - Best release per date via ROW_NUMBER (highest quality_rank, then
      longest duration as tiebreaker)

    Returns dict: song_id → [(concert_date, duration_seconds), ...]
    """
    rows = conn.execute("""
        SELECT sub.song_id, sub.concert_date, sub.show_dur
        FROM (
            SELECT t.song_id, r.concert_date,
                   MAX(COALESCE(NULLIF(t.sandwich_duration, 0), t.duration_seconds)) AS show_dur,
                   ROW_NUMBER() OVER (
                       PARTITION BY t.song_id, r.concert_date
                       ORDER BY r.quality_rank DESC,
                                MAX(COALESCE(NULLIF(t.sandwich_duration, 0), t.duration_seconds)) DESC
                   ) AS rn
            FROM tracks t
            JOIN releases r ON t.release_id = r.id
            WHERE t.song_id IS NOT NULL
              AND t.duration_seconds IS NOT NULL
              AND r.concert_date IS NOT NULL
            GROUP BY t.song_id, r.concert_date, r.id
        ) sub
        WHERE sub.rn = 1
        ORDER BY sub.song_id, sub.concert_date
    """).fetchall()

    result = {}
    for r in rows:
        result.setdefault(r["song_id"], []).append(
            (r["concert_date"], r["show_dur"])
        )
    return result


def compute_song_stats(conn, verbose=True):
    """Compute duration statistics for all songs and flag outliers.

    Uses per-show aggregated durations (one value per concert date) so that
    split songs and multiple tapers don't skew the results.
    """
    show_data = _per_show_durations(conn)
    updated = 0
    outliers_found = 0

    for song_id, date_durs in show_data.items():
        durations = [d for _, d in date_durs]
        dates = sorted(d for d, _ in date_durs)
        times_played = len(durations)

        if not durations:
            continue

        first_played = dates[0]
        last_played = dates[-1]

        median_dur = statistics.median(durations)
        mean_dur = statistics.mean(durations)
        std_dur = statistics.stdev(durations) if len(durations) >= 2 else 0.0

        db.update_song_stats(
            conn, song_id,
            times_played=times_played,
            median_duration=median_dur,
            mean_duration=mean_dur,
            std_duration=std_dur,
            first_played=first_played,
            last_played=last_played,
        )
        updated += 1

        # Flag outliers on per-show durations, then propagate to tracks
        if times_played >= MIN_SAMPLES_FOR_STATS and std_dur > 0:
            outlier_dates = set()
            for date, dur in date_durs:
                deviation = abs(dur - mean_dur)
                if deviation > OUTLIER_STD_MULTIPLIER * std_dur:
                    outlier_dates.add(date)

            # Mark all tracks belonging to outlier shows
            if outlier_dates:
                tracks = conn.execute(
                    """SELECT t.id, r.concert_date
                       FROM tracks t
                       JOIN releases r ON t.release_id = r.id
                       WHERE t.song_id = ?
                         AND t.duration_seconds IS NOT NULL""",
                    (song_id,),
                ).fetchall()
                for t in tracks:
                    is_outlier = 1 if t["concert_date"] in outlier_dates else 0
                    if is_outlier:
                        outliers_found += 1
                    db.mark_outlier(conn, t["id"], is_outlier)

    conn.commit()

    if verbose:
        print(f"  Updated stats for {updated} songs")
        print(f"  Flagged {outliers_found} outlier tracks")

    return updated, outliers_found


def print_song_summary(conn, top_n=20):
    """Print a summary of songs with the most variability."""
    rows = conn.execute(
        """SELECT canonical_name, times_played, median_duration, mean_duration,
                  std_duration, first_played, last_played
           FROM songs
           WHERE times_played >= ? AND std_duration IS NOT NULL
           ORDER BY std_duration DESC
           LIMIT ?""",
        (MIN_SAMPLES_FOR_STATS, top_n),
    ).fetchall()

    if not rows:
        print("  No songs with enough data for analysis.")
        return

    print(f"\n  Top {len(rows)} most variable songs:")
    print(f"  {'Song':<40} {'N':>4} {'Median':>8} {'Mean':>8} {'StdDev':>8}")
    print(f"  {'-'*40} {'-'*4} {'-'*8} {'-'*8} {'-'*8}")
    for r in rows:
        med = _fmt_duration(r["median_duration"])
        mean = _fmt_duration(r["mean_duration"])
        std = _fmt_duration(r["std_duration"])
        print(f"  {r['canonical_name']:<40} {r['times_played']:>4} {med:>8} {mean:>8} {std:>8}")


def _fmt_duration(seconds):
    """Format seconds as M:SS or H:MM:SS."""
    if seconds is None:
        return "-"
    seconds = int(round(seconds))
    if seconds >= 3600:
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        return f"{h}:{m:02d}:{s:02d}"
    m = seconds // 60
    s = seconds % 60
    return f"{m}:{s:02d}"
