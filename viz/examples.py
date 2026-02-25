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
import matplotlib.patches as mpatches

from viz.curves import (
    smooth_hilbert as _smooth_hilbert,
    precompute_gosper as _precompute_gosper,
    BIN_COLORS,
    BIN_LABELS,
)

# ── Config ────────────────────────────────────────────────────────────────
OUTPUT_DIR = Path(__file__).parent / "output"

# ── Theme constants ──────────────────────────────────────────────────────
DARK_BG = "#1a1a2e"
LABEL_COLOR = "white"


def get_conn():
    return get_connection()


def _create_dark_figure(figsize):
    """Create a figure + axes with the project dark background."""
    fig, ax = plt.subplots(figsize=figsize)
    fig.set_facecolor(DARK_BG)
    ax.set_facecolor(DARK_BG)
    return fig, ax


def _save_plot(fig, filename, dpi=200):
    """Save figure to OUTPUT_DIR and close it."""
    fig.savefig(OUTPUT_DIR / filename, dpi=dpi,
                facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"  {filename}")


_SHARE_MAX_BYTES = 5 * 1024 * 1024  # 5 MB target


def _save_shareable(fig, filename, dpi=120):
    """Save a tighter, smaller version for email/phone sharing.

    Uses bbox_inches='tight' to crop border whitespace and a small
    pad_inches for breathing room.  Target: <5MB per image so two
    fit within Gmail's 25MB limit.  ~2500-3000px on the long edge.

    If the initial save exceeds the target, retries at lower DPI.
    Saved alongside the full version with a '_share' suffix.
    """
    share_name = filename.replace(".png", "_share.png")
    path = OUTPUT_DIR / share_name
    save_kwargs = dict(facecolor=fig.get_facecolor(),
                       bbox_inches="tight", pad_inches=0.2)

    fig.savefig(path, dpi=dpi, **save_kwargs)
    sz = path.stat().st_size

    # Retry at lower DPI if over target
    while sz > _SHARE_MAX_BYTES and dpi > 80:
        dpi -= 10
        fig.savefig(path, dpi=dpi, **save_kwargs)
        sz = path.stat().st_size

    print(f"  {share_name} ({sz / 1e6:.1f}MB, {dpi}dpi)")


def _add_duration_legend(ax, durs, **kwargs):
    """Add a 5-bin duration legend to the axes.

    Returns the Legend object. Accepts extra kwargs passed to ax.legend().
    """
    q75, q50, q25 = _duration_thresholds(durs)
    labels = [f"Gigantous (≥25 min)", f"Epic jams (≥{q75:.0f} min)",
              f"Extended ({q50:.0f}–{q75:.0f} min)",
              f"Standard ({q25:.0f}–{q50:.0f} min)", f"Short (<{q25:.0f} min)"]
    patches = [Patch(facecolor=BIN_COLORS[i], label=labels[i]) for i in range(5)]
    defaults = dict(loc="upper center", fontsize=14, ncol=5, framealpha=0.85,
                    facecolor=DARK_BG, edgecolor="#444", labelcolor=LABEL_COLOR)
    defaults.update(kwargs)
    leg = ax.legend(handles=patches, **defaults)
    leg.get_frame().set_linewidth(0.5)
    return leg


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
    ax.legend(loc="upper left", fontsize=10, ncol=2, framealpha=0.9)
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "01_streamgraph.png", dpi=150)
    plt.close(fig)
    print("  01_streamgraph.png")


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



def _strip_layout(year_data, min_size=0.2, max_size=2.5,
                  size_scale=1.0, pad=1.15):
    """Compute tile positions for a dense year-strip layout.

    Tiles are laid out chronologically within each year.  Years that
    are wider than a global target width wrap into multiple rows; the
    target is the median year width, so most years are one row and
    large years split to match.  Each tile's slot equals its rendered
    size * pad, guaranteeing zero overlap.

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
        {year: {"y_center", "height"}}.
    fig_bounds : tuple (x_min, x_max, y_min, y_max).
    """
    all_years = sorted(year_data.keys())
    max_dur = max(p["dur_min"] for perfs in year_data.values() for p in perfs)

    # First pass: compute tile infos and total widths per year so we can
    # derive a global target row width (median of year widths for years
    # with enough tiles to potentially split).
    year_tile_infos = {}  # yr → [(perf, size), ...]
    year_total_w = {}     # yr → total slot width
    for yr in all_years:
        perfs = year_data[yr]
        if not perfs:
            continue
        chrono = sorted(perfs, key=lambda p: p["date"])
        infos = []
        for p in chrono:
            size = (min_size + (p["dur_min"] / max_dur)
                    * (max_size - min_size)) * size_scale
            infos.append((p, size))
        year_tile_infos[yr] = infos
        year_total_w[yr] = sum(s * pad for _, s in infos)

    # Target row width = median of year widths (years with ≥5 tiles).
    # This makes the typical year a single row and splits large years
    # into rows of similar width, producing a visually consistent strip.
    qualifying = [w for yr, w in year_total_w.items()
                  if len(year_tile_infos[yr]) >= 5]
    target_w = float(np.median(qualifying)) if qualifying else 20.0

    tiles = []
    strip_bounds = {}
    y_cursor = 0.0  # top of the figure

    for yr in sorted(year_tile_infos.keys()):
        tile_infos = year_tile_infos[yr]
        slot_widths = [s * pad for _, s in tile_infos]
        total_w = year_total_w[yr]

        # Split every year to approximate the global target width
        n_rows = max(1, round(total_w / target_w))
        if n_rows <= 1:
            rows = [list(tile_infos)]
        else:
            row_target = total_w / n_rows
            rows = [[]]
            row_w = 0.0
            for i, item in enumerate(tile_infos):
                sw = slot_widths[i]
                remaining_rows = n_rows - len(rows)
                if (rows[-1] and remaining_rows > 0
                        and abs(row_w + sw - row_target)
                            > abs(row_w - row_target)):
                    rows.append([])
                    row_w = 0.0
                rows[-1].append(item)
                row_w += sw

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
        }
        y_cursor -= 0.5  # gap between years

    # Compute x extent from actual tile positions
    if tiles:
        x_extent = max(abs(t["cx"]) + t["size"] / 2 for t in tiles)
    else:
        x_extent = 10.0
    x_min = -x_extent - 2
    x_max = x_extent + 2
    y_min = y_cursor - 1
    y_max = 1

    return tiles, strip_bounds, (x_min, x_max, y_min, y_max)


