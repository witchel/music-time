"""Generate 8 example visualizations from the gdtimings SQLite database.

Usage:
    uv run --extra viz python -m viz.examples
"""

import os
import sqlite3
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.collections import LineCollection
import numpy as np

# ── Config ────────────────────────────────────────────────────────────────
DB_PATH = os.path.expanduser("~/.gdtimings/gdtimings.db")
OUTPUT_DIR = Path(__file__).parent / "output"

# ── Region mappings ───────────────────────────────────────────────────────
STATE_REGION = {
    "AL": "South", "AK": "West", "AZ": "West", "AR": "South",
    "CA": "West", "CO": "West", "CT": "Northeast", "DE": "South",
    "FL": "South", "GA": "South", "HI": "West", "ID": "West",
    "IL": "Midwest", "IN": "Midwest", "IA": "Midwest", "KS": "Midwest",
    "KY": "South", "LA": "South", "ME": "Northeast", "MD": "South",
    "MA": "Northeast", "MI": "Midwest", "MN": "Midwest", "MS": "South",
    "MO": "Midwest", "MT": "West", "NE": "Midwest", "NV": "West",
    "NH": "Northeast", "NJ": "Northeast", "NM": "West", "NY": "Northeast",
    "NC": "South", "ND": "Midwest", "OH": "Midwest", "OK": "South",
    "OR": "West", "PA": "Northeast", "RI": "Northeast", "SC": "South",
    "SD": "Midwest", "TN": "South", "TX": "South", "UT": "West",
    "VT": "Northeast", "VA": "South", "WA": "West", "WV": "South",
    "WI": "Midwest", "WY": "West", "DC": "South",
}
REGION_COLORS = {
    "West": "#e74c3c", "Midwest": "#2ecc71",
    "South": "#f39c12", "Northeast": "#3498db",
}

# Tile-grid map: state → (col, row) for a simplified US grid.
STATE_GRID = {
    "AK": (0, 0), "ME": (10, 0),
    "WI": (5, 1), "VT": (9, 1), "NH": (10, 1),
    "WA": (0, 2), "ID": (1, 2), "MT": (2, 2), "ND": (3, 2), "MN": (4, 2),
    "IL": (5, 2), "MI": (6, 2), "NY": (8, 2), "MA": (9, 2), "CT": (10, 2),
    "OR": (0, 3), "NV": (1, 3), "WY": (2, 3), "SD": (3, 3), "IA": (4, 3),
    "IN": (5, 3), "OH": (6, 3), "PA": (7, 3), "NJ": (8, 3), "RI": (9, 3),
    "CA": (0, 4), "UT": (1, 4), "CO": (2, 4), "NE": (3, 4), "MO": (4, 4),
    "KY": (5, 4), "WV": (6, 4), "VA": (7, 4), "MD": (8, 4), "DE": (9, 4),
    "AZ": (1, 5), "NM": (2, 5), "KS": (3, 5), "AR": (4, 5), "TN": (5, 5),
    "NC": (6, 5), "SC": (7, 5), "DC": (8, 5),
    "OK": (3, 6), "LA": (4, 6), "MS": (5, 6), "AL": (6, 6), "GA": (7, 6),
    "HI": (0, 7), "TX": (3, 7), "FL": (7, 7),
}


# Full state name → abbreviation (DB stores full names like "California").
STATE_NAME_TO_ABBR = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
    "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID",
    "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
    "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
    "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN",
    "Mississippi": "MS", "Missouri": "MO", "Montana": "MT", "Nebraska": "NE",
    "Nevada": "NV", "New Hampshire": "NH", "New Jersey": "NJ",
    "New Mexico": "NM", "New York": "NY", "North Carolina": "NC",
    "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK", "Oregon": "OR",
    "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC",
    "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX", "Utah": "UT",
    "Vermont": "VT", "Virginia": "VA", "Washington": "WA",
    "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY",
    "District of Columbia": "DC",
}


