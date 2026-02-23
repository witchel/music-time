"""Allow running as `python -m viz`."""

import argparse

from viz.examples import main

parser = argparse.ArgumentParser()
parser.add_argument(
    "--tile-mode",
    choices=["positive", "negative"],
    default="negative",
    help="Tile rendering style: colored lines on dark bg (positive) "
    "or colored fill with dark lines (negative, default)",
)
args = parser.parse_args()
main(tile_mode=args.tile_mode)