def _draw_strip_decorations(ax, strip_bounds, fig_bounds):
    """Draw year labels and separator lines between consecutive years."""
    x_label = fig_bounds[0] + 0.5

    sorted_years = sorted(strip_bounds.keys())
    for yr in sorted_years:
        sb = strip_bounds[yr]
        # Year label centered vertically in the year's strip
        ax.text(x_label, sb["y_center"], str(yr),
                color="#aaaacc", fontsize=14, fontweight="bold",
                ha="right", va="center", zorder=5)

    # Draw separator lines between consecutive years, spanning content width
    x_line = fig_bounds[1] - 2  # content right edge
    for i in range(len(sorted_years) - 1):
        yr_above = sorted_years[i]
        yr_below = sorted_years[i + 1]
        sb_above = strip_bounds[yr_above]
        sb_below = strip_bounds[yr_below]
        y_boundary = (sb_above["y_center"] - sb_above["height"] / 2
                      + sb_below["y_center"] + sb_below["height"] / 2) / 2
        ax.plot([x_label, x_line], [y_boundary, y_boundary],
                color="#444466", linewidth=0.5, zorder=0.5)


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
# Curve-type configuration for unified plot functions
# ══════════════════════════════════════════════════════════════════════════

# Per-curve-type parameters that differ between Hilbert and Gosper variants.
# GOSPER_SCALE compensates for Gosper's sparser bounding-box fill.
GOSPER_SCALE = 1.3

# ── Tile rendering mode ──────────────────────────────────────────────────
# "positive" = colored lines on dark background (no fill shape)
# "negative" = light tinted fill with dark (background-matched) lines
TILE_MODE = "positive"


def _lighten(hex_color, amount=0.45):
    """Blend *hex_color* toward white by *amount* (0 = unchanged, 1 = white)."""
    r, g, b = mcolors.to_rgb(hex_color)
    return (r + (1 - r) * amount, g + (1 - g) * amount, b + (1 - b) * amount)


def _darken(hex_color, amount=0.45):
    """Blend *hex_color* toward black by *amount* (0 = unchanged, 1 = black)."""
    r, g, b = mcolors.to_rgb(hex_color)
    return (r * (1 - amount), g * (1 - amount), b * (1 - amount))


# ── Tile style: per-bin order and per-mode line widths ───────────────────
# Only 2 curve orders per curve type to keep visual complexity down.
_TILE_STYLE = {
    0: {"h_order": 4, "g_order": 3,
        "positive": {"lw": 0.65},
        "negative": {"lw": 0.45}},   # Gigantous
    1: {"h_order": 4, "g_order": 3,
        "positive": {"lw": 0.65},
        "negative": {"lw": 0.40}},   # Epic
    2: {"h_order": 4, "g_order": 3,
        "positive": {"lw": 0.65},
        "negative": {"lw": 0.60}},   # Extended
    3: {"h_order": 4, "g_order": 3,
        "positive": {"lw": 0.65},
        "negative": {"lw": 0.90}},   # Standard
    4: {"h_order": 3, "g_order": 2,
        "positive": {"lw": 1.10},
        "negative": {"lw": 1.30}},   # Short
}


def _tile_colors(bini):
    """Return (fill_color, line_color, base_lw) for the active TILE_MODE."""
    style = _TILE_STYLE[bini]
    if TILE_MODE == "positive":
        ms = style["positive"]
        return None, _lighten(BIN_COLORS[bini], 0.3), ms["lw"]
    else:
        ms = style["negative"]
        fill = _lighten(BIN_COLORS[bini])
        line = _darken(BIN_COLORS[bini])
        return fill, line, ms["lw"]

