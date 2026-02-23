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
from matplotlib.patches import Patch
import numpy as np

from gdtimings.db import get_connection

# ── Config ────────────────────────────────────────────────────────────────
OUTPUT_DIR = Path(__file__).parent / "output"


def get_conn():
    return get_connection()


# ══════════════════════════════════════════════════════════════════════════
# 1. Streamgraph — Top 10 songs stacked duration by year
# ══════════════════════════════════════════════════════════════════════════
def plot_streamgraph(conn):
    rows = conn.execute("""
        SELECT song, concert_year AS year,
               SUM(duration_seconds) / 3600.0 AS total_hours
        FROM best_performances
        WHERE concert_year IS NOT NULL
        GROUP BY song, concert_year
    """).fetchall()

    # Find top 10 songs by total time (utility tracks filtered by view)
    song_totals = {}
    for r in rows:
        song_totals[r["song"]] = song_totals.get(r["song"], 0) + r["total_hours"]
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
    fig.savefig(OUTPUT_DIR / "01_streamgraph.png", dpi=150)
    plt.close(fig)
    print("  01_streamgraph.png")


# ══════════════════════════════════════════════════════════════════════════
# Space-filling curve helpers (Hilbert & Gosper)
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


# ── Duration-bin color palette (jewel tones on dark background) ───────
BIN_COLORS = ["#FFFFFF", "#FFD700", "#FF6B6B", "#4ECDC4", "#A78BFA"]
#              white     gold       coral      teal       lavender
BIN_LABELS = ["Gigantous (25+ min)", "Epic jams", "Extended", "Standard", "Short"]
# Fixed threshold for the gigantous bin (absolute, not percentile-based).
_GIGANTOUS_THRESHOLD = 25.0  # minutes


def _duration_thresholds(durs):
    """Compute duration bin thresholds.

    Uses strict ``>`` with q50 nudged up by 0.1 min so that performances
    barely over a round-minute boundary (e.g. 8 min 0.1 s) fall into the
    lower bin.  Overall balance stays within ±7 of perfect quartiles.
    """
    q75, q50, q25 = np.percentile(durs, [75, 50, 25])
    return q75, q50 + 0.1, q25


def _duration_bins(durs):
    """Assign each duration to one of 5 bins (0 = longest).

    Bin 0 (Gigantous) uses a fixed 25-min threshold — these are rare
    outlier performances (11 of 626 PITB).  Bins 1-4 use quartile splits
    of the remaining data.
    """
    q75, q50, q25 = _duration_thresholds(durs)
    bins = np.empty(len(durs), dtype=int)
    for i, d in enumerate(durs):
        if d >= _GIGANTOUS_THRESHOLD:
            bins[i] = 0
        elif d > q75:
            bins[i] = 1
        elif d > q50:
            bins[i] = 2
        elif d > q25:
            bins[i] = 3
        else:
            bins[i] = 4
    return bins


def _sunflower_layout(durs, min_size=0.35, max_size=2.4, spacing=1.1,
                      size_aware=False):
    """Place tiles on a Fermat sunflower spiral (golden-angle spacing).

    Each successive tile is rotated by the golden angle (~137.5°) and pushed
    outward by √i, producing the classic sunflower seed pattern.  Tile side
    length ∝ √duration so that tile *area* ∝ duration.

    If size_aware=True, radii accumulate based on tile sizes so that larger
    tiles get more room — eliminates center overlap when tiles are sorted
    by duration descending.

    Returns (tile_cx, tile_cy, tile_angles, tile_sizes, r_outer).
    """
    n = len(durs)
    max_dur = durs.max()

    # ── Tile sizes: area ∝ duration → side ∝ √duration ──
    tile_sizes = min_size + np.sqrt(durs / max_dur) * (max_size - min_size)

    # ── Golden-angle spiral positions ──
    golden_angle = np.pi * (3 - np.sqrt(5))  # ≈ 2.3999 rad ≈ 137.508°
    tile_cx = np.empty(n)
    tile_cy = np.empty(n)
    tile_angles = np.empty(n)

    if size_aware:
        # Use r = c * (i+1)^0.7 instead of √i.  The steeper exponent
        # spreads the first (largest) tiles further apart while still
        # converging to a compact disc overall.
        c = spacing * 0.5  # rescale so outer radius stays comparable
        for i in range(n):
            theta = i * golden_angle
            r = c * (i + 1) ** 0.7
            tile_cx[i] = r * np.cos(theta)
            tile_cy[i] = r * np.sin(theta)
            tile_angles[i] = theta
        r_outer = c * n ** 0.7 + max_size
    else:
        c = spacing
        for i in range(n):
            theta = i * golden_angle
            r = c * np.sqrt(i + 1)
            tile_cx[i] = r * np.cos(theta)
            tile_cy[i] = r * np.sin(theta)
            tile_angles[i] = theta
        r_outer = c * np.sqrt(n) + max_size

    return tile_cx, tile_cy, tile_angles, tile_sizes, r_outer


# ── Strip-layout helpers ─────────────────────────────────────────────────



