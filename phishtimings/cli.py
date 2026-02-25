"""CLI with subcommands for the Phish timings database."""

import argparse
import csv
import os
import sys

from phishtimings import db
from phishtimings.analyze import compute_song_stats, print_song_summary, backfill_set_names
from phishtimings.config import PI_CACHE_DIR


def cmd_scrape(args):
    """Scrape release track listings from configured sources."""
    conn = db.get_connection()
    source = args.source

    if source in ("musicbrainz", "all"):
        from phishtimings.musicbrainz import scrape_all as scrape_mb
        print("Scraping MusicBrainz Phish releases...")
        releases, tracks = scrape_mb(
            conn, full=args.full, max_age_days=args.max_age
        )
        if releases == 0 and tracks == 0:
            print("  No new data (all MusicBrainz releases already scraped).")

    if source in ("livephish", "all"):
        from phishtimings.livephish import scrape_all as scrape_lp
        print("Scraping LivePhish catalog...")
        releases, tracks = scrape_lp(
            conn, full=args.full, max_age_days=args.max_age
        )
        if releases == 0 and tracks == 0:
            print("  No new data (all LivePhish shows already scraped).")

    if source in ("phishin", "all"):
        from phishtimings.phishin import scrape_all as scrape_pi
        print("Scraping phish.in fan recordings...")
        releases, tracks = scrape_pi(
            conn, full=args.full, max_age_days=args.max_age
        )
        if releases == 0 and tracks == 0:
            print("  No new data (all phish.in shows already scraped).")

    conn.close()


def cmd_analyze(args):
    """Compute song statistics, backfill set_name, and flag outliers."""
    conn = db.get_connection()
    print("Backfilling set_name from phish.in cache...")
    backfill_set_names(conn)
    print("Computing song statistics...")
    compute_song_stats(conn)
    print_song_summary(conn)
    conn.close()


def cmd_status(args):
    """Show database statistics."""
    conn = db.get_connection()
    stats = db.db_stats(conn)
    print(f"  Songs:              {stats['songs']}")
    print(f"  Song aliases:       {stats['song_aliases']}")
    print(f"  Releases:           {stats['releases']}")
    print(f"  Tracks:             {stats['tracks']}")
    print(f"  Tracks w/ duration: {stats['tracks_with_duration']}")
    print(f"  Unmatched tracks:   {stats['unmatched_tracks']}")

    # Breakdown by source
    sources = conn.execute(
        "SELECT source_type, COUNT(*) AS n FROM releases GROUP BY source_type"
    ).fetchall()
    if sources:
        print("  By source:")
        for row in sources:
            print(f"    {row['source_type']:15s} {row['n']} releases")

    # Coverage breakdown
    coverages = conn.execute(
        "SELECT coverage, COUNT(*) AS n FROM releases GROUP BY coverage ORDER BY n DESC"
    ).fetchall()
    if coverages:
        print("  By coverage:")
        for row in coverages:
            print(f"    {row['coverage'] or 'NULL':15s} {row['n']}")

    # phish.in coverage report (from cache)
    _print_coverage_report(conn)

    conn.close()


def _print_coverage_report(conn):
    """Print phish.in coverage: how many cached shows are in the DB."""
    if not os.path.isdir(PI_CACHE_DIR):
        return

    # Count cached show dates (files named YYYY-MM-DD.json in subdirs)
    import re
    date_pat = re.compile(r'^\d{4}-\d{2}-\d{2}$')
    cached_dates = set()
    for dirpath, _, filenames in os.walk(PI_CACHE_DIR):
        for fname in filenames:
            stem = fname.rsplit('.', 1)[0] if '.' in fname else fname
            if date_pat.match(stem):
                cached_dates.add(stem)

    if not cached_dates:
        return

    db_dates = db.dates_already_in_db(conn)
    covered = cached_dates & db_dates
    missing = sorted(cached_dates - db_dates)
    pct = 100 * len(covered) / len(cached_dates) if cached_dates else 0

    print(f"  Coverage: {len(covered)} of {len(cached_dates)} "
          f"phish.in shows ({pct:.1f}%)")
    if missing:
        sample = missing[:10]
        print(f"  Missing dates ({len(missing)} total): "
              f"{', '.join(sample)}{'...' if len(missing) > 10 else ''}")


def cmd_export(args):
    """Export song timings to CSV."""
    conn = db.get_connection()
    rows = db.export_tracks(conn)
    if not rows:
        print("No data to export. Run 'scrape' first.")
        conn.close()
        return

    fieldnames = rows[0].keys()
    out = args.output
    if out == "-":
        writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))
    else:
        with open(out, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow(dict(row))
        print(f"Exported {len(rows)} tracks to {out}")
    conn.close()


def main():
    parser = argparse.ArgumentParser(
        prog="phishtimings",
        description="Phish Song Timings Database",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # scrape
    p_scrape = subparsers.add_parser("scrape", help="Scrape release track listings")
    p_scrape.add_argument("--source", choices=["musicbrainz", "livephish", "phishin", "all"],
                          default="all", help="Data source (default: all)")
    p_scrape.add_argument("--full", action="store_true",
                          help="Re-scrape everything (ignore cache)")
    p_scrape.add_argument("--max-age", type=int, default=0,
                          help="Max cache age in days (0 = never expire)")
    p_scrape.set_defaults(func=cmd_scrape)

    # analyze
    p_analyze = subparsers.add_parser("analyze", help="Compute song stats and outliers")
    p_analyze.set_defaults(func=cmd_analyze)

    # status
    p_status = subparsers.add_parser("status", help="Show DB statistics")
    p_status.set_defaults(func=cmd_status)

    # export
    p_export = subparsers.add_parser("export", help="Export timings to CSV")
    p_export.add_argument("-o", "--output", default="-",
                          help="Output file (default: stdout)")
    p_export.set_defaults(func=cmd_export)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)