def to_abbr(state_name):
    """Convert a state name (full or already abbreviated) to 2-letter abbreviation."""
    if not state_name:
        return None
    if len(state_name) <= 2:
        return state_name.upper()
    return STATE_NAME_TO_ABBR.get(state_name)


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ══════════════════════════════════════════════════════════════════════════
# 1. Terrain Map — Dark Star duration over time, colored by region
# ══════════════════════════════════════════════════════════════════════════
def plot_terrain(conn):
    rows = conn.execute("""
        SELECT r.concert_date, t.duration_seconds / 60.0 AS dur_min, r.state
        FROM tracks t
        JOIN songs s ON t.song_id = s.id
        JOIN releases r ON t.release_id = r.id
        WHERE s.canonical_name = 'Dark Star'
          AND t.duration_seconds IS NOT NULL
          AND r.concert_date IS NOT NULL
        ORDER BY r.concert_date
    """).fetchall()

    fig, ax = plt.subplots(figsize=(14, 5))
    dates = [r["concert_date"] for r in rows]
    durs = [r["dur_min"] for r in rows]
    regions = [STATE_REGION.get(to_abbr(r["state"]) or "", "Unknown") for r in rows]

    xs = np.arange(len(dates))
    for i in range(len(xs)):
        color = REGION_COLORS.get(regions[i], "#999999")
        ax.fill_between([xs[i] - 0.5, xs[i] + 0.5], 0, durs[i],
                        color=color, alpha=0.7, linewidth=0)

    ax.set_xlim(0, len(xs))
    ax.set_ylim(0, max(durs) * 1.05)
    ax.set_ylabel("Duration (minutes)")
    ax.set_title("Dark Star — Terrain Map by US Region")

    # X-axis: show decade markers
    year_ticks, year_labels = [], []
    for i, d in enumerate(dates):
        y = d[:4]
        if y.endswith("0") or y.endswith("5"):
            if not year_labels or year_labels[-1] != y:
                year_ticks.append(i)
                year_labels.append(y)
    ax.set_xticks(year_ticks)
    ax.set_xticklabels(year_labels)

    # Legend
    from matplotlib.patches import Patch
    patches = [Patch(color=c, label=r) for r, c in REGION_COLORS.items()]
    ax.legend(handles=patches, loc="upper right", framealpha=0.9)

    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "01_terrain_dark_star.png", dpi=150)
    plt.close(fig)
    print("  01_terrain_dark_star.png")


# ══════════════════════════════════════════════════════════════════════════
# 2. Heatmap Grid — Year × Song (top 30), colored by mean duration
# ══════════════════════════════════════════════════════════════════════════
def plot_heatmap(conn):
    rows = conn.execute("""
        SELECT s.canonical_name AS song, r.concert_year AS year,
               AVG(t.duration_seconds) / 60.0 AS avg_min,
               COUNT(*) AS n
        FROM tracks t
        JOIN songs s ON t.song_id = s.id
        JOIN releases r ON t.release_id = r.id
        WHERE t.duration_seconds IS NOT NULL
          AND r.concert_year IS NOT NULL
        GROUP BY s.canonical_name, r.concert_year
    """).fetchall()

    # Find top 30 songs by total performances
    song_counts = {}
    for r in rows:
        song_counts[r["song"]] = song_counts.get(r["song"], 0) + r["n"]
    # Exclude utility tracks
    for skip in ("tuning", "Drums", "Space", "crowd"):
        song_counts.pop(skip, None)
    top_songs = sorted(song_counts, key=song_counts.get, reverse=True)[:30]

    years = sorted(set(r["year"] for r in rows))
    song_idx = {s: i for i, s in enumerate(top_songs)}
    year_idx = {y: i for i, y in enumerate(years)}

    grid = np.full((len(top_songs), len(years)), np.nan)
    sizes = np.zeros_like(grid)
    for r in rows:
        if r["song"] in song_idx and r["year"] in year_idx:
            grid[song_idx[r["song"]], year_idx[r["year"]]] = r["avg_min"]
            sizes[song_idx[r["song"]], year_idx[r["year"]]] = r["n"]

    fig, ax = plt.subplots(figsize=(16, 10))
    im = ax.imshow(grid, aspect="auto", cmap="YlOrRd", interpolation="nearest")
    ax.set_xticks(range(len(years)))
    ax.set_xticklabels(years, rotation=90, fontsize=7)
    ax.set_yticks(range(len(top_songs)))
    ax.set_yticklabels(top_songs, fontsize=7)
    ax.set_title("Heatmap: Mean Duration (min) — Top 30 Songs × Year")
    fig.colorbar(im, ax=ax, label="Mean duration (minutes)", shrink=0.6)
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "02_heatmap_year_x_song.png", dpi=150)
    plt.close(fig)
    print("  02_heatmap_year_x_song.png")