def _strip_layout(year_data, max_strip_width=50.0,
                  min_size=0.2, max_size=2.5, size_scale=1.0, pad=1.0):
    """Compute tile positions for a dense year-strip layout.

    Tiles are laid out chronologically within each year.  If a year's
    tiles don't fit in one row, the year wraps into multiple rows.
    Each tile's slot equals its rendered size * pad, guaranteeing
    zero overlap.

    Parameters
    ----------
    year_data : dict[int, list[dict]]
        {year: [{"dur_min": float, "month": int, "date": str}, ...]}.
    size_scale : float
        Multiplier applied to tile sizes (e.g. 1.3 for Gosper density
        compensation).  Baked into the stored size so drawing code can
        use t["size"] directly.
    pad : float
        Slot width = size * pad.  1.05 = 5% gap between tiles.

    Returns
    -------
    tiles : list[dict]
        Per-tile dict with keys: cx, cy, size, rotation, dur_min, date, year.
    strip_bounds : dict[int, dict]
        {year: {"y_center", "height", "x_left", "x_right"}}.
    fig_bounds : tuple (x_min, x_max, y_min, y_max).
    """
    all_years = sorted(year_data.keys())
    max_dur = max(p["dur_min"] for perfs in year_data.values() for p in perfs)

    tiles = []
    strip_bounds = {}
    y_cursor = 0.0  # top of the figure

    for yr in all_years:
        perfs = year_data[yr]
        if not perfs:
            continue

        # Chronological order within each year
        chrono = sorted(perfs, key=lambda p: p["date"])

        # Compute rendered tile sizes (includes size_scale)
        tile_infos = []
        for p in chrono:
            size = (min_size + (p["dur_min"] / max_dur)
                    * (max_size - min_size)) * size_scale
            tile_infos.append((p, size))

        # Greedily fill rows left-to-right; wrap when next tile exceeds width
        rows = [[]]
        row_widths = [0.0]
        for item in tile_infos:
            slot = item[1] * pad
            if row_widths[-1] + slot > max_strip_width and rows[-1]:
                rows.append([])
                row_widths.append(0.0)
            rows[-1].append(item)
            row_widths[-1] += slot

        # Place tiles
        yr_y_top = y_cursor
        for row in rows:
            row_h = max(s for _, s in row)
            y_center = y_cursor - row_h / 2
            row_w = sum(s * pad for _, s in row)

            x_pos = -row_w / 2
            for p, size in row:
                slot_w = size * pad
                cx = x_pos + slot_w / 2

                tiles.append({
                    "cx": cx, "cy": y_center, "size": size, "rotation": 0.0,
                    "dur_min": p["dur_min"], "date": p["date"],
                    "year": yr, "month": p["month"],
                })
                x_pos += slot_w

            y_cursor -= row_h

        yr_h = yr_y_top - y_cursor
        yr_y_center = yr_y_top - yr_h / 2
        strip_bounds[yr] = {
            "y_center": yr_y_center, "height": yr_h,
            "x_left": -max_strip_width / 2, "x_right": max_strip_width / 2,
        }

    x_min = -max_strip_width / 2 - 2
    x_max = max_strip_width / 2 + 2
    y_min = y_cursor - 1
    y_max = 1

    return tiles, strip_bounds, (x_min, x_max, y_min, y_max)


def _draw_strip_decorations(ax, strip_bounds, fig_bounds, all_years):
    """Draw year labels and separator lines between consecutive years."""
    x_label = fig_bounds[0] + 0.5

    sorted_years = sorted(strip_bounds.keys())
    for yr in sorted_years:
        sb = strip_bounds[yr]
        # Year label centered vertically in the year's strip
        ax.text(x_label, sb["y_center"], str(yr),
                color="#aaaacc", fontsize=14, fontweight="bold",
                ha="right", va="center", zorder=5)

    # Draw separator lines between consecutive years (at the boundary)
    for i in range(len(sorted_years) - 1):
        yr_above = sorted_years[i]
        yr_below = sorted_years[i + 1]
        sb_above = strip_bounds[yr_above]
        sb_below = strip_bounds[yr_below]
        y_boundary = (sb_above["y_center"] - sb_above["height"] / 2
                      + sb_below["y_center"] + sb_below["height"] / 2) / 2
        ax.axhline(y=y_boundary, xmin=0, xmax=1, color="#444466",
                   linewidth=0.5, zorder=0.5)


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


# ══════════════════════════════════════════════════════════════════════════
# 2. Hilbert Sunflower — Playing in the Band (chronological)
# ══════════════════════════════════════════════════════════════════════════

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
    tile_cx, tile_cy, _, tile_sizes, r_outer = _sunflower_layout(durs)

    # ── Color = duration (power-law scale) ──
    dur_norm = mcolors.PowerNorm(gamma=0.5, vmin=durs.min(), vmax=durs.max())
    cmap = plt.cm.YlOrRd

    fig, ax = plt.subplots(figsize=(22, 22))
    fig.set_facecolor("#1a1a2e")
    ax.set_facecolor("#1a1a2e")

    # Draw smallest tiles first so the epic jams render on top
    draw_order = sorted(range(n_tiles), key=lambda i: durs[i])
    lw_map = {2: 0.9, 3: 0.8, 4: 0.5, 5: 0.25}

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

    fig.savefig(OUTPUT_DIR / "02_hilbert_playing_in_band.png", dpi=200,
                facecolor=fig.get_facecolor())
    plt.close(fig)
    print("  02_hilbert_playing_in_band.png")


# ══════════════════════════════════════════════════════════════════════════
# 3. Gosper Sunflower — Playing in the Band (chronological)
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
    tile_cx, tile_cy, _, tile_sizes, r_outer = _sunflower_layout(durs)

    # Gosper curves don't fill their bounding box as densely as Hilbert,
    # so scale up by ~30% for visual equivalence.
    tile_sizes = tile_sizes * 1.3

    # Orient tiles radially outward from center
    orient_angles = np.arctan2(tile_cy, tile_cx)

    # ── Draw ──
    dur_norm = mcolors.PowerNorm(gamma=0.5, vmin=durs.min(), vmax=durs.max())
    cmap = plt.cm.YlOrRd
    lw_map = {1: 1.0, 2: 1.0, 3: 0.5, 4: 0.25}

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

    fig.savefig(OUTPUT_DIR / "03_gosper_flow_playing_in_band.png", dpi=200,
                facecolor=fig.get_facecolor())
    plt.close(fig)
    print("  03_gosper_flow_playing_in_band.png")


# ══════════════════════════════════════════════════════════════════════════
# 4. Hilbert Strip — year-strips of PITB Hilbert tiles
# ══════════════════════════════════════════════════════════════════════════

