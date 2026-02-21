"""Generate example visualizations from the gdtimings SQLite database.

Usage:
    uv run --extra viz python -m viz.examples
"""

from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np

from gdtimings.db import get_connection
from gdtimings.location import US_STATE_ABBREV

# ── Config ────────────────────────────────────────────────────────────────
OUTPUT_DIR = Path(__file__).parent / "output"

# Utility tracks to exclude from ranked song lists
SKIP_SONGS = {"tuning", "Drums", "Space", "crowd"}

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


# Full state name → abbreviation (derived from gdtimings.location canonical source).
STATE_NAME_TO_ABBR = {v: k for k, v in US_STATE_ABBREV.items()}


# ── Season/tour classification (Option C) ─────────────────────────────
# Spring: Feb–May, Summer: Jun–Sep, Fall/Winter: Oct–Jan
MONTH_TO_SEASON = {
    1: "Fall/Winter", 2: "Spring", 3: "Spring", 4: "Spring",
    5: "Spring", 6: "Summer", 7: "Summer", 8: "Summer",
    9: "Summer", 10: "Fall/Winter", 11: "Fall/Winter", 12: "Fall/Winter",
}
# Each season gets a 120° angular sector; Spring at top.
_SECTOR_WIDTH = 2 * np.pi / 3
_SECTOR_MARGIN = np.radians(3)
SEASON_SECTORS = {
    "Spring":      np.radians(30),   # 30°–150°  (centered at top)
    "Summer":      np.radians(150),  # 150°–270° (centered lower-left)
    "Fall/Winter": np.radians(270),  # 270°–390° (centered lower-right)
}


def to_abbr(state_name):
    """Convert a state name (full or already abbreviated) to 2-letter abbreviation."""
    if not state_name:
        return None
    if len(state_name) <= 2:
        return state_name.upper()
    return STATE_NAME_TO_ABBR.get(state_name)


def get_conn():
    return get_connection()