_CURVE_CONFIGS = {
    "hilbert": {
        "orders": [3, 4],
        "bin_to_order": {b: s["h_order"] for b, s in _TILE_STYLE.items()},
        "lw_map": {3: 0.9, 4: 0.5},
        "base_size": 2.0,
        "size_scale": 1.0,
        # Sunflower-flow specific (pair 1) — uses continuous color, no fill
        "flow_orders": [2, 3, 4, 5],
        "flow_lw_map": {2: 0.9, 3: 0.8, 4: 0.5, 5: 0.25},
        "flow_thresholds": [(5, 2), (10, 3), (18, 4)],  # (dur_break, order)
        "flow_default_order": 5,
        # Duration sunflower specific (pair 3)
        "dur_k": 0.7,
        # Era specific (pair 4)
        "era_k": 1.2,
    },
    "gosper": {
        "orders": [2, 3],
        "bin_to_order": {b: s["g_order"] for b, s in _TILE_STYLE.items()},
        "lw_map": {2: 1.0, 3: 0.5},
        "base_size": 2.0 * GOSPER_SCALE,
        "size_scale": GOSPER_SCALE,
        # Sunflower-flow specific (pair 1) — uses continuous color, no fill
        "flow_orders": range(1, 5),
        "flow_lw_map": {1: 1.0, 2: 1.0, 3: 0.5, 4: 0.25},
        "flow_thresholds": [(5, 1), (10, 2), (20, 3)],
        "flow_default_order": 4,
        # Duration sunflower specific (pair 3)
        "dur_k": 0.54,
        # Era specific (pair 4)
        "era_k": 0.92,
    },
}

_CURVE_FILENAMES = {
    # (pair, curve_type) → output filename
    ("flow", "hilbert"): "02_hilbert_playing_in_band.png",
    ("flow", "gosper"): "03_gosper_flow_playing_in_band.png",
    ("strip", "hilbert"): "04_hilbert_strip_playing_in_band.png",
    ("strip", "gosper"): "05_gosper_strip_playing_in_band.png",
    ("duration", "hilbert"): "06_hilbert_duration_sunflower.png",
    ("duration", "gosper"): "07_gosper_duration_sunflower.png",
    ("duration_era", "hilbert"): "08_hilbert_duration_era.png",
}


def _precompute_curves(curve_type, orders):
    """Pre-compute curve data for the given type and orders.

    Returns (curve_data, angle_data) where:
    - For hilbert: curve_data is {order: (xs, ys)}, angle_data is None
    - For gosper: curve_data is {order: points_array}, angle_data is {order: angle}
    """
    if curve_type == "hilbert":
        return {o: _smooth_hilbert(o) for o in orders}, None
    else:
        return _precompute_gosper(orders)


def _draw_hilbert_tile(ax, sx, sy, size, cx, cy, rot,
                       fill_color, line_color, lw, zorder):
    """Draw a Hilbert tile: rounded-rect fill + curve line on top."""
    margin = 0.04 * size
    span = size - 2 * margin
    local_x = -size / 2 + margin + sx * span
    local_y = -size / 2 + margin + sy * span
    ca, sa = np.cos(rot), np.sin(rot)
    xs = local_x * ca - local_y * sa + cx
    ys = local_x * sa + local_y * ca + cy

    # Rounded-rectangle fill
    if fill_color is not None:
        rpad = size * 0.12
        patch = mpatches.FancyBboxPatch(
            (cx - size / 2, cy - size / 2), size, size,
            boxstyle=f"round,pad=0,rounding_size={rpad}",
            facecolor=fill_color, edgecolor="none", alpha=0.9, zorder=zorder)
        ax.add_patch(patch)

    ax.plot(xs, ys, color=line_color, linewidth=lw, alpha=0.92,
            solid_capstyle="round", zorder=zorder + 0.1)
    return xs, ys


def _draw_gosper_tile(ax, pts, gosper_angle_val, size, cx, cy, rot,
                      fill_color, line_color, lw, zorder):
    """Draw a Gosper tile: convex-hull fill + curve line on top."""
    rot_adj = rot - gosper_angle_val
    ca, sa = np.cos(rot_adj), np.sin(rot_adj)
    scaled = pts * size
    rx = scaled[:, 0] * ca - scaled[:, 1] * sa + cx
    ry = scaled[:, 0] * sa + scaled[:, 1] * ca + cy

    # Convex-hull fill
    if fill_color is not None:
        from scipy.spatial import ConvexHull
        hull_pts = np.column_stack([rx, ry])
        hull = ConvexHull(hull_pts)
        hull_verts = hull_pts[hull.vertices]
        patch = mpatches.Polygon(hull_verts, closed=True,
                                 facecolor=fill_color, edgecolor="none",
                                 alpha=0.9, zorder=zorder)
        ax.add_patch(patch)

    ax.plot(rx, ry, color=line_color, linewidth=lw, alpha=0.92,
            solid_capstyle="round", zorder=zorder + 0.1)
    return rx, ry


# ══════════════════════════════════════════════════════════════════════════
# 2-3. Sunflower — Playing in the Band (chronological)
# ══════════════════════════════════════════════════════════════════════════