def plot_hilbert_strip(conn):
    """Dense year-strip layout with Hilbert tiles — longest jams at center."""
    rows = _query_pitb_with_month(conn)
    year_data = _build_year_data(rows)
    tiles, strip_bounds, fig_bounds = _strip_layout(year_data)

    all_durs = np.array([t["dur_min"] for t in tiles])
    max_dur = all_durs.max()

    # Pre-compute Hilbert curves (orders 2-6 to match sunflower plots)
    h_orders = [2, 3, 4, 5, 6]
    curves = {o: _hilbert_points(o) for o in h_orders}
    grids = {o: 2 ** o for o in h_orders}

    # 5-bin system matching sunflower plots
    bins = _duration_bins(all_durs)
    bin_to_order = {0: 6, 1: 5, 2: 4, 3: 3, 4: 2}
    lw_map = {2: 0.9, 3: 0.8, 4: 0.5, 5: 0.25, 6: 0.15}
    base_size = 2.0

    fig, ax = plt.subplots(figsize=(24, 30))
    fig.set_facecolor("#1a1a2e")
    ax.set_facecolor("#1a1a2e")

    all_years = sorted(year_data.keys())
    _draw_strip_decorations(ax, strip_bounds, fig_bounds, all_years)

    # Draw tiles chronologically, connecting consecutive tiles in same row
    prev_end = None
    prev_cy = None
    for idx in range(len(tiles)):
        t = tiles[idx]
        dur = t["dur_min"]
        size = t["size"]
        cx, cy = t["cx"], t["cy"]
        rot = t["rotation"]

        bini = bins[idx]
        order = bin_to_order[bini]
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

        # Connect to previous tile in same row
        if prev_end is not None and cy == prev_cy:
            ax.plot([prev_end[0], xs[0]], [prev_end[1], ys[0]],
                    color="#666688", linewidth=0.4, alpha=0.6, zorder=0.5)

        color = BIN_COLORS[bini]
        zorder = 1 + dur / max_dur
        lw = lw_map[order] * (size / base_size)
        ax.plot(xs, ys, color=color, linewidth=lw, alpha=0.92,
                solid_capstyle="round", zorder=zorder)

        prev_end = (xs[-1], ys[-1])
        prev_cy = cy

    ax.set_xlim(fig_bounds[0], fig_bounds[1])
    ax.set_ylim(fig_bounds[2], fig_bounds[3])
    ax.set_aspect("equal")
    ax.axis("off")

    ax.set_title("Playing in the Band — Hilbert Year Strips\n"
                 "tile area & complexity ∝ duration  ·  "
                 "longest jams at center",
                 fontsize=15, pad=14, color="white")

    # Duration legend (matching sunflower plots)
    q75, q50, q25 = _duration_thresholds(all_durs)
    labels = [f"Gigantous (≥25 min)", f"Epic jams (≥{q75:.0f} min)",
              f"Extended ({q50:.0f}–{q75:.0f} min)",
              f"Standard ({q25:.0f}–{q50:.0f} min)", f"Short (<{q25:.0f} min)"]
    patches = [Patch(facecolor=BIN_COLORS[i], label=labels[i]) for i in range(5)]
    leg = ax.legend(handles=patches, loc="upper center", fontsize=11,
                    ncol=5, framealpha=0.85, facecolor="#1a1a2e",
                    edgecolor="#444", labelcolor="white",
                    bbox_to_anchor=(0.5, 1.0))
    leg.get_frame().set_linewidth(0.5)

    fig.savefig(OUTPUT_DIR / "04_hilbert_strip_playing_in_band.png", dpi=200,
                facecolor=fig.get_facecolor())
    plt.close(fig)
    print("  04_hilbert_strip_playing_in_band.png")


# ══════════════════════════════════════════════════════════════════════════
# 5. Gosper Strip — year-strips of PITB Gosper tiles
# ══════════════════════════════════════════════════════════════════════════

def plot_gosper_strip(conn):
    """Dense year-strip layout with Gosper tiles — longest jams at center."""
    rows = _query_pitb_with_month(conn)
    year_data = _build_year_data(rows)
    tiles, strip_bounds, fig_bounds = _strip_layout(year_data, size_scale=1.3)

    all_durs = np.array([t["dur_min"] for t in tiles])
    max_dur = all_durs.max()

    # Pre-compute normalized Gosper curves (orders 1-5 to match sunflower plots)
    gosper_norm = {}
    gosper_angle = {}
    for order in range(1, 6):
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

    # 5-bin system matching sunflower plots
    bins = _duration_bins(all_durs)
    bin_to_order = {0: 5, 1: 4, 2: 3, 3: 2, 4: 1}
    lw_map = {1: 1.0, 2: 1.0, 3: 0.5, 4: 0.25, 5: 0.15}
    base_size = 2.0 * 1.3  # Gosper density compensation

    fig, ax = plt.subplots(figsize=(24, 30))
    fig.set_facecolor("#1a1a2e")
    ax.set_facecolor("#1a1a2e")

    all_years = sorted(year_data.keys())
    _draw_strip_decorations(ax, strip_bounds, fig_bounds, all_years)

    # Draw tiles chronologically, connecting consecutive tiles in same row
    prev_end = None
    prev_cy = None
    for idx in range(len(tiles)):
        t = tiles[idx]
        dur = t["dur_min"]
        size = t["size"]  # size_scale=1.3 already baked in by layout
        cx, cy = t["cx"], t["cy"]
        rot = t["rotation"]

        bini = bins[idx]
        order = bin_to_order[bini]
        pts = gosper_norm[order].copy()
        # Subtract intrinsic angle so curve aligns consistently
        rot_adj = rot - gosper_angle[order]
        ca, sa = np.cos(rot_adj), np.sin(rot_adj)
        scaled = pts * size
        rx = scaled[:, 0] * ca - scaled[:, 1] * sa + cx
        ry = scaled[:, 0] * sa + scaled[:, 1] * ca + cy

        # Connect to previous tile in same row
        if prev_end is not None and cy == prev_cy:
            ax.plot([prev_end[0], rx[0]], [prev_end[1], ry[0]],
                    color="#666688", linewidth=0.4, alpha=0.6, zorder=0.5)

        color = BIN_COLORS[bini]
        zorder = 1 + dur / max_dur
        lw = lw_map[order] * (size / base_size)
        ax.plot(rx, ry, color=color, linewidth=lw, alpha=0.92,
                solid_capstyle="round", zorder=zorder)

        prev_end = (rx[-1], ry[-1])
        prev_cy = cy

    ax.set_xlim(fig_bounds[0], fig_bounds[1])
    ax.set_ylim(fig_bounds[2], fig_bounds[3])
    ax.set_aspect("equal")
    ax.axis("off")

    ax.set_title("Playing in the Band — Gosper Year Strips\n"
                 "tile area & complexity ∝ duration  ·  "
                 "longest jams at center",
                 fontsize=15, pad=14, color="white")

    # Duration legend (matching sunflower plots)
    q75, q50, q25 = _duration_thresholds(all_durs)
    labels = [f"Gigantous (≥25 min)", f"Epic jams (≥{q75:.0f} min)",
              f"Extended ({q50:.0f}–{q75:.0f} min)",
              f"Standard ({q25:.0f}–{q50:.0f} min)", f"Short (<{q25:.0f} min)"]
    patches = [Patch(facecolor=BIN_COLORS[i], label=labels[i]) for i in range(5)]
    leg = ax.legend(handles=patches, loc="upper center", fontsize=11,
                    ncol=5, framealpha=0.85, facecolor="#1a1a2e",
                    edgecolor="#444", labelcolor="white",
                    bbox_to_anchor=(0.5, 1.0))
    leg.get_frame().set_linewidth(0.5)

    fig.savefig(OUTPUT_DIR / "05_gosper_strip_playing_in_band.png", dpi=200,
                facecolor=fig.get_facecolor())
    plt.close(fig)
    print("  05_gosper_strip_playing_in_band.png")


