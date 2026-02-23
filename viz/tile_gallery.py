"""Tile Design Gallery — grid of fill-shape × curve-type × style variations.

Renders a comparison grid so the user can evaluate tile designs before
modifying the actual sunflower/strip plot code.

Usage:
    uv run --extra viz python -m viz.tile_gallery
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

from viz.curves import smooth_hilbert, gosper_points, chaikin_smooth, BIN_COLORS

OUTPUT_DIR = Path(__file__).parent / "output"


# ── Curve generation helpers ─────────────────────────────────────────────

def _make_hilbert(order):
    """Return (xs, ys) normalized to [0, 1] for a smoothed Hilbert curve."""
    return smooth_hilbert(order, iterations=2)


def _make_gosper(order):
    """Return (xs, ys) normalized to [0, 1] for a smoothed Gosper curve."""
    raw = gosper_points(order)
    mid = (raw[0] + raw[-1]) / 2
    centered = raw - mid
    extent = max(centered[:, 0].max() - centered[:, 0].min(),
                 centered[:, 1].max() - centered[:, 1].min())
    if extent > 0:
        centered /= extent
    # Shift to [0, 1] range
    xs = centered[:, 0] + 0.5
    ys = centered[:, 1] + 0.5
    xs, ys = chaikin_smooth(xs, ys, iterations=2)
    return xs, ys


# ── Fill shape patches ───────────────────────────────────────────────────

def _circle_patch(cx, cy, size, **kwargs):
    return mpatches.Circle((cx, cy), radius=size / 2, **kwargs)


def _rounded_square_patch(cx, cy, size, **kwargs):
    pad = size * 0.12
    return mpatches.FancyBboxPatch(
        (cx - size / 2, cy - size / 2), size, size,
        boxstyle=f"round,pad=0,rounding_size={pad}",
        **kwargs,
    )


def _hexagon_patch(cx, cy, size, **kwargs):
    return mpatches.RegularPolygon((cx, cy), numVertices=6, radius=size / 2, **kwargs)


def _convex_hull_patch(curve_xs, curve_ys, **kwargs):
    from scipy.spatial import ConvexHull  # type: ignore[import-untyped]
    pts = np.column_stack([curve_xs, curve_ys])
    hull = ConvexHull(pts)
    hull_pts = pts[hull.vertices]
    return mpatches.Polygon(hull_pts, closed=True, **kwargs)


FILL_SHAPES = ["circle", "rounded_sq", "hexagon", "hull"]
CURVE_TYPES = ["hilbert", "gosper"]

SHAPE_BUILDERS = {
    "circle": _circle_patch,
    "rounded_sq": _rounded_square_patch,
    "hexagon": _hexagon_patch,
    "hull": _convex_hull_patch,
}


# ── Tile renderer ────────────────────────────────────────────────────────

def _render_tile(ax, cx, cy, size, curve_xs, curve_ys,
                 fill_shape, fill_color, line_color, line_width,
                 alpha=1.0, edge_color="none", edge_width=0):
    """Draw one tile: optional fill shape + curve line on top."""
    margin = 0.06 * size
    span = size - 2 * margin
    xs = cx - size / 2 + margin + curve_xs * span
    ys = cy - size / 2 + margin + curve_ys * span

    # Draw fill patch
    if fill_color is not None:
        if fill_shape == "hull":
            patch = _convex_hull_patch(xs, ys,
                                       facecolor=fill_color, edgecolor=edge_color,
                                       linewidth=edge_width, alpha=alpha, zorder=1)
        else:
            builder = SHAPE_BUILDERS[fill_shape]
            patch = builder(cx, cy, size,
                            facecolor=fill_color, edgecolor=edge_color,
                            linewidth=edge_width, alpha=alpha, zorder=1)
        ax.add_patch(patch)

    # Draw curve line
    ax.plot(xs, ys, color=line_color, linewidth=line_width,
            solid_capstyle="round", zorder=2)


# ── Row variation definitions ────────────────────────────────────────────

def _darken(hex_color, factor=0.3):
    """Blend hex_color toward black.  factor=0 → black, factor=1 → original."""
    from matplotlib.colors import to_rgb
    r, g, b = to_rgb(hex_color)
    return (r * factor, g * factor, b * factor)


# Each row returns (fill_color, line_color, lw_scale, alpha, edge_color, edge_width, label)
ROW_SPECS = [
    {
        "label": "Black line on colored fill",
        "fill": lambda c: c,
        "line": lambda _c: "black",
        "lw_scale": 1.0,
        "alpha": 0.9,
        "edge": lambda _c: "none",
        "edge_w": 0,
    },
    {
        "label": "Black line, thicker (1.5×)",
        "fill": lambda c: c,
        "line": lambda _c: "black",
        "lw_scale": 1.5,
        "alpha": 0.9,
        "edge": lambda _c: "none",
        "edge_w": 0,
    },
    {
        "label": "Black line, thinner (0.6×)",
        "fill": lambda c: c,
        "line": lambda _c: "black",
        "lw_scale": 0.6,
        "alpha": 0.9,
        "edge": lambda _c: "none",
        "edge_w": 0,
    },
    {
        "label": "Dark fill + colored line",
        "fill": lambda c: _darken(c, 0.3),
        "line": lambda c: c,
        "lw_scale": 1.0,
        "alpha": 0.95,
        "edge": lambda _c: "none",
        "edge_w": 0,
    },
    {
        "label": "White line on colored fill",
        "fill": lambda c: c,
        "line": lambda _c: "white",
        "lw_scale": 1.0,
        "alpha": 0.9,
        "edge": lambda _c: "none",
        "edge_w": 0,
    },
    {
        "label": "Outline only + colored line",
        "fill": lambda _c: "none",
        "line": lambda c: c,
        "lw_scale": 1.0,
        "alpha": 1.0,
        "edge": lambda c: c,
        "edge_w": 1.5,
    },
]


# ── Pre-compute curves ──────────────────────────────────────────────────

def _precompute_curves():
    """Build a dict of (curve_type, size_label) → (xs, ys, base_lw)."""
    curves = {}
    # Large tiles
    curves[("hilbert", "large")] = (*_make_hilbert(5), 0.5)
    curves[("hilbert", "small")] = (*_make_hilbert(2), 1.2)
    # Gosper
    curves[("gosper", "large")] = (*_make_gosper(4), 0.4)
    curves[("gosper", "small")] = (*_make_gosper(1), 1.4)
    return curves


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    n_rows = len(ROW_SPECS)
    n_cols = len(FILL_SHAPES) * len(CURVE_TYPES)  # 4 × 2 = 8

    curves = _precompute_curves()

    # Two representative bin colors: gold (Epic, index 1) and lavender (Short, index 4)
    colors_for_size = {"large": BIN_COLORS[1], "small": BIN_COLORS[4]}

    # Each cell shows two tiles side-by-side (large + small)
    cell_w, cell_h = 3.0, 2.6
    fig_w = n_cols * cell_w + 2.0  # extra for row labels
    fig_h = n_rows * cell_h + 2.0  # extra for column headers

    fig, axes = plt.subplots(n_rows, n_cols,
                             figsize=(fig_w, fig_h),
                             squeeze=False)
    fig.set_facecolor("#1a1a2e")

    # Column headers
    col_headers = []
    for shape in FILL_SHAPES:
        for ctype in CURVE_TYPES:
            nice_shape = {"circle": "Circle", "rounded_sq": "Rounded Sq",
                          "hexagon": "Hexagon", "hull": "Convex Hull"}[shape]
            nice_curve = ctype.capitalize()
            col_headers.append(f"{nice_shape}\n{nice_curve}")

    for col_idx, header in enumerate(col_headers):
        axes[0, col_idx].set_title(header, fontsize=9, color="white",
                                   fontweight="bold", pad=8)

    tile_large = 1.5
    tile_small = 0.8

    for row_idx, spec in enumerate(ROW_SPECS):
        for col_idx, (shape, ctype) in enumerate(
            [(s, c) for s in FILL_SHAPES for c in CURVE_TYPES]
        ):
            ax = axes[row_idx, col_idx]
            ax.set_facecolor("#1a1a2e")
            ax.set_xlim(-0.2, 3.2)
            ax.set_ylim(-0.3, 2.3)
            ax.set_aspect("equal")
            ax.axis("off")

            # Large tile (left)
            lg_cx, lg_cy = 0.9, 1.0
            lg_xs, lg_ys, lg_base_lw = curves[(ctype, "large")]
            lg_color = colors_for_size["large"]
            _render_tile(
                ax, lg_cx, lg_cy, tile_large, lg_xs, lg_ys,
                fill_shape=shape,
                fill_color=spec["fill"](lg_color),
                line_color=spec["line"](lg_color),
                line_width=lg_base_lw * spec["lw_scale"],
                alpha=spec["alpha"],
                edge_color=spec["edge"](lg_color),
                edge_width=spec["edge_w"],
            )

            # Small tile (right)
            sm_cx, sm_cy = 2.3, 1.0
            sm_xs, sm_ys, sm_base_lw = curves[(ctype, "small")]
            sm_color = colors_for_size["small"]
            _render_tile(
                ax, sm_cx, sm_cy, tile_small, sm_xs, sm_ys,
                fill_shape=shape,
                fill_color=spec["fill"](sm_color),
                line_color=spec["line"](sm_color),
                line_width=sm_base_lw * spec["lw_scale"],
                alpha=spec["alpha"],
                edge_color=spec["edge"](sm_color),
                edge_width=spec["edge_w"],
            )

        # Row label on the left
        axes[row_idx, 0].text(
            -0.35, 1.0, spec["label"],
            transform=axes[row_idx, 0].transData,
            fontsize=8, color="white", va="center", ha="right",
            fontweight="bold",
        )

    fig.suptitle("Tile Design Gallery", fontsize=18, color="white",
                 fontweight="bold", y=0.98)
    fig.tight_layout(rect=[0.08, 0.01, 1.0, 0.95])
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / "tile_gallery.png"
    fig.savefig(out_path, dpi=200, facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"  {out_path}")


if __name__ == "__main__":
    main()