def _plot_sunflower_flow(conn, curve_type="hilbert"):
    """Chronological sunflower with continuous color scale.

    curve_type: "hilbert" | "gosper"
    """
    cfg = _CURVE_CONFIGS[curve_type]
    rows = _query_pitb_with_month(conn)

    durs = np.array([r["dur_min"] for r in rows])
    n_tiles = len(rows)
    max_dur = durs.max()

    curve_data, gosper_angles = _precompute_curves(curve_type, cfg["flow_orders"])

    # Choose order per performance based on duration thresholds
    tile_orders = np.empty(n_tiles, dtype=int)
    for i, d in enumerate(durs):
        assigned = False
        for thresh, order in cfg["flow_thresholds"]:
            if d < thresh:
                tile_orders[i] = order
                assigned = True
                break
        if not assigned:
            tile_orders[i] = cfg["flow_default_order"]

    # Sunflower spiral layout
    tile_cx, tile_cy, _, tile_sizes, r_outer = _sunflower_layout(durs)

    if curve_type == "gosper":
        tile_sizes = tile_sizes * GOSPER_SCALE

    # Orient Gosper tiles radially; Hilbert tiles are axis-aligned
    orient_angles = np.arctan2(tile_cy, tile_cx) if curve_type == "gosper" else None

    # Color = duration (power-law scale)
    dur_norm = mcolors.PowerNorm(gamma=0.5, vmin=durs.min(), vmax=durs.max())
    cmap = plt.cm.YlOrRd
    lw_map = cfg["flow_lw_map"]

    fig, ax = _create_dark_figure((22, 22))
    draw_order = sorted(range(n_tiles), key=lambda i: durs[i])

    for idx in draw_order:
        size = tile_sizes[idx]
        cx, cy = tile_cx[idx], tile_cy[idx]
        order = tile_orders[idx]
        color = cmap(dur_norm(durs[idx]))
        zorder = 1 + durs[idx] / max_dur
        lw = lw_map[order]

        if curve_type == "hilbert":
            sx, sy = curve_data[order]
            ox, oy = cx - size / 2, cy - size / 2
            margin = 0.04 * size
            span = size - 2 * margin
            xs = ox + margin + sx * span
            ys = oy + margin + sy * span
            ax.plot(xs, ys, color=color, linewidth=lw, alpha=0.95,
                    solid_capstyle="round", zorder=zorder)
        else:
            pts = curve_data[order].copy()
            tang = orient_angles[idx]
            rot = tang - gosper_angles[order]
            ca, sa = np.cos(rot), np.sin(rot)
            scaled = pts * size
            rx = scaled[:, 0] * ca - scaled[:, 1] * sa + cx
            ry = scaled[:, 0] * sa + scaled[:, 1] * ca + cy
            ax.plot(rx, ry, color=color, linewidth=lw, alpha=0.95,
                    solid_capstyle="round", zorder=zorder)

    pad = 3.5
    ax.set_xlim(-r_outer - pad, r_outer + pad)
    ax.set_ylim(-r_outer - pad, r_outer + pad)
    ax.set_aspect("equal")
    ax.axis("off")

    curve_label = "Hilbert" if curve_type == "hilbert" else "Gosper"
    ax.set_title(f"Playing in the Band — {curve_label} Sunflower\n"
                 "golden-angle spiral  ·  "
                 "tile area & complexity ∝ duration  ·  color = duration",
                 fontsize=15, pad=14, color=LABEL_COLOR)

    cax = fig.add_axes([0.20, 0.94, 0.60, 0.012])
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=dur_norm)
    sm.set_array([])
    cb = fig.colorbar(sm, cax=cax, orientation="horizontal")
    cb.set_label("Duration (minutes)", color=LABEL_COLOR, fontsize=12, labelpad=6)
    cb.ax.xaxis.set_tick_params(color=LABEL_COLOR, labelsize=11)
    cb.ax.xaxis.set_label_position("top")
    plt.setp(cb.ax.xaxis.get_ticklabels(), color=LABEL_COLOR)

    fname = _CURVE_FILENAMES[("flow", curve_type)]
    _save_shareable(fig, fname)
    _save_plot(fig, fname)


def plot_hilbert(conn):
    _plot_sunflower_flow(conn, curve_type="hilbert")


def plot_gosper_flow(conn):
    _plot_sunflower_flow(conn, curve_type="gosper")


# ══════════════════════════════════════════════════════════════════════════
# 4-5. Year Strips — Playing in the Band
# ══════════════════════════════════════════════════════════════════════════