# ══════════════════════════════════════════════════════════════════════════
# 6. Hilbert Duration Sunflower — Playing in the Band
# ══════════════════════════════════════════════════════════════════════════

def plot_hilbert_duration(conn):
    """Hilbert sunflower sorted by duration: shortest at center, epic jams on rim."""
    rows = _query_pitb_with_month(conn)

    # Sort by duration ascending — small tiles pack tightly at center,
    # big tiles get the room they need at the outer edge.
    rows = sorted(rows, key=lambda r: r["dur_min"])
    durs = np.array([r["dur_min"] for r in rows])
    n_tiles = len(rows)
    max_dur = durs.max()

    # Pre-compute Hilbert curves at multiple orders
    h_orders = [2, 3, 4, 5, 6]
    curves = {o: _hilbert_points(o) for o in h_orders}
    grids = {o: 2 ** o for o in h_orders}

    # ── Duration bins → curve order + color ──
    bins = _duration_bins(durs)
    bin_to_order = {0: 6, 1: 5, 2: 4, 3: 3, 4: 2}
    lw_map = {2: 0.9, 3: 0.8, 4: 0.5, 5: 0.25, 6: 0.15}
    base_size = 2.0

    # Continuous linear size: tile side ∝ duration (same formula as strips)
    min_size, max_size = 1.0, 7.0
    tile_sizes = min_size + (durs / max_dur) * (max_size - min_size)

    # ── Adaptive sunflower: each ring's spacing ∝ its tile sizes ──
    # r = k * √(Σ size²)  →  density ∝ 1/size², tight center, roomy rim
    golden_angle = np.pi * (3 - np.sqrt(5))
    tile_cx = np.empty(n_tiles)
    tile_cy = np.empty(n_tiles)
    cumul_area = 0.0
    k = 0.7  # packing factor (<1 = tighter)
    for i in range(n_tiles):
        cumul_area += tile_sizes[i] ** 2
        r = k * np.sqrt(cumul_area)
        theta = i * golden_angle
        tile_cx[i] = r * np.cos(theta)
        tile_cy[i] = r * np.sin(theta)
    r_outer = k * np.sqrt(cumul_area) + tile_sizes[-1]

    # Aligned rotation (all tiles same orientation)
    tile_rots = np.zeros(n_tiles)

    fig, ax = plt.subplots(figsize=(30, 30))
    fig.set_facecolor("#1a1a2e")
    ax.set_facecolor("#1a1a2e")

    # Draw smallest tiles first so the epic jams render on top
    draw_order = sorted(range(n_tiles), key=lambda i: durs[i])

    for idx in draw_order:
        size = tile_sizes[idx]
        cx, cy = tile_cx[idx], tile_cy[idx]
        rot = tile_rots[idx]

        bini = bins[idx]
        color = BIN_COLORS[bini]
        order = bin_to_order[bini]
        pts = curves[order]
        grid_n = grids[order]

        margin = 0.04 * size
        span = size - 2 * margin
        denom = max(grid_n - 1, 1)

        # Build local coordinates centered on origin, then rotate
        local_x = np.array([-size / 2 + margin + (p[0] / denom) * span for p in pts])
        local_y = np.array([-size / 2 + margin + (p[1] / denom) * span for p in pts])
        ca, sa = np.cos(rot), np.sin(rot)
        xs = local_x * ca - local_y * sa + cx
        ys = local_x * sa + local_y * ca + cy

        zorder = 1 + durs[idx] / max_dur
        lw = lw_map[order] * (size / base_size)
        ax.plot(xs, ys, color=color, linewidth=lw, alpha=0.92,
                solid_capstyle="round", zorder=zorder)

    pad = 3.5
    ax.set_xlim(-r_outer - pad, r_outer + pad)
    ax.set_ylim(-r_outer - pad, r_outer + pad)
    ax.set_aspect("equal")
    ax.axis("off")

    ax.set_title("Playing in the Band — Hilbert Duration Sunflower\n"
                 "gigantous jams on the rim  ·  tile area & complexity ∝ duration",
                 fontsize=15, pad=14, color="white")

    # Legend
    q75, q50, q25 = _duration_thresholds(durs)
    labels = [f"Gigantous (≥25 min)", f"Epic jams (≥{q75:.0f} min)",
              f"Extended ({q50:.0f}–{q75:.0f} min)",
              f"Standard ({q25:.0f}–{q50:.0f} min)", f"Short (<{q25:.0f} min)"]
    patches = [Patch(facecolor=BIN_COLORS[i], label=labels[i]) for i in range(5)]
    leg = ax.legend(handles=patches, loc="upper center", fontsize=11,
                    ncol=5, framealpha=0.85, facecolor="#1a1a2e",
                    edgecolor="#444", labelcolor="white")
    leg.get_frame().set_linewidth(0.5)

    fig.savefig(OUTPUT_DIR / "06_hilbert_duration_sunflower.png", dpi=250,
                facecolor=fig.get_facecolor())
    plt.close(fig)
    print("  06_hilbert_duration_sunflower.png")


