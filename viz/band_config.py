"""Band-specific configuration for visualizations.

Each BandConfig bundles the DB path, showcase song, era definitions,
and output filename prefix so plot functions can work with any band.
"""

import os
from dataclasses import dataclass, field


@dataclass
class BandConfig:
    name: str               # "Grateful Dead" or "Phish"
    db_path: str            # full path to SQLite DB
    showcase_song: str      # "Playing in the Band" or "Tweezer"
    eras: list = field(default_factory=list)  # [(name, start_year, end_year), ...]
    output_prefix: str = "" # "gd_" or "phish_" for filenames


GD_CONFIG = BandConfig(
    name="Grateful Dead",
    db_path=os.path.expanduser("~/.gdtimings/gdtimings.db"),
    showcase_song="Playing in the Band",
    eras=[
        ("Genesis",     1970, 1971),
        ("Peak Jams",   1972, 1974),
        ("Post-Hiatus", 1976, 1979),
        ("Transition",  1980, 1984),
        ("Stadium",     1985, 1989),
        ("Late Era",    1990, 1995),
    ],
    output_prefix="",  # GD keeps original filenames for backwards compat
)

PHISH_CONFIG = BandConfig(
    name="Phish",
    db_path=os.path.expanduser("~/.phishtimings/phishtimings.db"),
    showcase_song="Tweezer",
    eras=[
        ("Early Days", 1983, 1992),
        ("Rise",       1993, 1996),
        ("Peak",       1997, 2000),
        ("Hiatus 1.0", 2003, 2004),
        ("Reunion",    2009, 2014),
        ("Modern",     2015, 2025),
    ],
    output_prefix="phish_",
)

BAND_CONFIGS = {
    "gd": GD_CONFIG,
    "phish": PHISH_CONFIG,
}