# ══════════════════════════════════════════════════════════════════════════
# 3. Radial / Polar — Dark Star: angle=date, radius=duration, color=set
# ══════════════════════════════════════════════════════════════════════════
def plot_polar(conn):
    rows = conn.execute("""
        SELECT r.concert_date, t.duration_seconds / 60.0 AS dur_min,
               COALESCE(LOWER(t.set_name), 'unknown') AS sn
        FROM tracks t
        JOIN songs s ON t.song_id = s.id
        JOIN releases r ON t.release_id = r.id
        WHERE s.canonical_name = 'Dark Star'
          AND t.duration_seconds IS NOT NULL
          AND r.concert_date IS NOT NULL
        ORDER BY r.concert_date
    """).fetchall()

    # Map date to angle: full career 1965-1995 → 0 to 2π
    min_year, max_year = 1965, 1995
    total_days = (max_year - min_year + 1) * 365.25

    def date_to_angle(d):
        parts = d.split("-")
        yr, mo, dy = int(parts[0]), int(parts[1]), int(parts[2])
        day_of_career = (yr - min_year) * 365.25 + (mo - 1) * 30.44 + dy
        return 2 * np.pi * day_of_career / total_days

    set_colors = {
        "set 1": "#3498db", "set 2": "#e74c3c",
        "encore": "#2ecc71", "unknown": "#95a5a6",
    }

    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw={"projection": "polar"})
    for r in rows:
        theta = date_to_angle(r["concert_date"])
        radius = r["dur_min"]
        color = set_colors.get(r["sn"], "#95a5a6")
        ax.scatter(theta, radius, c=color, s=15, alpha=0.7, edgecolors="none")

    ax.set_title("Dark Star — Polar Timeline\n(angle = date, radius = duration)",
                 pad=20)
    ax.set_ylim(0, 50)
    ax.set_yticks([0, 10, 20, 30, 40, 50])
    ax.set_yticklabels(["0m", "10m", "20m", "30m", "40m", "50m"])

    # Year labels around the circle
    for yr in range(1966, 1995, 3):
        day_of_career = (yr - min_year) * 365.25
        angle = 2 * np.pi * day_of_career / total_days
        ax.annotate(str(yr), xy=(angle, 52), fontsize=7, ha="center",
                    annotation_clip=False)

    from matplotlib.patches import Patch
    patches = [Patch(color=c, label=k.title()) for k, c in set_colors.items()
               if k != "unknown"]
    patches.append(Patch(color="#95a5a6", label="Unknown"))
    ax.legend(handles=patches, loc="lower right", bbox_to_anchor=(1.3, 0),
              framealpha=0.9)

    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "03_polar_dark_star.png", dpi=150)
    plt.close(fig)
    print("  03_polar_dark_star.png")


# ══════════════════════════════════════════════════════════════════════════
# 4. Streamgraph — Top 10 songs stacked duration by year
# ══════════════════════════════════════════════════════════════════════════
def plot_streamgraph(conn):
    rows = conn.execute("""
        SELECT s.canonical_name AS song, r.concert_year AS year,
               SUM(t.duration_seconds) / 3600.0 AS total_hours
        FROM tracks t
        JOIN songs s ON t.song_id = s.id
        JOIN releases r ON t.release_id = r.id
        WHERE t.duration_seconds IS NOT NULL
          AND r.concert_year IS NOT NULL
        GROUP BY s.canonical_name, r.concert_year
    """).fetchall()

    # Find top 10 songs by total time (excluding utility tracks)
    song_totals = {}
    for r in rows:
        song_totals[r["song"]] = song_totals.get(r["song"], 0) + r["total_hours"]
    for skip in ("tuning", "crowd"):
        song_totals.pop(skip, None)
    top10 = sorted(song_totals, key=song_totals.get, reverse=True)[:10]

    years = sorted(set(r["year"] for r in rows))
    data = {s: np.zeros(len(years)) for s in top10}
    year_idx = {y: i for i, y in enumerate(years)}
    for r in rows:
        if r["song"] in data:
            data[r["song"]][year_idx[r["year"]]] = r["total_hours"]

    # Normalize each year to % of total recorded time for these songs.
    # This removes the Archive.org data-availability bias (100x more
    # recordings in the early 70s than the 80s).
    y_stack = np.vstack([data[s] for s in top10])
    year_totals = y_stack.sum(axis=0)
    year_totals[year_totals == 0] = 1  # avoid division by zero
    y_pct = y_stack / year_totals * 100

    # Center on zero (streamgraph style)
    total_pct = y_pct.sum(axis=0)
    baseline = -total_pct / 2

    fig, ax = plt.subplots(figsize=(14, 6))
    cmap = plt.cm.tab10
    bottom = baseline.copy()
    for i, song in enumerate(top10):
        ax.fill_between(years, bottom, bottom + y_pct[i],
                        color=cmap(i), alpha=0.8, label=song, linewidth=0.5,
                        edgecolor="white")
        bottom = bottom + y_pct[i]

    ax.set_xlim(years[0], years[-1])
    ax.set_title("Streamgraph — Share of Performance Time (top 10 songs)")
    ax.set_ylabel("% of recorded time (centered)")
    ax.set_xlabel("Year")
    ax.legend(loc="upper left", fontsize=7, ncol=2, framealpha=0.9)
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "04_streamgraph.png", dpi=150)
    plt.close(fig)
    print("  04_streamgraph.png")