# ══════════════════════════════════════════════════════════════════════════
# 7. Gosper Duration Sunflower — Playing in the Band
# ══════════════════════════════════════════════════════════════════════════

def plot_gosper_duration(conn):
    """Gosper sunflower sorted by duration: shortest at center, epic jams on rim."""
    rows = conn.execute("""
        SELECT concert_date, concert_year, dur_min
        FROM best_performances
        WHERE song = 'Playing in the Band'
        ORDER BY concert_date
    """).fetchall()

    # Sort by duration ascending — small tiles pack tightly at center,
    # big tiles get the room they need at the outer edge.
    rows = sorted(rows, key=lambda r: r["dur_min"])
    durs = np.array([r["dur_min"] for r in rows])
    n_perfs = len(rows)
    max_dur = durs.max()

    # ── Pre-compute normalized Gosper curves at orders 1-5 ──
    gosper_norm = {}
    gosper_angle = {}
    for order in range(1, 6):
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

    # ── Duration bins → curve order + color ──
    bins = _duration_bins(durs)
    bin_to_order = {0: 5, 1: 4, 2: 3, 3: 2, 4: 1}
    lw_map = {1: 1.0, 2: 1.0, 3: 0.5, 4: 0.25, 5: 0.15}
    # Gosper curves are sparser than Hilbert, so 1.3× base size
    base_size = 2.0 * 1.3

    # Continuous linear size: tile side ∝ duration (same formula as strips)
    min_size, max_size = 1.0 * 1.3, 7.0 * 1.3
    tile_sizes = min_size + (durs / max_dur) * (max_size - min_size)

    # ── Adaptive sunflower: each ring's spacing ∝ its tile sizes ──
    # r = k * √(Σ size²)  →  density ∝ 1/size², tight center, roomy rim
    golden_angle = np.pi * (3 - np.sqrt(5))
    tile_cx = np.empty(n_perfs)
    tile_cy = np.empty(n_perfs)
    cumul_area = 0.0
    k = 0.54
    for i in range(n_perfs):
        cumul_area += tile_sizes[i] ** 2
        r = k * np.sqrt(cumul_area)
        theta = i * golden_angle
        tile_cx[i] = r * np.cos(theta)
        tile_cy[i] = r * np.sin(theta)
    r_outer = k * np.sqrt(cumul_area) + tile_sizes[-1]

    # Aligned rotation (all tiles same orientation)
    tile_rots = np.zeros(n_perfs)

    fig, ax = plt.subplots(figsize=(30, 30))
    fig.set_facecolor("#1a1a2e")
    ax.set_facecolor("#1a1a2e")

    # Draw smallest tiles first so the epic jams render on top
    draw_order = sorted(range(n_perfs), key=lambda i: durs[i])

    for idx in draw_order:
        bini = bins[idx]
        order = bin_to_order[bini]
        pts = gosper_norm[order].copy()
        size = tile_sizes[idx]
        rot = tile_rots[idx]

        # Subtract intrinsic angle so curve aligns with random rotation
        rot_adj = rot - gosper_angle[order]
        ca, sa = np.cos(rot_adj), np.sin(rot_adj)
        scaled = pts * size
        rx = scaled[:, 0] * ca - scaled[:, 1] * sa + tile_cx[idx]
        ry = scaled[:, 0] * sa + scaled[:, 1] * ca + tile_cy[idx]

        color = BIN_COLORS[bini]
        zorder = 1 + durs[idx] / max_dur
        lw = lw_map[order] * (size / base_size)

        ax.plot(rx, ry, color=color, linewidth=lw, alpha=0.92,
                solid_capstyle="round", zorder=zorder)

    pad = 3.5
    ax.set_xlim(-r_outer - pad, r_outer + pad)
    ax.set_ylim(-r_outer - pad, r_outer + pad)
    ax.set_aspect("equal")
    ax.axis("off")

    ax.set_title("Playing in the Band — Gosper Duration Sunflower\n"
                 "gigantous jams on the rim  ·  tile area & complexity ∝ duration",
                 fontsize=15, pad=14, color="white")

    # Legend
    q75, q50, q25 = _duration_thresholds(durs)
    labels = [f"Gigantous (≥25 min)", f"Epic jams (≥{q75:.0f} min)",
              f"Extended ({q50:.0f}–{q75:.0f} min)",
              f"Standard ({q25:.0f}–{q50:.0f} min)", f"Short (<{q25:.0f} min)"]
    patches = [Patch(facecolor=BIN_COLORS[i], label=labels[i]) for i in range(5)]
    leg = ax.legend(handles=patches, loc="upper center", fontsize=11,
                    ncol=5, framealpha=0.85, facecolor="#1a1a2e",
                    edgecolor="#444", labelcolor="white")
    leg.get_frame().set_linewidth(0.5)

    fig.savefig(OUTPUT_DIR / "07_gosper_duration_sunflower.png", dpi=250,
                facecolor=fig.get_facecolor())
    plt.close(fig)
    print("  07_gosper_duration_sunflower.png")


# ── Era definitions for PITB segmented sunflowers ────────────────────────
PITB_ERAS = [
    ("Genesis",     1970, 1971),
    ("Peak Jams",   1972, 1974),
    ("Post-Hiatus", 1976, 1979),
    ("Transition",  1980, 1984),
    ("Stadium",     1985, 1989),
    ("Late Era",    1990, 1995),
]


