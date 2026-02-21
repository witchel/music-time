"""CLI with subcommands for the Grateful Dead timings database."""

import argparse
import csv
import sys

from gdtimings import db
from gdtimings.analyze import classify_song_types, compute_song_stats, print_song_summary


def cmd_scrape(args):
    """Scrape release track listings from specified source(s)."""
    conn = db.get_connection()
    source = args.source

    if source in ("wikipedia", "all"):
        from gdtimings.wikipedia import scrape_all as scrape_wiki
        print("Scraping Wikipedia live releases...")
        releases, tracks = scrape_wiki(conn, full=args.full)
        if releases == 0 and tracks == 0:
            print("  No new data (all categories already scraped). Use --full to re-scrape.")

    if source in ("archive", "all"):
        from gdtimings.archive_org import scrape_all as scrape_archive
        print("Scraping archive.org GratefulDead collection...")
        scrape_archive(
            conn, full=args.full,
            workers=args.workers,
            use_cache=not args.no_cache,
            max_age_days=args.max_age,
        )

    conn.close()


def cmd_analyze(args):
    """Classify song types, compute statistics, and detect outliers."""
    conn = db.get_connection()
    print("Classifying song types...")
    classify_song_types(conn)
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
    if len(sources) > 1 or (sources and sources[0]["source_type"] != "wikipedia"):
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

    conn.close()


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


def cmd_normalize(args):
    """Show unresolved or fuzzy-matched song titles."""
    conn = db.get_connection()
    if args.unmatched:
        rows = db.unmatched_tracks(conn)
        if rows:
            print(f"  {len(rows)} unmatched track titles:")
            for row in rows:
                print(f"    - {row['title_raw']}")
        else:
            print("  All tracks matched to songs.")
    else:
        # Show alias stats
        fuzzy = conn.execute(
            "SELECT alias, song_id, alias_type FROM song_aliases WHERE alias_type = 'auto_fuzzy'"
        ).fetchall()
        if fuzzy:
            print(f"  {len(fuzzy)} auto-fuzzy matches:")
            for row in fuzzy:
                song = conn.execute(
                    "SELECT canonical_name FROM songs WHERE id = ?", (row["song_id"],)
                ).fetchone()
                print(f"    '{row['alias']}' → {song['canonical_name']}")
        else:
            print("  No fuzzy matches to review.")
    conn.close()


def main():
    parser = argparse.ArgumentParser(
        prog="gdtimings",
        description="Grateful Dead Song Timings Database",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # scrape
    p_scrape = subparsers.add_parser("scrape", help="Scrape release track listings")
    p_scrape.add_argument("--source", choices=["wikipedia", "archive", "all"],
                          default="wikipedia",
                          help="Data source (default: wikipedia)")
    p_scrape.add_argument("--full", action="store_true",
                          help="Re-scrape everything (ignore prior state)")
    p_scrape.add_argument("--workers", type=int, default=None,
                          help="Number of parallel fetch workers (default: 8)")
    p_scrape.add_argument("--no-cache", action="store_true",
                          help="Disable local JSON cache (sequential fetching)")
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

    # normalize
    p_norm = subparsers.add_parser("normalize", help="Song name normalization tools")
    p_norm.add_argument("--unmatched", action="store_true",
                        help="Show unresolved song titles")
    p_norm.set_defaults(func=cmd_normalize)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)