# ══════════════════════════════════════════════════════════════════════════
# 5. Geographic Map — Dark Star mean duration by state (tile grid)
# ══════════════════════════════════════════════════════════════════════════
def plot_geographic(conn):
    rows = conn.execute("""
        SELECT r.state, AVG(t.duration_seconds) / 60.0 AS avg_min,
               COUNT(*) AS n
        FROM tracks t
        JOIN songs s ON t.song_id = s.id
        JOIN releases r ON t.release_id = r.id
        WHERE s.canonical_name = 'Dark Star'
          AND t.duration_seconds IS NOT NULL
          AND r.state IS NOT NULL
        GROUP BY r.state
    """).fetchall()

    state_data = {}
    for r in rows:
        abbr = to_abbr(r["state"])
        if abbr:
            state_data[abbr] = (r["avg_min"], r["n"])

    fig, ax = plt.subplots(figsize=(12, 8))
    cmap = plt.cm.YlOrRd
    all_avgs = [v[0] for v in state_data.values()]
    if not all_avgs:
        plt.close(fig)
        return
    norm = mcolors.Normalize(vmin=min(all_avgs), vmax=max(all_avgs))

    max_col = max(c for c, r in STATE_GRID.values()) + 1
    max_row = max(r for c, r in STATE_GRID.values()) + 1

    for st, (col, row) in STATE_GRID.items():
        if st in state_data:
            avg, n = state_data[st]
            color = cmap(norm(avg))
            ax.add_patch(plt.Rectangle((col, max_row - row - 1), 0.9, 0.9,
                                       facecolor=color, edgecolor="white",
                                       linewidth=1.5))
            ax.text(col + 0.45, max_row - row - 0.35, st, ha="center",
                    va="center", fontsize=8, fontweight="bold")
            ax.text(col + 0.45, max_row - row - 0.65, f"{avg:.0f}m",
                    ha="center", va="center", fontsize=6, color="#333")
        else:
            ax.add_patch(plt.Rectangle((col, max_row - row - 1), 0.9, 0.9,
                                       facecolor="#eeeeee", edgecolor="white",
                                       linewidth=1.5))
            ax.text(col + 0.45, max_row - row - 0.45, st, ha="center",
                    va="center", fontsize=7, color="#aaa")

    ax.set_xlim(-0.5, max_col + 0.5)
    ax.set_ylim(-0.5, max_row + 0.5)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title("Dark Star — Mean Duration by State (tile grid map)", pad=15)

    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    fig.colorbar(sm, ax=ax, label="Mean duration (minutes)", shrink=0.5,
                 pad=0.02)

    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "05_geographic_dark_star.png", dpi=150)
    plt.close(fig)
    print("  05_geographic_dark_star.png")


# ══════════════════════════════════════════════════════════════════════════
# 6. Small Multiples — Top 20 songs as sparkline tiles
# ══════════════════════════════════════════════════════════════════════════
def plot_small_multiples(conn):
    rows = conn.execute("""
        SELECT s.canonical_name AS song, r.concert_year AS year,
               AVG(t.duration_seconds) / 60.0 AS avg_min,
               COUNT(*) AS n
        FROM tracks t
        JOIN songs s ON t.song_id = s.id
        JOIN releases r ON t.release_id = r.id
        WHERE t.duration_seconds IS NOT NULL
          AND r.concert_year IS NOT NULL
        GROUP BY s.canonical_name, r.concert_year
    """).fetchall()

    # Top 20 songs by performance count (excluding utility tracks)
    song_counts = {}
    for r in rows:
        song_counts[r["song"]] = song_counts.get(r["song"], 0) + r["n"]
    for skip in ("tuning", "Drums", "Space", "crowd"):
        song_counts.pop(skip, None)
    top20 = sorted(song_counts, key=song_counts.get, reverse=True)[:20]

    years = sorted(set(r["year"] for r in rows))
    song_data = {s: {} for s in top20}
    for r in rows:
        if r["song"] in song_data:
            song_data[r["song"]][r["year"]] = r["avg_min"]

    # Compute per-song std dev across years for tile border color
    song_stds = {}
    for s in top20:
        vals = list(song_data[s].values())
        song_stds[s] = np.std(vals) if len(vals) > 1 else 0

    max_std = max(song_stds.values()) if song_stds else 1
    global_max_dur = max(v for s in top20 for v in song_data[s].values())

    ncols, nrows = 5, 4
    fig, axes = plt.subplots(nrows, ncols, figsize=(16, 10))
    std_cmap = plt.cm.viridis

    for idx, song in enumerate(top20):
        r, c = divmod(idx, ncols)
        ax = axes[r][c]
        ys = [song_data[song].get(y, 0) for y in years]
        norm_std = song_stds[song] / max_std if max_std else 0
        color = std_cmap(norm_std)

        ax.fill_between(years, 0, ys, color=color, alpha=0.7)
        ax.plot(years, ys, color=color, linewidth=0.8)
        ax.set_ylim(0, global_max_dur * 1.05)
        ax.set_xlim(years[0], years[-1])
        ax.set_title(song, fontsize=7, pad=2)
        ax.tick_params(labelsize=5)
        ax.set_xticks([1970, 1980, 1990])

    fig.suptitle("Small Multiples — Duration Over Time (color = variability)",
                 fontsize=13)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(OUTPUT_DIR / "06_small_multiples.png", dpi=150)
    plt.close(fig)
    print("  06_small_multiples.png")