def _assign_eras(rows):
    """Assign each row to a PITB era, returning list of (era_index, row) pairs.

    Rows whose concert_year doesn't fall into any era are dropped (e.g. 1975).
    """
    assigned = []
    for r in rows:
        yr = r["concert_year"]
        for ei, (_, y0, y1) in enumerate(PITB_ERAS):
            if y0 <= yr <= y1:
                assigned.append((ei, r))
                break
    return assigned


def _era_wedge_layout(assigned, tile_sizes, k=0.7,
                      gap_deg=1.5, era_k_scales=None):
    """Compute tile positions for era-segmented sunflower.

    Parameters
    ----------
    assigned : list of (era_index, row)
        Pre-sorted by era, then by duration ascending within each era.
    tile_sizes : array
        Pre-computed tile sizes (one per element of assigned).
    era_k_scales : dict, optional
        Per-era multiplier for k (e.g. {1: 0.8} to tighten Peak Jams).
    k : float
        Packing factor.
    gap_deg : float
        Angular gap between eras in degrees.

    Returns
    -------
    tile_cx, tile_cy, tile_sizes, r_outer, era_boundaries
    """
    n = len(assigned)
    tile_cx = np.empty(n)
    tile_cy = np.empty(n)

    # Count tiles per era
    era_counts = [0] * len(PITB_ERAS)
    for ei, _ in assigned:
        era_counts[ei] += 1

    total_count = sum(era_counts)
    total_gap = len([c for c in era_counts if c > 0]) * gap_deg
    usable_deg = 360.0 - total_gap

    # Compute angular wedges (start from 12 o'clock = -π/2, going clockwise)
    gap_rad = np.radians(gap_deg)
    era_boundaries = []  # (start_angle, end_angle, era_name)
    angle_cursor = -np.pi / 2
    for ei, (name, y0, y1) in enumerate(PITB_ERAS):
        if era_counts[ei] == 0:
            continue
        wedge_deg = usable_deg * era_counts[ei] / total_count
        wedge_rad = np.radians(wedge_deg)
        era_start = angle_cursor + gap_rad / 2
        era_end = era_start + wedge_rad
        era_boundaries.append((era_start, era_end, name, ei, y0, y1))
        angle_cursor = era_end + gap_rad / 2

    # Build lookup: era_index → (start, width)
    era_wedge = {}
    for (start, end, _, ei, _, _) in era_boundaries:
        era_wedge[ei] = (start, end - start)

    # Place tiles per era using golden-angle within the wedge
    golden_angle = np.pi * (3 - np.sqrt(5))
    # Track cumulative area per era for radius computation.
    # Exponent > 0.5 pushes large (epic) tiles further out radially,
    # giving them more room at the rim where they need it.
    radial_exp = 0.55
    era_cumul = [0.0] * len(PITB_ERAS)
    era_tile_idx = [0] * len(PITB_ERAS)  # count within era

    _ek = era_k_scales or {}
    for i, (ei, _) in enumerate(assigned):
        size = tile_sizes[i]
        era_cumul[ei] += size ** 2
        r = k * _ek.get(ei, 1.0) * era_cumul[ei] ** radial_exp

        j = era_tile_idx[ei]
        era_start, era_width = era_wedge[ei]
        # Golden angle mapped into the wedge
        frac = (j * golden_angle / (2 * np.pi)) % 1.0
        theta = era_start + frac * era_width

        tile_cx[i] = r * np.cos(theta)
        tile_cy[i] = r * np.sin(theta)
        era_tile_idx[ei] += 1

    r_outer = k * np.sqrt(max(era_cumul)) + tile_sizes.max()

    return tile_cx, tile_cy, tile_sizes, r_outer, era_boundaries


def _draw_era_spokes_and_labels(ax, era_boundaries, r_outer, pad=3.5):
    """Draw radial spokes at era boundaries and horizontal era labels."""
    r_spoke = r_outer + pad * 0.3

    for start, end, name, _, y0, y1 in era_boundaries:
        # Spoke at start of each wedge
        ax.plot([0, r_spoke * np.cos(start)],
                [0, r_spoke * np.sin(start)],
                color="#555577", linewidth=3.0, alpha=0.7, zorder=0.5)

        # Label at middle of wedge, 72% of outer radius — horizontal (no rotation)
        mid_angle = (start + end) / 2
        label_r = r_outer * 0.72
        lx = label_r * np.cos(mid_angle)
        ly = label_r * np.sin(mid_angle)

        year_str = f"{y0}–{y1}" if y0 != y1 else str(y0)
        label = f"{name}\n{year_str}"
        ax.text(lx, ly, label, color="white", fontsize=14, fontweight="bold",
                ha="center", va="center", rotation=0,
                alpha=0.85, zorder=10,
                bbox=dict(boxstyle="round,pad=0.2", facecolor="#1a1a2e",
                          edgecolor="none", alpha=0.7))



# ══════════════════════════════════════════════════════════════════════════
# 8. Hilbert Duration Era Sunflower — Playing in the Band
# ══════════════════════════════════════════════════════════════════════════