# ══════════════════════════════════════════════════════════════════════════
# 1. Terrain Map — Dark Star duration over time, colored by region
# ══════════════════════════════════════════════════════════════════════════
def plot_terrain(conn):
    rows = conn.execute("""
        SELECT concert_date, dur_min, state
        FROM best_performances
        WHERE song = 'Dark Star'
        ORDER BY concert_date
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
        SELECT song, concert_year AS year,
               AVG(dur_min) AS avg_min,
               COUNT(*) AS n
        FROM best_performances
        WHERE concert_year IS NOT NULL
        GROUP BY song, concert_year
    """).fetchall()

    # Find top 30 songs by total performances
    song_counts = {}
    for r in rows:
        song_counts[r["song"]] = song_counts.get(r["song"], 0) + r["n"]
    for skip in SKIP_SONGS:
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
        SELECT concert_date, dur_min,
               COALESCE(LOWER(set_name), 'unknown') AS sn
        FROM best_performances
        WHERE song = 'Dark Star'
        ORDER BY concert_date
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
        SELECT song, concert_year AS year,
               SUM(duration_seconds) / 3600.0 AS total_hours
        FROM best_performances
        WHERE concert_year IS NOT NULL
        GROUP BY song, concert_year
    """).fetchall()

    # Find top 10 songs by total time (excluding utility tracks)
    song_totals = {}
    for r in rows:
        song_totals[r["song"]] = song_totals.get(r["song"], 0) + r["total_hours"]
    for skip in SKIP_SONGS:
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
        SELECT state, AVG(dur_min) AS avg_min, COUNT(*) AS n
        FROM best_performances
        WHERE song = 'Dark Star' AND state IS NOT NULL
        GROUP BY state
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
        SELECT song, concert_year AS year,
               AVG(dur_min) AS avg_min,
               COUNT(*) AS n
        FROM best_performances
        WHERE concert_year IS NOT NULL
        GROUP BY song, concert_year
    """).fetchall()

    # Top 20 songs by performance count (excluding utility tracks)
    song_counts = {}
    for r in rows:
        song_counts[r["song"]] = song_counts.get(r["song"], 0) + r["n"]
    for skip in SKIP_SONGS:
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
        SELECT song, concert_year AS year, dur_min
        FROM best_performances
        WHERE concert_year IS NOT NULL
    """).fetchall()

    # Group by (song, year)
    groups = {}
    for r in rows:
        key = (r["song"], r["year"])
        groups.setdefault(key, []).append(r["dur_min"])

    # Top 30 songs by total performances (excluding utility tracks)
    song_total = {}
    for (song, _), vals in groups.items():
        if song not in SKIP_SONGS:
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
        SELECT concert_date, dur_min
        FROM best_performances
        WHERE song = 'Playing in the Band'
        ORDER BY concert_date
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


def _sunflower_layout(durs):
    """Place tiles on a Fermat sunflower spiral (golden-angle spacing).

    Each successive tile is rotated by the golden angle (~137.5°) and pushed
    outward by √i, producing the classic sunflower seed pattern.  Tile side
    length ∝ √duration so that tile *area* ∝ duration.

    Returns (tile_cx, tile_cy, tile_angles, tile_sizes, r_outer).
    """
    n = len(durs)
    max_dur = durs.max()

    # ── Tile sizes: area ∝ duration → side ∝ √duration ──
    min_size = 0.35
    max_size = 2.4
    tile_sizes = min_size + np.sqrt(durs / max_dur) * (max_size - min_size)

    # ── Golden-angle spiral positions ──
    golden_angle = np.pi * (3 - np.sqrt(5))  # ≈ 2.3999 rad ≈ 137.508°
    # Spacing constant: controls how tightly packed the spiral is.
    # Larger c → more spread out.  Tune so tiles mostly touch.
    c = 1.1
    tile_cx = np.empty(n)
    tile_cy = np.empty(n)
    tile_angles = np.empty(n)
    for i in range(n):
        theta = i * golden_angle
        r = c * np.sqrt(i + 1)
        tile_cx[i] = r * np.cos(theta)
        tile_cy[i] = r * np.sin(theta)
        tile_angles[i] = theta

    r_outer = c * np.sqrt(n) + max_size
    return tile_cx, tile_cy, tile_angles, tile_sizes, r_outer


# ── Strip-layout helpers for plots 11 & 12 ──────────────────────────────

# Season blocks for strip layout: month → block index & label
_STRIP_SEASONS = {
    1: (0, "Spring"), 2: (0, "Spring"), 3: (0, "Spring"),
    4: (0, "Spring"), 5: (0, "Spring"),
    6: (1, "Summer"), 7: (1, "Summer"), 8: (1, "Summer"),
    9: (1, "Summer"),
    10: (2, "Fall/Winter"), 11: (2, "Fall/Winter"), 12: (2, "Fall/Winter"),
}
_SEASON_LABELS = ["Spring", "Summer", "Fall/Winter"]


def _strip_layout(year_data, max_strip_width=50.0, min_strip_height=2.5,
                  max_strip_height=5.5, year_gap=-0.3,
                  hiatus_gap=2.5, min_size=0.2, max_size=3.5, seed=42):
    """Compute tile positions for a dense year-strip layout.

    Tiles are placed center-out: longest performances at the center of
    each strip, progressively shorter ones toward the edges.  This makes
    the epic jams visually dominant.

    Parameters
    ----------
    year_data : dict[int, list[dict]]
        {year: [{"dur_min": float, "month": int, "date": str}, ...]}.

    Returns
    -------
    tiles : list[dict]
        Per-tile dict with keys: cx, cy, size, rotation, dur_min, date, year.
    strip_bounds : dict[int, dict]
        {year: {"y_center", "height", "x_left", "x_right"}}.
    fig_bounds : tuple (x_min, x_max, y_min, y_max).
    """
    rng = np.random.default_rng(seed)

    all_years = sorted(year_data.keys())

    # Global stats for scaling
    year_total_min = {}
    year_count = {}
    for yr, perfs in year_data.items():
        year_total_min[yr] = sum(p["dur_min"] for p in perfs)
        year_count[yr] = len(perfs)

    max_total = max(year_total_min.values()) if year_total_min else 1
    max_count = max(year_count.values()) if year_count else 1
    max_dur = max(p["dur_min"] for perfs in year_data.values() for p in perfs)

    tiles = []
    strip_bounds = {}
    y_cursor = 0.0  # top of the figure

    for yr in all_years:
        perfs = year_data[yr]
        if not perfs:
            continue

        # Strip dimensions
        tot = year_total_min.get(yr, 0)
        cnt = year_count.get(yr, 0)
        strip_w = np.sqrt(tot / max_total) * max_strip_width
        strip_h = min_strip_height + (max_strip_height - min_strip_height) * np.sqrt(cnt / max_count)

        y_center = y_cursor - strip_h / 2

        # Sort by duration descending → center-out placement
        sorted_perfs = sorted(perfs, key=lambda p: p["dur_min"], reverse=True)
        total_dur = sum(p["dur_min"] for p in sorted_perfs) or 1

        # Build center-out ordering: longest at center, then alternate R/L
        center_list = []
        right_list = []
        left_list = []
        for i, p in enumerate(sorted_perfs):
            if i == 0:
                center_list.append(p)
            elif i % 2 == 1:
                right_list.append(p)
            else:
                left_list.append(p)
        ordered = list(reversed(left_list)) + center_list + right_list

        # Place tiles L→R within strip, each getting width ∝ duration
        total_w = strip_w
        x_start = -total_w / 2
        x_pos = x_start
        for p in ordered:
            frac = p["dur_min"] / total_dur
            tile_w = frac * total_w
            cx = x_pos + tile_w / 2
            cy = y_center + rng.uniform(-strip_h * 0.3, strip_h * 0.3)

            size = min_size + np.sqrt(p["dur_min"] / max_dur) * (max_size - min_size)
            rotation = rng.uniform(0, 2 * np.pi)

            tiles.append({
                "cx": cx, "cy": cy, "size": size, "rotation": rotation,
                "dur_min": p["dur_min"], "date": p["date"],
                "year": yr, "month": p["month"],
            })
            x_pos += tile_w

        strip_bounds[yr] = {
            "y_center": y_center, "height": strip_h,
            "x_left": -total_w / 2, "x_right": total_w / 2,
        }

        y_cursor -= strip_h + year_gap

        # Modest gap for 1974→1976 hiatus
        if yr == 1974:
            y_cursor -= hiatus_gap

    x_min = min(sb["x_left"] for sb in strip_bounds.values()) - 2
    x_max = max(sb["x_right"] for sb in strip_bounds.values()) + 2
    y_min = y_cursor - 1
    y_max = 1

    return tiles, strip_bounds, (x_min, x_max, y_min, y_max)


def _catmull_rom_chain(points, num_interp=8):
    """Centripetal Catmull-Rom spline through (N, 2) control points.

    Falls back to linear interpolation for <4 points.
    """
    points = np.asarray(points, dtype=float)
    n = len(points)
    if n < 2:
        return points.copy()
    if n < 4:
        # Linear interpolation fallback
        segs = []
        for i in range(n - 1):
            ts = np.linspace(0, 1, num_interp, endpoint=(i == n - 2))
            seg = points[i] + ts[:, None] * (points[i + 1] - points[i])
            segs.append(seg)
        return np.vstack(segs)

    alpha = 0.5  # centripetal

    def _t(ti, pi, pj):
        d = np.linalg.norm(pj - pi)
        return ti + d ** alpha

    result = []
    # Pad with phantom points
    pts = np.vstack([2 * points[0] - points[1], points,
                     2 * points[-1] - points[-2]])
    for i in range(len(pts) - 3):
        p0, p1, p2, p3 = pts[i], pts[i + 1], pts[i + 2], pts[i + 3]
        t0 = 0.0
        t1 = _t(t0, p0, p1)
        t2 = _t(t1, p1, p2)
        t3 = _t(t2, p2, p3)

        last = (i == len(pts) - 4)
        ts = np.linspace(t1, t2, num_interp, endpoint=last)
        for t in ts:
            a1 = (t1 - t) / (t1 - t0) * p0 + (t - t0) / (t1 - t0) * p1 if t1 != t0 else p0
            a2 = (t2 - t) / (t2 - t1) * p1 + (t - t1) / (t2 - t1) * p2 if t2 != t1 else p1
            a3 = (t3 - t) / (t3 - t2) * p2 + (t - t2) / (t3 - t2) * p3 if t3 != t2 else p2
            b1 = (t2 - t) / (t2 - t0) * a1 + (t - t0) / (t2 - t0) * a2 if t2 != t0 else a1
            b2 = (t3 - t) / (t3 - t1) * a2 + (t - t1) / (t3 - t1) * a3 if t3 != t1 else a2
            c = (t2 - t) / (t2 - t1) * b1 + (t - t1) / (t2 - t1) * b2 if t2 != t1 else b1
            result.append(c)

    return np.array(result)


def _query_pitb_with_month(conn):
    """Query PITB performances with concert_month included."""
    return conn.execute("""
        SELECT concert_date, concert_year, concert_month, dur_min
        FROM best_performances
        WHERE song = 'Playing in the Band'
        ORDER BY concert_date
    """).fetchall()


def _build_year_data(rows):
    """Group PITB query rows into year_data dict for _strip_layout."""
    year_data = defaultdict(list)
    for r in rows:
        year_data[r["concert_year"]].append({
            "dur_min": r["dur_min"],
            "month": r["concert_month"],
            "date": r["concert_date"],
        })
    return dict(year_data)


def plot_hilbert(conn):
    rows = _query_pitb_with_month(conn)

    durs = np.array([r["dur_min"] for r in rows])
    n_tiles = len(rows)
    max_dur = durs.max()

    # Pre-compute Hilbert curves at multiple orders.
    h_orders = [2, 3, 4, 5]
    curves = {o: _hilbert_points(o) for o in h_orders}
    grids = {o: 2 ** o for o in h_orders}

    # ── Choose order per performance ──
    tile_orders = np.empty(n_tiles, dtype=int)
    for i, d in enumerate(durs):
        if d < 5:
            tile_orders[i] = 2
        elif d < 10:
            tile_orders[i] = 3
        elif d < 18:
            tile_orders[i] = 4
        else:
            tile_orders[i] = 5

    # ── Sunflower spiral layout ──
    tile_cx, tile_cy, tile_angles, tile_sizes, r_outer = _sunflower_layout(durs)

    # ── Color = duration (power-law scale) ──
    dur_norm = mcolors.PowerNorm(gamma=0.5, vmin=durs.min(), vmax=durs.max())
    cmap = plt.cm.YlOrRd

    fig, ax = plt.subplots(figsize=(22, 22))
    fig.set_facecolor("#1a1a2e")
    ax.set_facecolor("#1a1a2e")

    # Draw smallest tiles first so the epic jams render on top
    draw_order = sorted(range(n_tiles), key=lambda i: durs[i])
    lw_map = {2: 2.8, 3: 1.6, 4: 0.9, 5: 0.55}

    for idx in draw_order:
        size = tile_sizes[idx]
        cx, cy = tile_cx[idx], tile_cy[idx]
        ox = cx - size / 2
        oy = cy - size / 2

        dur = durs[idx]
        color = cmap(dur_norm(dur))
        order = tile_orders[idx]
        pts = curves[order]
        grid_n = grids[order]

        margin = 0.04 * size
        span = size - 2 * margin
        denom = max(grid_n - 1, 1)
        xs = [ox + margin + (p[0] / denom) * span for p in pts]
        ys = [oy + margin + (p[1] / denom) * span for p in pts]

        zorder = 1 + durs[idx] / max_dur
        lw = lw_map[order]
        ax.plot(xs, ys, color=color, linewidth=lw, alpha=0.95,
                solid_capstyle="round", zorder=zorder)

    pad = 3.5
    ax.set_xlim(-r_outer - pad, r_outer + pad)
    ax.set_ylim(-r_outer - pad, r_outer + pad)
    ax.set_aspect("equal")
    ax.axis("off")

    # ── Title ──
    ax.set_title("Playing in the Band — Hilbert Sunflower\n"
                 "golden-angle spiral  ·  "
                 "tile area & complexity ∝ duration  ·  color = duration",
                 fontsize=15, pad=14, color="white")

    cax = fig.add_axes([0.20, 0.94, 0.60, 0.012])
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=dur_norm)
    sm.set_array([])
    cb = fig.colorbar(sm, cax=cax, orientation="horizontal")
    cb.set_label("Duration (minutes)", color="white", fontsize=12, labelpad=6)
    cb.ax.xaxis.set_tick_params(color="white", labelsize=11)
    cb.ax.xaxis.set_label_position("top")
    plt.setp(cb.ax.xaxis.get_ticklabels(), color="white")

    fig.savefig(OUTPUT_DIR / "09_hilbert_playing_in_band.png", dpi=200,
                facecolor=fig.get_facecolor())
    plt.close(fig)
    print("  09_hilbert_playing_in_band.png")


# ══════════════════════════════════════════════════════════════════════════
# 10. Gosper Rings — concentric year-rings, season sectors, tile area ∝ duration
# ══════════════════════════════════════════════════════════════════════════
def plot_gosper_flow(conn):
    """Gosper curve tiles on sunflower spiral layout."""

    rows = conn.execute("""
        SELECT concert_date, concert_year, dur_min
        FROM best_performances
        WHERE song = 'Playing in the Band'
        ORDER BY concert_date
    """).fetchall()

    durs = np.array([r["dur_min"] for r in rows])
    n_perfs = len(rows)
    max_dur = durs.max()

    # ── Pre-compute Gosper curves at orders 1-4 ──
    gosper_norm = {}
    gosper_angle = {}
    for order in range(1, 5):
        raw = _gosper_points(order)
        delta = raw[-1] - raw[0]
        gosper_angle[order] = np.arctan2(delta[1], delta[0])
        mid = (raw[0] + raw[-1]) / 2
        centered = raw - mid
        extent = max(centered[:, 0].max() - centered[:, 0].min(),
                     centered[:, 1].max() - centered[:, 1].min())
        if extent > 0:
            centered /= extent
        gosper_norm[order] = centered

    # ── Choose order per performance ──
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

    # ── Sunflower spiral layout ──
    tile_cx, tile_cy, tile_angles, tile_sizes, r_outer = _sunflower_layout(durs)

    # Gosper curves don't fill their bounding box as densely as Hilbert,
    # so scale up by ~30% for visual equivalence.
    tile_sizes = tile_sizes * 1.3

    # Orient tiles radially outward from center
    orient_angles = np.arctan2(tile_cy, tile_cx)

    # ── Draw ──
    dur_norm = mcolors.PowerNorm(gamma=0.5, vmin=durs.min(), vmax=durs.max())
    cmap = plt.cm.YlOrRd
    lw_map = {1: 3.0, 2: 2.0, 3: 1.0, 4: 0.55}

    fig, ax = plt.subplots(figsize=(22, 22))
    fig.set_facecolor("#1a1a2e")
    ax.set_facecolor("#1a1a2e")

    # Draw smallest tiles first so the epic jams render on top
    draw_order = sorted(range(n_perfs), key=lambda i: durs[i])

    for idx in draw_order:
        order = orders[idx]
        pts = gosper_norm[order].copy()
        size = tile_sizes[idx]
        tang = orient_angles[idx]

        rot = tang - gosper_angle[order]
        ca, sa = np.cos(rot), np.sin(rot)
        scaled = pts * size
        rx = scaled[:, 0] * ca - scaled[:, 1] * sa + tile_cx[idx]
        ry = scaled[:, 0] * sa + scaled[:, 1] * ca + tile_cy[idx]

        color = cmap(dur_norm(durs[idx]))
        zorder = 1 + durs[idx] / max_dur
        lw = lw_map[order]

        ax.plot(rx, ry, color=color, linewidth=lw, alpha=0.95,
                solid_capstyle="round", zorder=zorder)

    pad = 3.5
    ax.set_xlim(-r_outer - pad, r_outer + pad)
    ax.set_ylim(-r_outer - pad, r_outer + pad)
    ax.set_aspect("equal")
    ax.axis("off")

    # ── Title ──
    ax.set_title("Playing in the Band — Gosper Sunflower\n"
                 "golden-angle spiral  ·  "
                 "tile area & complexity ∝ duration  ·  color = duration",
                 fontsize=15, pad=14, color="white")

    cax = fig.add_axes([0.20, 0.94, 0.60, 0.012])
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=dur_norm)
    sm.set_array([])
    cb = fig.colorbar(sm, cax=cax, orientation="horizontal")
    cb.set_label("Duration (minutes)", color="white", fontsize=12, labelpad=6)
    cb.ax.xaxis.set_tick_params(color="white", labelsize=11)
    cb.ax.xaxis.set_label_position("top")
    plt.setp(cb.ax.xaxis.get_ticklabels(), color="white")

    fig.savefig(OUTPUT_DIR / "10_gosper_flow_playing_in_band.png", dpi=200,
                facecolor=fig.get_facecolor())
    plt.close(fig)
    print("  10_gosper_flow_playing_in_band.png")


# ══════════════════════════════════════════════════════════════════════════
# 11. Hilbert Strip — year-strips of PITB Hilbert tiles
# ══════════════════════════════════════════════════════════════════════════

def _draw_strip_decorations(ax, strip_bounds, fig_bounds, all_years):
    """Draw year labels (every 5 years) and hiatus marker."""
    x_label = fig_bounds[0] + 1.0

    for yr, sb in strip_bounds.items():
        if yr % 5 == 0:
            ax.text(x_label, sb["y_center"], str(yr),
                    color="#aaaacc", fontsize=10, fontweight="bold",
                    ha="right", va="center", zorder=5)

    if 1974 in strip_bounds and 1976 in strip_bounds:
        y_1974 = strip_bounds[1974]["y_center"] - strip_bounds[1974]["height"] / 2
        y_1976 = strip_bounds[1976]["y_center"] + strip_bounds[1976]["height"] / 2
        y_hiatus = (y_1974 + y_1976) / 2
        ax.text(x_label, y_hiatus, "'75",
                color="#555577", fontsize=8, fontstyle="italic",
                ha="right", va="center", zorder=5)


def plot_hilbert_strip(conn):
    """Dense year-strip layout with Hilbert tiles — longest jams at center."""
    rows = _query_pitb_with_month(conn)
    year_data = _build_year_data(rows)
    tiles, strip_bounds, fig_bounds = _strip_layout(year_data)

    all_durs = np.array([t["dur_min"] for t in tiles])
    max_dur = all_durs.max()

    # Pre-compute Hilbert curves
    h_orders = [2, 3, 4, 5]
    curves = {o: _hilbert_points(o) for o in h_orders}
    grids = {o: 2 ** o for o in h_orders}

    # Color mapping
    dur_norm = mcolors.PowerNorm(gamma=0.5, vmin=all_durs.min(), vmax=all_durs.max())
    cmap = plt.cm.YlOrRd
    lw_map = {2: 2.8, 3: 1.6, 4: 0.9, 5: 0.55}

    fig, ax = plt.subplots(figsize=(24, 30))
    fig.set_facecolor("#1a1a2e")
    ax.set_facecolor("#1a1a2e")

    all_years = sorted(year_data.keys())
    _draw_strip_decorations(ax, strip_bounds, fig_bounds, all_years)

    # Draw tiles — smallest first
    draw_order = sorted(range(len(tiles)), key=lambda i: tiles[i]["dur_min"])
    for idx in draw_order:
        t = tiles[idx]
        dur = t["dur_min"]
        size = t["size"]
        cx, cy = t["cx"], t["cy"]
        rot = t["rotation"]

        # Choose Hilbert order
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
        margin = 0.04 * size
        span = size - 2 * margin
        denom = max(grid_n - 1, 1)

        # Build local coordinates centered on origin
        local_x = np.array([-size / 2 + margin + (p[0] / denom) * span for p in pts])
        local_y = np.array([-size / 2 + margin + (p[1] / denom) * span for p in pts])

        # Rotate and translate
        ca, sa = np.cos(rot), np.sin(rot)
        xs = local_x * ca - local_y * sa + cx
        ys = local_x * sa + local_y * ca + cy

        color = cmap(dur_norm(dur))
        zorder = 1 + dur / max_dur
        lw = lw_map[order]
        ax.plot(xs, ys, color=color, linewidth=lw, alpha=0.95,
                solid_capstyle="round", zorder=zorder)

    ax.set_xlim(fig_bounds[0], fig_bounds[1])
    ax.set_ylim(fig_bounds[2], fig_bounds[3])
    ax.set_aspect("equal")
    ax.axis("off")

    ax.set_title("Playing in the Band — Hilbert Year Strips\n"
                 "tile area & complexity ∝ duration  ·  "
                 "longest jams at center",
                 fontsize=15, pad=14, color="white")

    cax = fig.add_axes([0.20, 0.96, 0.60, 0.008])
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=dur_norm)
    sm.set_array([])
    cb = fig.colorbar(sm, cax=cax, orientation="horizontal")
    cb.set_label("Duration (minutes)", color="white", fontsize=12, labelpad=6)
    cb.ax.xaxis.set_tick_params(color="white", labelsize=11)
    cb.ax.xaxis.set_label_position("top")
    plt.setp(cb.ax.xaxis.get_ticklabels(), color="white")

    fig.savefig(OUTPUT_DIR / "11_hilbert_strip_playing_in_band.png", dpi=200,
                facecolor=fig.get_facecolor())
    plt.close(fig)
    print("  11_hilbert_strip_playing_in_band.png")


# ══════════════════════════════════════════════════════════════════════════
# 12. Gosper Strip — year-strips of PITB Gosper tiles
# ══════════════════════════════════════════════════════════════════════════

def plot_gosper_strip(conn):
    """Dense year-strip layout with Gosper tiles — longest jams at center."""
    rows = _query_pitb_with_month(conn)
    year_data = _build_year_data(rows)
    tiles, strip_bounds, fig_bounds = _strip_layout(year_data)

    all_durs = np.array([t["dur_min"] for t in tiles])
    max_dur = all_durs.max()

    # Pre-compute normalized Gosper curves
    gosper_norm = {}
    gosper_angle = {}
    for order in range(1, 5):
        raw = _gosper_points(order)
        delta = raw[-1] - raw[0]
        gosper_angle[order] = np.arctan2(delta[1], delta[0])
        mid = (raw[0] + raw[-1]) / 2
        centered = raw - mid
        extent = max(centered[:, 0].max() - centered[:, 0].min(),
                     centered[:, 1].max() - centered[:, 1].min())
        if extent > 0:
            centered /= extent
        gosper_norm[order] = centered

    # Color mapping
    dur_norm = mcolors.PowerNorm(gamma=0.5, vmin=all_durs.min(), vmax=all_durs.max())
    cmap = plt.cm.YlOrRd
    lw_map = {1: 3.0, 2: 2.0, 3: 1.0, 4: 0.55}

    fig, ax = plt.subplots(figsize=(24, 30))
    fig.set_facecolor("#1a1a2e")
    ax.set_facecolor("#1a1a2e")

    all_years = sorted(year_data.keys())
    _draw_strip_decorations(ax, strip_bounds, fig_bounds, all_years)

    # Draw tiles — smallest first
    draw_order = sorted(range(len(tiles)), key=lambda i: tiles[i]["dur_min"])
    for idx in draw_order:
        t = tiles[idx]
        dur = t["dur_min"]
        size = t["size"] * 1.3  # Gosper density compensation
        cx, cy = t["cx"], t["cy"]
        rot = t["rotation"]

        # Choose Gosper order
        if dur < 5:
            order = 1
        elif dur < 10:
            order = 2
        elif dur < 20:
            order = 3
        else:
            order = 4

        pts = gosper_norm[order].copy()
        # Subtract intrinsic angle so curve aligns with tile rotation
        rot_adj = rot - gosper_angle[order]
        ca, sa = np.cos(rot_adj), np.sin(rot_adj)
        scaled = pts * size
        rx = scaled[:, 0] * ca - scaled[:, 1] * sa + cx
        ry = scaled[:, 0] * sa + scaled[:, 1] * ca + cy

        color = cmap(dur_norm(dur))
        zorder = 1 + dur / max_dur
        lw = lw_map[order]
        ax.plot(rx, ry, color=color, linewidth=lw, alpha=0.95,
                solid_capstyle="round", zorder=zorder)

    ax.set_xlim(fig_bounds[0], fig_bounds[1])
    ax.set_ylim(fig_bounds[2], fig_bounds[3])
    ax.set_aspect("equal")
    ax.axis("off")

    ax.set_title("Playing in the Band — Gosper Year Strips\n"
                 "tile area & complexity ∝ duration  ·  "
                 "longest jams at center",
                 fontsize=15, pad=14, color="white")

    cax = fig.add_axes([0.20, 0.96, 0.60, 0.008])
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=dur_norm)
    sm.set_array([])
    cb = fig.colorbar(sm, cax=cax, orientation="horizontal")
    cb.set_label("Duration (minutes)", color="white", fontsize=12, labelpad=6)
    cb.ax.xaxis.set_tick_params(color="white", labelsize=11)
    cb.ax.xaxis.set_label_position("top")
    plt.setp(cb.ax.xaxis.get_ticklabels(), color="white")

    fig.savefig(OUTPUT_DIR / "12_gosper_strip_playing_in_band.png", dpi=200,
                facecolor=fig.get_facecolor())
    plt.close(fig)
    print("  12_gosper_strip_playing_in_band.png")


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
    plot_hilbert_strip(conn)
    plot_gosper_strip(conn)
    conn.close()
    print(f"Done — 12 plots saved to {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