# ══════════════════════════════════════════════════════════════════════════
# 7. Duration × Variability scatterplot — songs migrate over time
# ══════════════════════════════════════════════════════════════════════════
def plot_duration_variability(conn):
    rows = conn.execute("""
        SELECT s.canonical_name AS song, r.concert_year AS year,
               t.duration_seconds / 60.0 AS dur_min
        FROM tracks t
        JOIN songs s ON t.song_id = s.id
        JOIN releases r ON t.release_id = r.id
        WHERE t.duration_seconds IS NOT NULL
          AND r.concert_year IS NOT NULL
    """).fetchall()

    # Group by (song, year)
    groups = {}
    for r in rows:
        key = (r["song"], r["year"])
        groups.setdefault(key, []).append(r["dur_min"])

    # Filter: need 3+ performances in a year, exclude utility tracks
    skip = {"tuning", "Drums", "Space", "crowd"}
    # Top 30 songs by total performances
    song_total = {}
    for (song, _), vals in groups.items():
        if song not in skip:
            song_total[song] = song_total.get(song, 0) + len(vals)
    top30 = set(sorted(song_total, key=song_total.get, reverse=True)[:30])

    medians, stds, years_c, sizes = [], [], [], []
    for (song, year), vals in groups.items():
        if song in top30 and len(vals) >= 3:
            medians.append(np.median(vals))
            stds.append(np.std(vals))
            years_c.append(year)
            sizes.append(len(vals))

    fig, ax = plt.subplots(figsize=(10, 8))
    sc = ax.scatter(medians, stds, c=years_c, cmap="coolwarm",
                    s=[s * 3 for s in sizes], alpha=0.6, edgecolors="white",
                    linewidth=0.3)
    fig.colorbar(sc, ax=ax, label="Year")
    ax.set_xlabel("Median Duration (minutes)")
    ax.set_ylabel("Std Dev of Duration (minutes)")
    ax.set_title("Duration × Variability — Top 30 Songs Across Years")
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "07_duration_variability.png", dpi=150)
    plt.close(fig)
    print("  07_duration_variability.png")


# ══════════════════════════════════════════════════════════════════════════
# 8. Duration Envelope — Playing in the Band with derivative coloring
# ══════════════════════════════════════════════════════════════════════════
def plot_envelope(conn):
    rows = conn.execute("""
        SELECT r.concert_date, t.duration_seconds / 60.0 AS dur_min
        FROM tracks t
        JOIN songs s ON t.song_id = s.id
        JOIN releases r ON t.release_id = r.id
        WHERE s.canonical_name = 'Playing in the Band'
          AND t.duration_seconds IS NOT NULL
          AND r.concert_date IS NOT NULL
        ORDER BY r.concert_date
    """).fetchall()

    dates = [r["concert_date"] for r in rows]
    durs = np.array([r["dur_min"] for r in rows])
    xs = np.arange(len(durs))

    # Smoothed derivative (rate of change) using a rolling window
    window = 7
    if len(durs) > window:
        smoothed = np.convolve(durs, np.ones(window) / window, mode="same")
        deriv = np.gradient(smoothed)
    else:
        deriv = np.gradient(durs)

    # Normalize derivative to [-1, 1] for coloring
    max_abs = np.max(np.abs(deriv)) if np.max(np.abs(deriv)) > 0 else 1
    deriv_norm = deriv / max_abs

    fig, ax = plt.subplots(figsize=(14, 5))
    cmap = plt.cm.coolwarm  # blue = shrinking, red = growing

    for i in range(len(xs)):
        color = cmap((deriv_norm[i] + 1) / 2)  # map [-1,1] → [0,1]
        ax.fill_between([xs[i] - 0.5, xs[i] + 0.5], 0, durs[i],
                        color=color, alpha=0.8, linewidth=0)

    # Overlay the smoothed line
    if len(durs) > window:
        ax.plot(xs, smoothed, color="black", linewidth=0.8, alpha=0.5)

    ax.set_xlim(0, len(xs))
    ax.set_ylim(0, max(durs) * 1.05)
    ax.set_ylabel("Duration (minutes)")
    ax.set_title("Playing in the Band — Duration Envelope\n"
                 "(blue = shrinking, red = growing)")

    # X-axis: year markers
    year_ticks, year_labels = [], []
    for i, d in enumerate(dates):
        y = d[:4]
        if y.endswith("0") or y.endswith("5"):
            if not year_labels or year_labels[-1] != y:
                year_ticks.append(i)
                year_labels.append(y)
    ax.set_xticks(year_ticks)
    ax.set_xticklabels(year_labels)

    # Colorbar
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=mcolors.Normalize(-1, 1))
    sm.set_array([])
    cb = fig.colorbar(sm, ax=ax, shrink=0.6, pad=0.02)
    cb.set_label("Rate of change")
    cb.set_ticks([-1, 0, 1])
    cb.set_ticklabels(["Shrinking", "Stable", "Growing"])

    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "08_envelope_playing_in_band.png", dpi=150)
    plt.close(fig)
    print("  08_envelope_playing_in_band.png")


# ══════════════════════════════════════════════════════════════════════════
# 9. Hilbert Curve — Playing in the Band: complexity ∝ duration
# ══════════════════════════════════════════════════════════════════════════