def plot_hilbert_duration_era(conn):
    """Hilbert sunflower segmented by era wedges, duration-sorted within each."""
    rows = _query_pitb_with_month(conn)

    # Assign eras and sort: by era, then by duration ascending within each
    assigned = _assign_eras(rows)
    assigned.sort(key=lambda x: (x[0], x[1]["dur_min"]))

    durs = np.array([r["dur_min"] for (_, r) in assigned])
    n_tiles = len(assigned)
    max_dur = durs.max()

    # Pre-compute Hilbert curves at multiple orders
    h_orders = [2, 3, 4, 5, 6]
    curves = {o: _hilbert_points(o) for o in h_orders}
    grids = {o: 2 ** o for o in h_orders}

    # Duration bins → curve order + color
    bins = _duration_bins(durs)
    bin_to_order = {0: 6, 1: 5, 2: 4, 3: 3, 4: 2}
    lw_map = {2: 0.9, 3: 0.8, 4: 0.5, 5: 0.25, 6: 0.15}
    base_size = 2.0

    # Continuous linear size: tile side ∝ duration (same formula as strips)
    min_size, max_size = 1.0, 7.0
    tile_sizes_pre = min_size + (durs / max_dur) * (max_size - min_size)

    # Era-wedge layout
    tile_cx, tile_cy, tile_sizes, r_outer, era_boundaries = _era_wedge_layout(
        assigned, tile_sizes_pre, k=1.2,
        era_k_scales={1: 0.82, 3: 0.92})

    # Aligned rotation (all tiles same orientation)
    tile_rots = np.zeros(n_tiles)

    fig, ax = plt.subplots(figsize=(30, 30))
    fig.set_facecolor("#1a1a2e")
    ax.set_facecolor("#1a1a2e")

    # Draw era spokes and labels
    _draw_era_spokes_and_labels(ax, era_boundaries, r_outer)

    # Draw smallest tiles first so the epic jams render on top
    draw_order = sorted(range(n_tiles), key=lambda i: durs[i])

    for idx in draw_order:
        size = tile_sizes[idx]
        cx, cy = tile_cx[idx], tile_cy[idx]
        rot = tile_rots[idx]

        bini = bins[idx]
        color = BIN_COLORS[bini]
        order = bin_to_order[bini]
        pts = curves[order]
        grid_n = grids[order]

        margin = 0.04 * size
        span = size - 2 * margin
        denom = max(grid_n - 1, 1)

        # Build local coordinates centered on origin, then rotate
        local_x = np.array([-size / 2 + margin + (p[0] / denom) * span for p in pts])
        local_y = np.array([-size / 2 + margin + (p[1] / denom) * span for p in pts])
        ca, sa = np.cos(rot), np.sin(rot)
        xs = local_x * ca - local_y * sa + cx
        ys = local_x * sa + local_y * ca + cy

        zorder = 1 + durs[idx] / max_dur
        lw = lw_map[order] * (size / base_size)
        ax.plot(xs, ys, color=color, linewidth=lw, alpha=0.92,
                solid_capstyle="round", zorder=zorder)

    pad = 3.5
    shift = r_outer * 0.22  # shift view left so Peak Jams wedge has more room
    ax.set_xlim(-r_outer - pad + shift, r_outer + pad + shift)
    ax.set_ylim(-r_outer - pad, r_outer + pad)
    ax.set_aspect("equal")
    ax.axis("off")

    ax.set_title("Playing in the Band — Hilbert Duration Sunflower by Era\n"
                 "wedges ∝ track count  ·  gigantous jams on the rim  ·  "
                 "tile area & complexity ∝ duration",
                 fontsize=15, pad=14, color="white")

    # Duration legend (top row)
    q75, q50, q25 = _duration_thresholds(durs)
    labels = [f"Gigantous (≥25 min)", f"Epic jams (≥{q75:.0f} min)",
              f"Extended ({q50:.0f}–{q75:.0f} min)",
              f"Standard ({q25:.0f}–{q50:.0f} min)", f"Short (<{q25:.0f} min)"]
    patches = [Patch(facecolor=BIN_COLORS[i], label=labels[i]) for i in range(5)]
    leg = ax.legend(handles=patches, loc="upper center", fontsize=11,
                    ncol=5, framealpha=0.85, facecolor="#1a1a2e",
                    edgecolor="#444", labelcolor="white",
                    bbox_to_anchor=(0.5, 1.0))
    leg.get_frame().set_linewidth(0.5)

    # Era legend (second row, below duration legend)
    era_colors = ["#7B68EE", "#FF8C00", "#20B2AA", "#DC143C", "#32CD32", "#BA55D3"]
    era_patches = []
    for i, (_, _, name, _, y0, y1) in enumerate(era_boundaries):
        yr = f"{y0}–{y1}" if y0 != y1 else str(y0)
        era_patches.append(Patch(facecolor=era_colors[i % len(era_colors)],
                                 alpha=0.0, label=f"{name} ({yr})"))
    leg2 = ax.legend(handles=era_patches, loc="upper center", fontsize=13,
                     ncol=len(era_boundaries), framealpha=0.85,
                     facecolor="#1a1a2e", edgecolor="#444", labelcolor="#aaaacc",
                     bbox_to_anchor=(0.5, 0.97))
    leg2.get_frame().set_linewidth(0.5)
    ax.add_artist(leg)  # re-add first legend so both display

    fig.savefig(OUTPUT_DIR / "08_hilbert_duration_era.png", dpi=250,
                facecolor=fig.get_facecolor())
    plt.close(fig)
    print("  08_hilbert_duration_era.png")


# ══════════════════════════════════════════════════════════════════════════
# 9. Gosper Duration Era Sunflower — Playing in the Band
# ══════════════════════════════════════════════════════════════════════════

def _gosper_tile_rotations(n_tiles, mode, rng):
    """Compute per-tile rotations for Gosper plots.

    Modes:
      "random"    – uniform [0, 2π) per tile (original behavior)
      "aligned"   – all tiles at 0° (after subtracting intrinsic angle)
      "hex6"      – quantized to nearest 60° multiple (6 orientations)
      "hex3"      – quantized to nearest 120° multiple (3 orientations)
    """
    if mode == "aligned":
        return np.zeros(n_tiles)
    elif mode == "hex6":
        # 6 orientations at 0°, 60°, 120°, 180°, 240°, 300°
        choices = np.arange(6) * (np.pi / 3)
        return rng.choice(choices, n_tiles)
    elif mode == "hex3":
        choices = np.arange(3) * (2 * np.pi / 3)
        return rng.choice(choices, n_tiles)
    else:  # "random"
        return rng.uniform(0, 2 * np.pi, n_tiles)