def _plot_strip(conn, curve_type="hilbert"):
    """Dense year-strip layout — longest jams at center.

    curve_type: "hilbert" | "gosper"
    """
    cfg = _CURVE_CONFIGS[curve_type]
    rows = _query_pitb_with_month(conn)
    year_data = _build_year_data(rows)
    tiles, strip_bounds, fig_bounds = _strip_layout(
        year_data, size_scale=cfg["size_scale"])

    all_durs = np.array([t["dur_min"] for t in tiles])
    max_dur = all_durs.max()

    curve_data, gosper_angles = _precompute_curves(curve_type, cfg["orders"])

    bins = _duration_bins(all_durs)
    bin_to_order = cfg["bin_to_order"]
    lw_map = cfg["lw_map"]
    base_size = cfg["base_size"]

    fig, ax = _create_dark_figure((24, 30))
    _draw_strip_decorations(ax, strip_bounds, fig_bounds)

    prev_end = None
    prev_cx = None
    prev_size = None
    prev_cy = None
    for idx in range(len(tiles)):
        t = tiles[idx]
        dur = t["dur_min"]
        size = t["size"]
        cx, cy = t["cx"], t["cy"]
        rot = t["rotation"]
        bini = bins[idx]
        order = bin_to_order[bini]
        fill_color, line_color, base_lw = _tile_colors(bini)
        zorder = 1 + dur / max_dur
        lw = base_lw * (size / base_size)

        if curve_type == "hilbert":
            xs, ys = _draw_hilbert_tile(
                ax, *curve_data[order], size, cx, cy, rot,
                fill_color, line_color, lw, zorder)
            tile_start = (xs[0], ys[0])
            tile_end = (xs[-1], ys[-1])
        else:
            rx, ry = _draw_gosper_tile(
                ax, curve_data[order].copy(), gosper_angles[order],
                size, cx, cy, rot,
                fill_color, line_color, lw, zorder)
            tile_start = (rx[0], ry[0])
            tile_end = (rx[-1], ry[-1])

        # Connect to previous tile in same row with light gray bridge
        if prev_end is not None and cy == prev_cy:
            # Draw from right edge of previous tile to left edge of current
            x0 = prev_cx + prev_size / 2
            x1 = cx - size / 2
            ax.plot([x0, x1], [cy, cy],
                    color="#888899", linewidth=0.6, alpha=0.7,
                    solid_capstyle="round", zorder=0.5)

        prev_end = tile_end
        prev_cx = cx
        prev_size = size
        prev_cy = cy

    ax.set_xlim(fig_bounds[0], fig_bounds[1])
    ax.set_ylim(fig_bounds[2], fig_bounds[3])
    ax.set_aspect("equal")
    ax.axis("off")

    n_tiles = len(tiles)
    n_years = len(strip_bounds)
    curve_label = "Hilbert" if curve_type == "hilbert" else "Gosper"
    ax.set_title(f"Playing in the Band — {curve_label} Year Strips\n"
                 f"{n_tiles} performances across {n_years} years  ·  "
                 f"tile area proportional to performance length",
                 fontsize=15, pad=14, color=LABEL_COLOR)

    _add_duration_legend(ax, all_durs, bbox_to_anchor=(0.5, 1.0))
    fname = _CURVE_FILENAMES[("strip", curve_type)]
    _save_shareable(fig, fname)
    _save_plot(fig, fname)


def plot_hilbert_strip(conn):
    _plot_strip(conn, curve_type="hilbert")


def plot_gosper_strip(conn):
    _plot_strip(conn, curve_type="gosper")


# ══════════════════════════════════════════════════════════════════════════
# 6-7. Duration Sunflower — Playing in the Band
# ══════════════════════════════════════════════════════════════════════════

def _plot_duration_sunflower(conn, curve_type="hilbert", mobile=False):
    """Duration-sorted sunflower: shortest at center, epic jams on rim.

    curve_type: "hilbert" | "gosper"
    mobile: if True, render a compact 1500×1500 version (no title, tight pad)
    """
    cfg = _CURVE_CONFIGS[curve_type]
    rows = _query_pitb_with_month(conn)

    rows = sorted(rows, key=lambda r: r["dur_min"])
    durs = np.array([r["dur_min"] for r in rows])
    n_tiles = len(rows)
    max_dur = durs.max()

    curve_data, gosper_angles = _precompute_curves(curve_type, cfg["orders"])

    bins = _duration_bins(durs)
    bin_to_order = cfg["bin_to_order"]
    lw_map = cfg["lw_map"]
    base_size = cfg["base_size"]
    scale = cfg["size_scale"]

    # Tile side ∝ duration^0.75 — compresses the extreme outlier so the
    # largest tile doesn't dominate packing.  (Area still grows with duration.)
    min_size, max_size = 1.0 * scale, 7.0 * scale
    tile_sizes = min_size + (durs / max_dur) ** 0.75 * (max_size - min_size)

    # Adaptive sunflower layout
    golden_angle = np.pi * (3 - np.sqrt(5))
    tile_cx = np.empty(n_tiles)
    tile_cy = np.empty(n_tiles)
    cumul_area = 0.0
    k = cfg["dur_k"]
    for i in range(n_tiles):
        cumul_area += tile_sizes[i] ** 2
        r = k * np.sqrt(cumul_area)
        theta = i * golden_angle
        tile_cx[i] = r * np.cos(theta)
        tile_cy[i] = r * np.sin(theta)
    r_outer = k * np.sqrt(cumul_area) + tile_sizes[-1]

    _resolve_overlaps(tile_cx, tile_cy, tile_sizes, gap=0.0)

    tile_rots = np.zeros(n_tiles)

    figsize = (15, 15) if mobile else (30, 30)
    fig, ax = _create_dark_figure(figsize)
    draw_order = sorted(range(n_tiles), key=lambda i: durs[i])

    for idx in draw_order:
        size = tile_sizes[idx]
        cx, cy = tile_cx[idx], tile_cy[idx]
        rot = tile_rots[idx]
        bini = bins[idx]
        fill_color, line_color, base_lw = _tile_colors(bini)
        order = bin_to_order[bini]
        zorder = 1 + durs[idx] / max_dur
        lw = base_lw * (size / base_size)

        if curve_type == "hilbert":
            _draw_hilbert_tile(
                ax, *curve_data[order], size, cx, cy, rot,
                fill_color, line_color, lw, zorder)
        else:
            _draw_gosper_tile(
                ax, curve_data[order].copy(), gosper_angles[order],
                size, cx, cy, rot,
                fill_color, line_color, lw, zorder)

    pad = 2.0 if mobile else 3.5
    ax.set_xlim(-r_outer - pad, r_outer + pad)
    ax.set_ylim(-r_outer - pad, r_outer + pad)
    ax.set_aspect("equal")
    ax.axis("off")

    curve_label = "Hilbert" if curve_type == "hilbert" else "Gosper"
    ax.set_title(f"Playing in the Band — {curve_label} Duration Sunflower\n"
                 f"{n_tiles} performances  ·  "
                 f"tile area proportional to performance length",
                 fontsize=15, pad=14, color=LABEL_COLOR)

    if mobile:
        fig.subplots_adjust(top=0.88)
        _add_duration_legend(ax, durs, fontsize=11, ncol=3,
                             bbox_to_anchor=(0.5, 1.02))
        base = _CURVE_FILENAMES[("duration", curve_type)]
        fname = base.replace(".png", "_mobile.png")
        _save_plot(fig, fname, dpi=100)
    else:
        _add_duration_legend(ax, durs)
        fname = _CURVE_FILENAMES[("duration", curve_type)]
        _save_shareable(fig, fname)
        _save_plot(fig, fname, dpi=250)


