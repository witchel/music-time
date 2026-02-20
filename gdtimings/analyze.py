"""Outlier detection and consensus timing statistics."""

import statistics

from gdtimings import db
from gdtimings.config import OUTLIER_STD_MULTIPLIER, MIN_SAMPLES_FOR_STATS


def compute_song_stats(conn, verbose=True):
    """Compute duration statistics for all songs and flag outliers.

    For each song with enough samples:
    - Compute mean, median, std deviation of durations
    - Track first/last played dates
    - Flag individual tracks as outliers if > N std devs from mean
    """
    songs = db.all_songs(conn)
    updated = 0
    outliers_found = 0

    for song in songs:
        tracks = db.get_tracks_for_song(conn, song["id"])
        durations = [t["duration_seconds"] for t in tracks if t["duration_seconds"]]
        if not durations:
            continue

        times_played = len(durations)

        # Get concert dates for first/last played
        dates = []
        for t in tracks:
            release = conn.execute(
                "SELECT concert_date FROM releases WHERE id = ?", (t["release_id"],)
            ).fetchone()
            if release and release["concert_date"]:
                dates.append(release["concert_date"])
        dates.sort()
        first_played = dates[0] if dates else None
        last_played = dates[-1] if dates else None

        median_dur = statistics.median(durations)
        mean_dur = statistics.mean(durations)
        std_dur = statistics.stdev(durations) if len(durations) >= 2 else 0.0

        db.update_song_stats(
            conn, song["id"],
            times_played=times_played,
            median_duration=median_dur,
            mean_duration=mean_dur,
            std_duration=std_dur,
            first_played=first_played,
            last_played=last_played,
        )
        updated += 1

        # Flag outliers (need enough samples and non-zero std)
        if times_played >= MIN_SAMPLES_FOR_STATS and std_dur > 0:
            for t in tracks:
                if t["duration_seconds"] is None:
                    continue
                deviation = abs(t["duration_seconds"] - mean_dur)
                is_outlier = 1 if deviation > OUTLIER_STD_MULTIPLIER * std_dur else 0
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