def plot_gosper_duration_era(conn, rotation_mode="aligned", suffix=""):
    """Gosper sunflower segmented by era wedges, duration-sorted within each.

    rotation_mode: "random" | "aligned" | "hex6" | "hex3"
    suffix: appended to filename, e.g. "_aligned"
    """
    rows = _query_pitb_with_month(conn)

    # Assign eras and sort: by era, then by duration ascending within each
    assigned = _assign_eras(rows)
    assigned.sort(key=lambda x: (x[0], x[1]["dur_min"]))

    durs = np.array([r["dur_min"] for (_, r) in assigned])
    n_tiles = len(assigned)
    max_dur = durs.max()
    rng = np.random.default_rng(42)

    # Pre-compute normalized Gosper curves at orders 1-5
    gosper_norm = {}
    gosper_angle = {}
    for order in range(1, 6):
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

    # Duration bins → curve order + color
    bins = _duration_bins(durs)
    bin_to_order = {0: 5, 1: 4, 2: 3, 3: 2, 4: 1}
    lw_map = {1: 1.0, 2: 1.0, 3: 0.5, 4: 0.25, 5: 0.15}
    base_size = 2.0 * 1.3  # Gosper density compensation

    # Continuous linear size: tile side ∝ duration (same formula as strips)
    min_size, max_size = 1.0 * 1.3, 7.0 * 1.3
    tile_sizes_pre = min_size + (durs / max_dur) * (max_size - min_size)

    # Era-wedge layout (tighter k for Gosper's larger tiles)
    tile_cx, tile_cy, tile_sizes, r_outer, era_boundaries = _era_wedge_layout(
        assigned, tile_sizes_pre, k=0.92,
        era_k_scales={1: 0.82, 3: 0.92})

    # Tile rotations — strategy depends on mode
    tile_rots = _gosper_tile_rotations(n_tiles, rotation_mode, rng)

    fig, ax = plt.subplots(figsize=(30, 30))
    fig.set_facecolor("#1a1a2e")
    ax.set_facecolor("#1a1a2e")

    # Draw era spokes and labels
    _draw_era_spokes_and_labels(ax, era_boundaries, r_outer)

    # Draw smallest tiles first so the epic jams render on top
    draw_order = sorted(range(n_tiles), key=lambda i: durs[i])

    for idx in draw_order:
        bini = bins[idx]
        order = bin_to_order[bini]
        pts = gosper_norm[order].copy()
        size = tile_sizes[idx]
        rot = tile_rots[idx]

        # Subtract intrinsic angle so curve aligns with chosen rotation
        rot_adj = rot - gosper_angle[order]
        ca, sa = np.cos(rot_adj), np.sin(rot_adj)
        scaled = pts * size
        rx = scaled[:, 0] * ca - scaled[:, 1] * sa + tile_cx[idx]
        ry = scaled[:, 0] * sa + scaled[:, 1] * ca + tile_cy[idx]

        color = BIN_COLORS[bini]
        zorder = 1 + durs[idx] / max_dur
        lw = lw_map[order] * (size / base_size)

        ax.plot(rx, ry, color=color, linewidth=lw, alpha=0.92,
                solid_capstyle="round", zorder=zorder)

    pad = 3.5
    shift = r_outer * 0.22  # shift view left so Peak Jams wedge has more room
    ax.set_xlim(-r_outer - pad + shift, r_outer + pad + shift)
    ax.set_ylim(-r_outer - pad, r_outer + pad)
    ax.set_aspect("equal")
    ax.axis("off")

    mode_label = {"random": "random rotation", "aligned": "aligned (0°)",
                  "hex6": "hex-6 (60° quantized)", "hex3": "hex-3 (120° quantized)"}
    ax.set_title(f"Playing in the Band — Gosper Duration Sunflower by Era\n"
                 f"rotation: {mode_label.get(rotation_mode, rotation_mode)}  ·  "
                 f"tile area & complexity ∝ duration",
                 fontsize=15, pad=14, color="white")

    # Duration legend (top row)
    q75, q50, q25 = _duration_thresholds(durs)
    labels = [f"Gigantous (≥25 min)", f"Epic jams (≥{q75:.0f} min)",
              f"Extended ({q50:.0f}–{q75:.0f} min)",
              f"Standard ({q25:.0f}–{q50:.0f} min)", f"Short (<{q25:.0f} min)"]
    patches = [Patch(facecolor=BIN_COLORS[i], label=labels[i]) for i in range(5)]
    leg = ax.legend(handles=patches, loc="upper center", fontsize=11,
                    ncol=5, framealpha=0.85, facecolor="#1a1a2e",
                    edgecolor="#444", labelcolor="white",
                    bbox_to_anchor=(0.5, 1.0))
    leg.get_frame().set_linewidth(0.5)

    # Era legend (second row, below duration legend)
    era_colors = ["#7B68EE", "#FF8C00", "#20B2AA", "#DC143C", "#32CD32", "#BA55D3"]
    era_patches = []
    for i, (_, _, name, _, y0, y1) in enumerate(era_boundaries):
        yr = f"{y0}–{y1}" if y0 != y1 else str(y0)
        era_patches.append(Patch(facecolor=era_colors[i % len(era_colors)],
                                 alpha=0.0, label=f"{name} ({yr})"))
    leg2 = ax.legend(handles=era_patches, loc="upper center", fontsize=13,
                     ncol=len(era_boundaries), framealpha=0.85,
                     facecolor="#1a1a2e", edgecolor="#444", labelcolor="#aaaacc",
                     bbox_to_anchor=(0.5, 0.97))
    leg2.get_frame().set_linewidth(0.5)
    ax.add_artist(leg)  # re-add first legend so both display

    fname = f"09_gosper_duration_era{suffix}.png"
    fig.savefig(OUTPUT_DIR / fname, dpi=250,
                facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"  {fname}")


# ══════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════
def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    conn = get_conn()
    print("Generating visualizations...")
    plot_streamgraph(conn)
    plot_hilbert(conn)
    plot_gosper_flow(conn)
    plot_hilbert_strip(conn)
    plot_gosper_strip(conn)
    plot_hilbert_duration(conn)
    plot_gosper_duration(conn)
    plot_hilbert_duration_era(conn)
    plot_gosper_duration_era(conn)
    conn.close()
    print(f"Done — 9 plots saved to {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