def plot_hilbert_duration(conn):
    _plot_duration_sunflower(conn, curve_type="hilbert")


def plot_gosper_duration(conn):
    _plot_duration_sunflower(conn, curve_type="gosper")


def plot_gosper_duration_mobile(conn):
    _plot_duration_sunflower(conn, curve_type="gosper", mobile=True)


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

    # Count tiles per era for wedge allocation
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

    # Build per-tile angular constraints from era wedges
    wedge_mid = np.empty(n)
    wedge_half = np.empty(n)
    for i, (ei, _) in enumerate(assigned):
        es, ew = era_wedge[ei]
        wedge_mid[i] = es + ew / 2
        wedge_half[i] = ew / 2

    # Resolve overlaps with per-iteration angular clamping so tiles
    # can only spread radially, never across era boundaries.
    _resolve_overlaps(tile_cx, tile_cy, tile_sizes,
                      wedge_mid=wedge_mid, wedge_half=wedge_half,
                      tangential_damping=0.7)

    # Recalculate r_outer after tiles may have shifted outward
    max_r = np.sqrt(tile_cx ** 2 + tile_cy ** 2) + tile_sizes / 2
    r_outer = max_r.max()

    return tile_cx, tile_cy, tile_sizes, r_outer, era_boundaries


def _resolve_overlaps(tile_cx, tile_cy, tile_sizes,
                      gap=0.3, iterations=2000, tol=0.01,
                      wedge_mid=None, wedge_half=None,
                      tangential_damping=1.0):
    """Push overlapping tiles apart until no bounding boxes overlap.

    Uses vectorised pairwise repulsion: each overlapping pair generates
    equal-and-opposite forces proportional to the overlap depth.
    *gap* adds breathing room (in data units) between tile edges.

    When *wedge_mid* and *wedge_half* are provided, tiles are clamped to
    their angular wedge after every displacement step.  Overlaps can then
    only be resolved radially, keeping tiles within their sectors.

    *tangential_damping* (0–1) scales the tangential component of repulsive
    forces when wedge constraints are active.  Values < 1 bias overlap
    resolution toward radial spreading, reducing boundary oscillation.

    Modifies tile_cx, tile_cy in place.
    """
    min_sep = (tile_sizes[:, None] + tile_sizes[None, :]) / 2 + gap
    has_wedge = wedge_mid is not None

    for _ in range(iterations):
        dx = tile_cx[:, None] - tile_cx[None, :]
        dy = tile_cy[:, None] - tile_cy[None, :]
        dist = np.sqrt(dx ** 2 + dy ** 2)
        np.fill_diagonal(dist, np.inf)

        overlap = np.maximum(min_sep - dist, 0)
        max_ovl = overlap.max()
        if max_ovl < tol:
            break

        # Unit vectors from j toward i (push i away from j)
        safe_dist = np.maximum(dist, 1e-6)
        ux = dx / safe_dist
        uy = dy / safe_dist

        # Net repulsive force on each tile
        fx = np.sum(overlap * ux, axis=1)
        fy = np.sum(overlap * uy, axis=1)

        # Dampen tangential forces to bias overlap resolution radially
        if has_wedge and tangential_damping < 1.0:
            r_safe = np.maximum(np.sqrt(tile_cx**2 + tile_cy**2), 1e-6)
            ur_x = tile_cx / r_safe
            ur_y = tile_cy / r_safe
            f_radial = fx * ur_x + fy * ur_y           # radial projection
            ft_x = fx - f_radial * ur_x                # tangential remainder
            ft_y = fy - f_radial * ur_y
            fx = f_radial * ur_x + tangential_damping * ft_x
            fy = f_radial * ur_y + tangential_damping * ft_y

        # Adaptive step: scale so the largest displacement ≈ 40% of worst overlap
        fmax = max(np.abs(fx).max(), np.abs(fy).max(), 1e-6)
        step = 0.4 * max_ovl / fmax
        tile_cx += fx * step
        tile_cy += fy * step

        # Clamp angles to wedge boundaries, accounting for tile size so
        # the visual edge (not just center) stays inside the wedge.
        if has_wedge:
            theta = np.arctan2(tile_cy, tile_cx)
            theta = np.where(theta < wedge_mid - np.pi,
                             theta + 2 * np.pi, theta)
            delta = theta - wedge_mid
            r = np.sqrt(tile_cx ** 2 + tile_cy ** 2)
            # Shrink allowed range so tile's visual edge doesn't cross boundary
            margin = np.where(r > 1e-6, (tile_sizes / 2) / r, 0.0)
            effective_half = np.maximum(wedge_half - margin, 0.0)
            outside = np.abs(delta) > effective_half
            if outside.any():
                clamped = wedge_mid[outside] + np.clip(
                    delta[outside],
                    -effective_half[outside], effective_half[outside])
                tile_cx[outside] = r[outside] * np.cos(clamped)
                tile_cy[outside] = r[outside] * np.sin(clamped)