def _d2xy(n, d):
    """Convert distance d along a Hilbert curve to (x, y) in an n×n grid."""
    x = y = 0
    s = 1
    while s < n:
        rx = 1 & (d // 2)
        ry = 1 & (d ^ rx)
        if ry == 0:
            if rx == 1:
                x = s - 1 - x
                y = s - 1 - y
            x, y = y, x
        x += s * rx
        y += s * ry
        d //= 4
        s *= 2
    return x, y


def _hilbert_points(order):
    """Return list of (x, y) points for a Hilbert curve of given order."""
    n = 2 ** order
    return [_d2xy(n, d) for d in range(n * n)]


def _gosper_points(order):
    """Generate (x, y) points for a Gosper curve (flowsnake) via L-system.

    Rules: A → A-B--B+A++AA+B-,  B → +A-BB--B-A++A+B
    Turn angle: 60°.  Each order multiplies segment count by 7.
    """
    axiom = "A"
    rules = {"A": "A-B--B+A++AA+B-", "B": "+A-BB--B-A++A+B"}
    s = axiom
    for _ in range(order):
        s = "".join(rules.get(c, c) for c in s)

    x, y = 0.0, 0.0
    direction = 0.0
    points = [(x, y)]
    for c in s:
        if c in ("A", "B"):
            rad = np.radians(direction)
            x += np.cos(rad)
            y += np.sin(rad)
            points.append((x, y))
        elif c == "+":
            direction += 60
        elif c == "-":
            direction -= 60
    return np.array(points)


def plot_hilbert(conn):
    rows = conn.execute("""
        SELECT r.concert_date, r.concert_year,
               AVG(t.duration_seconds) / 60.0 AS dur_min
        FROM tracks t
        JOIN songs s ON t.song_id = s.id
        JOIN releases r ON t.release_id = r.id
        WHERE s.canonical_name = 'Playing in the Band'
          AND t.duration_seconds IS NOT NULL
          AND r.concert_date IS NOT NULL
        GROUP BY r.concert_date
        ORDER BY r.concert_date
    """).fetchall()

    durs = np.array([r["dur_min"] for r in rows])
    years = np.array([r["concert_year"] for r in rows])
    n_tiles = len(rows)
    max_dur = durs.max()

    # Pre-compute Hilbert curves at multiple orders.
    orders = [2, 3, 4, 5]
    curves = {o: _hilbert_points(o) for o in orders}
    grids = {o: 2 ** o for o in orders}

    # ── Archimedean spiral layout ──
    # Place tiles at equal arc-length intervals along r = r0 + b*θ.
    # This keeps consecutive performances spatially adjacent (readable order).
    tile_size = 0.85
    r0 = 1.2
    growth = 0.22         # ring gap = growth * 2π ≈ 1.38 > tile_size
    n_revolutions = 8
    max_theta = 2 * np.pi * n_revolutions

    # Build a fine spiral to compute arc length
    n_fine = 20000
    thetas_fine = np.linspace(0, max_theta, n_fine)
    r_fine = r0 + growth * thetas_fine
    x_fine = r_fine * np.cos(thetas_fine)
    y_fine = r_fine * np.sin(thetas_fine)
    ds = np.sqrt(np.diff(x_fine)**2 + np.diff(y_fine)**2)
    arc = np.concatenate([[0], np.cumsum(ds)])

    # Place tiles at equal arc-length intervals
    target_arcs = np.linspace(0, arc[-1], n_tiles + 2)[1:-1]
    tile_thetas = np.interp(target_arcs, arc, thetas_fine)
    tile_rs = r0 + growth * tile_thetas
    tile_cx = tile_rs * np.cos(tile_thetas)
    tile_cy = tile_rs * np.sin(tile_thetas)

    # ── Color = duration ──
    dur_norm = mcolors.Normalize(vmin=durs.min(), vmax=durs.max())
    cmap = plt.cm.YlOrRd

    fig, ax = plt.subplots(figsize=(14, 14))
    fig.set_facecolor("#1a1a2e")
    ax.set_facecolor("#1a1a2e")

    for idx in range(n_tiles):
        cx, cy = tile_cx[idx], tile_cy[idx]
        ox = cx - tile_size / 2
        oy = cy - tile_size / 2

        dur = durs[idx]
        color = cmap(dur_norm(dur))

        # Subtle tile background
        ax.add_patch(plt.Rectangle((ox - 0.02, oy - 0.02), tile_size + 0.04,
                                   tile_size + 0.04, facecolor="#252545",
                                   edgecolor="none", zorder=1))

        # Pick discrete Hilbert order based on duration
        if dur < 5:
            order = 2
        elif dur < 10:
            order = 3
        elif dur < 18:
            order = 4
        else:
            order = 5
        pts = curves[order]
        grid_n = grids[order]

        # Scale points into the tile
        margin = 0.06
        span = tile_size - 2 * margin
        denom = max(grid_n - 1, 1)
        xs = [ox + margin + (p[0] / denom) * span for p in pts]
        ys = [oy + margin + (p[1] / denom) * span for p in pts]

        lw = {2: 2.0, 3: 1.2, 4: 0.7, 5: 0.45}[order]
        ax.plot(xs, ys, color=color, linewidth=lw, alpha=0.9,
                solid_capstyle="round", zorder=2)

    # ── Year rings at 12 o'clock ──
    unique_years = sorted(set(years))
    ring_years = unique_years[::3]
    if unique_years[-1] not in ring_years:
        ring_years.append(unique_years[-1])

    for yr in ring_years:
        yr_mask = years >= yr
        if not yr_mask.any():
            continue
        pi = np.where(yr_mask)[0][0]
        ring_r = tile_rs[pi]

        circle = plt.Circle((0, 0), ring_r, fill=False,
                             edgecolor="#333344", linewidth=0.5,
                             linestyle="--", zorder=0)
        ax.add_patch(circle)
        ax.text(0, ring_r + tile_size * 0.6, str(yr), color="#777788",
                fontsize=8, ha="center", va="bottom", fontweight="bold",
                zorder=5)

    pad = tile_size * 2
    ax.set_xlim(tile_cx.min() - pad, tile_cx.max() + pad)
    ax.set_ylim(tile_cy.min() - pad, tile_cy.max() + pad)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title("Playing in the Band — Hilbert Spiral\n"
                 "center = first performance (1971), spiraling outward  ·  "
                 "density & color ∝ duration",
                 fontsize=11, pad=12, color="white")

    sm = plt.cm.ScalarMappable(cmap=cmap, norm=dur_norm)
    sm.set_array([])
    cb = fig.colorbar(sm, ax=ax, shrink=0.35, pad=0.02, aspect=30)
    cb.set_label("Duration (minutes)", color="white")
    cb.ax.yaxis.set_tick_params(color="white")
    plt.setp(cb.ax.yaxis.get_ticklabels(), color="white")

    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "09_hilbert_playing_in_band.png", dpi=200,
                facecolor=fig.get_facecolor())
    plt.close(fig)
    print("  09_hilbert_playing_in_band.png")