def _label_radius_at_angle(angle, tile_cx, tile_cy, tile_sizes, gap=5.0):
    """Minimum radius so a point at *angle* clears every tile by *gap*.

    Uses the exact quadratic solution: for a tile at polar (r_i, θ_i)
    with clearance c_i = size_i/2 + gap, the label at radius R along
    angle θ satisfies  dist² = R² + r_i² − 2 R r_i cos(Δθ) ≥ c_i².
    Rearranging gives R ≥ r_i cos(Δθ) + √(c_i² − r_i² sin²(Δθ))
    for tiles where the discriminant is non-negative (tiles angularly
    close enough to matter).
    """
    clearance = tile_sizes / 2 + gap
    tile_r = np.sqrt(tile_cx ** 2 + tile_cy ** 2)
    sin_dt = np.sin(angle - np.arctan2(tile_cy, tile_cx))
    cos_dt = np.cos(angle - np.arctan2(tile_cy, tile_cx))

    disc = clearance ** 2 - (tile_r * sin_dt) ** 2
    mask = disc >= 0
    if not mask.any():
        return gap
    return max(float((tile_r[mask] * cos_dt[mask]
                       + np.sqrt(disc[mask])).max()), gap)


def _draw_era_spokes_and_labels(ax, era_boundaries, r_outer,
                                tile_cx, tile_cy, tile_sizes, pad=3.5):
    """Draw radial spokes and era labels just outside the tiles.

    Each label is placed near the upper (start) spoke of its wedge,
    at the minimum radius that clears all tile bounding boxes by a
    comfortable margin.
    """
    r_spoke = r_outer + pad * 0.3

    for start, end, name, _, y0, y1 in era_boundaries:
        # Spoke at start of each wedge
        ax.plot([0, r_spoke * np.cos(start)],
                [0, r_spoke * np.sin(start)],
                color="#555577", linewidth=3.0, alpha=0.7, zorder=0.5)

        # Place label near the visually higher spoke (larger y = sin).
        # Wedges go counter-clockwise from -π/2 (bottom), so "start" is
        # NOT always the upper boundary — depends on where the wedge sits.
        bias = 0.15
        if np.sin(start) >= np.sin(end):
            label_angle = start + bias * (end - start)
        else:
            label_angle = end - bias * (end - start)
        label_r = _label_radius_at_angle(
            label_angle, tile_cx, tile_cy, tile_sizes, gap=5.0)
        lx = label_r * np.cos(label_angle)
        ly = label_r * np.sin(label_angle)

        year_str = f"{y0}–{y1}" if y0 != y1 else str(y0)
        label = f"{name}\n{year_str}"
        ax.text(lx, ly, label, color=LABEL_COLOR, fontsize=14, fontweight="bold",
                ha="center", va="center", rotation=0,
                alpha=0.85, zorder=10,
                bbox=dict(boxstyle="round,pad=0.2", facecolor=DARK_BG,
                          edgecolor="none", alpha=0.7))



# ══════════════════════════════════════════════════════════════════════════
# 8-9. Duration Era Sunflower — Playing in the Band
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
        choices = np.arange(6) * (np.pi / 3)
        return rng.choice(choices, n_tiles)
    elif mode == "hex3":
        choices = np.arange(3) * (2 * np.pi / 3)
        return rng.choice(choices, n_tiles)
    else:  # "random"
        return rng.uniform(0, 2 * np.pi, n_tiles)


def _plot_duration_era(conn, curve_type="hilbert",
                       rotation_mode="aligned", suffix="", mobile=False):
    """Era-segmented sunflower, duration-sorted within each wedge.

    curve_type: "hilbert" | "gosper"
    rotation_mode: "random" | "aligned" | "hex6" | "hex3" (Gosper only)
    suffix: appended to Gosper filename, e.g. "_aligned"
    mobile: if True, render a compact 1500×1500 version (no title, tight pad)
    """
    cfg = _CURVE_CONFIGS[curve_type]
    rows = _query_pitb_with_month(conn)

    assigned = _assign_eras(rows)
    assigned.sort(key=lambda x: (x[0], x[1]["dur_min"]))

    durs = np.array([r["dur_min"] for (_, r) in assigned])
    n_tiles = len(assigned)
    max_dur = durs.max()

    curve_data, gosper_angles = _precompute_curves(curve_type, cfg["orders"])

    bins = _duration_bins(durs)
    bin_to_order = cfg["bin_to_order"]
    lw_map = cfg["lw_map"]
    base_size = cfg["base_size"]
    scale = cfg["size_scale"]

    # Tile side ∝ duration^0.75 — matches sunflower plots
    min_size, max_size = 1.0 * scale, 7.0 * scale
    tile_sizes_pre = min_size + (durs / max_dur) ** 0.75 * (max_size - min_size)

    tile_cx, tile_cy, tile_sizes, r_outer, era_boundaries = _era_wedge_layout(
        assigned, tile_sizes_pre, k=cfg["era_k"],
        era_k_scales={1: 0.82, 3: 0.92})

    # Tile rotations
    if curve_type == "gosper":
        rng = np.random.default_rng(42)
        tile_rots = _gosper_tile_rotations(n_tiles, rotation_mode, rng)
    else:
        tile_rots = np.zeros(n_tiles)

    figsize = (15, 15) if mobile else (30, 30)
    fig, ax = _create_dark_figure(figsize)

    _draw_era_spokes_and_labels(ax, era_boundaries, r_outer,
                                tile_cx, tile_cy, tile_sizes)

    draw_order = sorted(range(n_tiles), key=lambda i: durs[i])

    for idx in draw_order:
        size = tile_sizes[idx]
        cx, cy = tile_cx[idx], tile_cy[idx]
        rot = tile_rots[idx]
        bini = bins[idx]
        fill_color, line_color, base_lw = _tile_colors(bini)
        order = bin_to_order[bini]
        zorder = 1 + durs[idx] / max_dur
        lw = base_lw * (size / base_size)

        if curve_type == "hilbert":
            _draw_hilbert_tile(
                ax, *curve_data[order], size, cx, cy, rot,
                fill_color, line_color, lw, zorder)
        else:
            _draw_gosper_tile(
                ax, curve_data[order].copy(), gosper_angles[order],
                size, cx, cy, rot,
                fill_color, line_color, lw, zorder)

    pad = 2.0 if mobile else 3.5
    shift = r_outer * 0.22
    ax.set_xlim(-r_outer - pad + shift, r_outer + pad + shift)
    ax.set_ylim(-r_outer - pad, r_outer + pad)
    ax.set_aspect("equal")
    ax.axis("off")

    curve_label = "Hilbert" if curve_type == "hilbert" else "Gosper"
    subtitle = (f"{n_tiles} performances  ·  "
                f"tile area proportional to performance length")
    ax.set_title(f"Playing in the Band — {curve_label} Duration Sunflower by Era\n"
                 f"{subtitle}",
                 fontsize=15, pad=14, color=LABEL_COLOR)

    # Duration legend
    if mobile:
        fig.subplots_adjust(top=0.88)
        _add_duration_legend(ax, durs, fontsize=11, ncol=3,
                             bbox_to_anchor=(0.5, 1.02))
    else:
        _add_duration_legend(ax, durs, bbox_to_anchor=(0.5, 1.0))

    if mobile:
        base = _CURVE_FILENAMES.get(("duration_era", curve_type),
                                     f"09_gosper_duration_era{suffix}.png")
        fname = base.replace(".png", "_mobile.png")
        _save_plot(fig, fname, dpi=100)
    elif curve_type == "hilbert":
        fname = _CURVE_FILENAMES[("duration_era", "hilbert")]
        _save_shareable(fig, fname)
        _save_plot(fig, fname, dpi=250)
    else:
        fname = f"09_gosper_duration_era{suffix}.png"
        _save_shareable(fig, fname)
        _save_plot(fig, fname, dpi=250)


def plot_hilbert_duration_era(conn):
    _plot_duration_era(conn, curve_type="hilbert")


def plot_gosper_duration_era(conn, rotation_mode="aligned", suffix=""):
    _plot_duration_era(conn, curve_type="gosper",
                       rotation_mode=rotation_mode, suffix=suffix)


def plot_gosper_duration_era_mobile(conn, rotation_mode="aligned", suffix=""):
    _plot_duration_era(conn, curve_type="gosper",
                       rotation_mode=rotation_mode, suffix=suffix, mobile=True)


# ══════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════
def main(tile_mode=None):
    global TILE_MODE
    if tile_mode is not None:
        TILE_MODE = tile_mode
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
    plot_gosper_duration_mobile(conn)
    plot_hilbert_duration_era(conn)
    plot_gosper_duration_era(conn)
    plot_gosper_duration_era_mobile(conn)
    conn.close()
    print(f"Done — 11 plots saved to {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