# ══════════════════════════════════════════════════════════════════════════
# 10. Gosper Spiral — continuous flowsnake, tile area ∝ duration
# ══════════════════════════════════════════════════════════════════════════
def plot_gosper_flow(conn):
    """Gosper curve tiles on an Archimedean spiral — one continuous line.

    Like plot #9 but with Gosper (flowsnake) curves instead of Hilbert,
    tile size scales with duration (area ∝ duration), no bounding boxes,
    and the curve is continuous — each tile's end connects to the next
    tile's start along the spiral backbone.
    """

    rows = conn.execute("""
        SELECT r.concert_date, r.concert_year,
               AVG(t.duration_seconds) / 60.0 AS dur_min
        FROM tracks t
        JOIN songs s ON t.song_id = s.id
        JOIN releases r ON t.release_id = r.id
        WHERE s.canonical_name = 'Playing in the Band'
          AND t.duration_seconds IS NOT NULL
          AND r.concert_date IS NOT NULL
        GROUP BY r.concert_date
        ORDER BY r.concert_date
    """).fetchall()

    durs = np.array([r["dur_min"] for r in rows])
    years = np.array([r["concert_year"] for r in rows])
    n_perfs = len(rows)
    max_dur = durs.max()

    # ── Pre-compute Gosper curves at orders 1-4 ──
    gosper_norm = {}    # centered & unit-scaled points
    gosper_angle = {}   # angle of start→end vector (for alignment)
    for order in range(1, 5):
        raw = _gosper_points(order)
        delta = raw[-1] - raw[0]
        gosper_angle[order] = np.arctan2(delta[1], delta[0])
        # Center at midpoint of start→end so start/end straddle the center
        mid = (raw[0] + raw[-1]) / 2
        centered = raw - mid
        extent = max(centered[:, 0].max() - centered[:, 0].min(),
                     centered[:, 1].max() - centered[:, 1].min())
        if extent > 0:
            centered /= extent
        gosper_norm[order] = centered

    # ── Choose order & tile size per performance ──
    orders = np.empty(n_perfs, dtype=int)
    for i, d in enumerate(durs):
        if d < 5:
            orders[i] = 1
        elif d < 10:
            orders[i] = 2
        elif d < 20:
            orders[i] = 3
        else:
            orders[i] = 4

    # Tile size: area ∝ duration → linear size ∝ sqrt(duration)
    min_tile = 0.25
    max_tile = 1.1
    tile_sizes = min_tile + np.sqrt(durs / max_dur) * (max_tile - min_tile)

    # ── Archimedean spiral ──
    growth = 0.25
    r0 = 1.5
    n_revolutions = 10
    max_theta = 2 * np.pi * n_revolutions

    n_fine = 30000
    thetas_fine = np.linspace(0, max_theta, n_fine)
    r_fine = r0 + growth * thetas_fine
    x_fine = r_fine * np.cos(thetas_fine)
    y_fine = r_fine * np.sin(thetas_fine)
    ds = np.sqrt(np.diff(x_fine)**2 + np.diff(y_fine)**2)
    arc = np.concatenate([[0], np.cumsum(ds)])
    total_arc = arc[-1]

    # Tangent angles along fine spiral
    dx_fine = np.gradient(x_fine)
    dy_fine = np.gradient(y_fine)
    tang_fine = np.arctan2(dy_fine, dx_fine)

    # ── Arc-length spacing proportional to tile size ──
    cum_space = np.cumsum(tile_sizes)
    margin = tile_sizes[0]
    usable = total_arc - 2 * margin
    target_arcs = margin + ((cum_space - cum_space[0])
                            / (cum_space[-1] - cum_space[0]) * usable)

    tile_thetas = np.interp(target_arcs, arc, thetas_fine)
    tile_rs = r0 + growth * tile_thetas
    tile_cx = tile_rs * np.cos(tile_thetas)
    tile_cy = tile_rs * np.sin(tile_thetas)
    tile_tangents = np.interp(target_arcs, arc, tang_fine)

    # ── Build one continuous path as line segments ──
    dur_norm = mcolors.Normalize(vmin=durs.min(), vmax=durs.max())
    cmap = plt.cm.YlOrRd

    all_segments = []
    all_dur_values = []
    all_linewidths = []
    lw_map = {1: 2.0, 2: 1.2, 3: 0.7, 4: 0.4}

    prev_end = None
    for idx in range(n_perfs):
        order = orders[idx]
        pts = gosper_norm[order].copy()
        size = tile_sizes[idx]
        tang = tile_tangents[idx]

        # Rotate so the curve's start→end aligns with the spiral tangent
        rot = tang - gosper_angle[order]
        ca, sa = np.cos(rot), np.sin(rot)
        scaled = pts * size
        rx = scaled[:, 0] * ca - scaled[:, 1] * sa + tile_cx[idx]
        ry = scaled[:, 0] * sa + scaled[:, 1] * ca + tile_cy[idx]

        # Connecting segment from previous tile's end
        if prev_end is not None:
            all_segments.append([prev_end, [rx[0], ry[0]]])
            all_dur_values.append((durs[max(0, idx - 1)] + durs[idx]) / 2)
            all_linewidths.append(0.4)

        # Gosper curve segments for this performance
        for j in range(len(rx) - 1):
            all_segments.append([[rx[j], ry[j]], [rx[j + 1], ry[j + 1]]])
            all_dur_values.append(durs[idx])
            all_linewidths.append(lw_map[order])

        prev_end = [rx[-1], ry[-1]]

    segments = np.array(all_segments)
    lc = LineCollection(segments, cmap=cmap, norm=dur_norm,
                        linewidths=all_linewidths, alpha=0.9)
    lc.set_array(np.array(all_dur_values))

    fig, ax = plt.subplots(figsize=(14, 14))
    fig.set_facecolor("#1a1a2e")
    ax.set_facecolor("#1a1a2e")
    ax.add_collection(lc)

    # ── Year rings at 12 o'clock ──
    unique_years = sorted(set(years))
    ring_years = unique_years[::3]
    if unique_years[-1] not in ring_years:
        ring_years.append(unique_years[-1])

    for yr in ring_years:
        yr_mask = years >= yr
        if not yr_mask.any():
            continue
        pi = np.where(yr_mask)[0][0]
        ring_r = tile_rs[pi]

        circle = plt.Circle((0, 0), ring_r, fill=False,
                             edgecolor="#333344", linewidth=0.5,
                             linestyle="--", zorder=0)
        ax.add_patch(circle)
        ax.text(0, ring_r + max_tile * 0.4, str(yr), color="#777788",
                fontsize=8, ha="center", va="bottom", fontweight="bold",
                zorder=5)

    all_x = segments[:, :, 0].ravel()
    all_y = segments[:, :, 1].ravel()
    pad = max_tile * 2
    ax.set_xlim(all_x.min() - pad, all_x.max() + pad)
    ax.set_ylim(all_y.min() - pad, all_y.max() + pad)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title("Playing in the Band — Gosper Spiral\n"
                 "center → outward chronologically  ·  "
                 "tile area & complexity ∝ duration  ·  color = duration",
                 fontsize=11, pad=12, color="white")

    sm = plt.cm.ScalarMappable(cmap=cmap, norm=dur_norm)
    sm.set_array([])
    cb = fig.colorbar(sm, ax=ax, shrink=0.35, pad=0.02, aspect=30)
    cb.set_label("Duration (minutes)", color="white")
    cb.ax.yaxis.set_tick_params(color="white")
    plt.setp(cb.ax.yaxis.get_ticklabels(), color="white")

    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "10_gosper_flow_playing_in_band.png", dpi=200,
                facecolor=fig.get_facecolor())
    plt.close(fig)
    print("  10_gosper_flow_playing_in_band.png")


# ══════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════
def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    conn = get_conn()
    print("Generating visualizations...")
    plot_terrain(conn)
    plot_heatmap(conn)
    plot_polar(conn)
    plot_streamgraph(conn)
    plot_geographic(conn)
    plot_small_multiples(conn)
    plot_duration_variability(conn)
    plot_envelope(conn)
    plot_hilbert(conn)
    plot_gosper_flow(conn)
    conn.close()
    print(f"Done — 10 plots saved to {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
