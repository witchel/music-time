"""Space-filling curve primitives (Hilbert & Gosper) and duration-bin palette.

Extracted from viz/examples.py to allow reuse across visualization modules.
"""

import numpy as np


# ── Duration-bin color palette (jewel tones on dark background) ───────
BIN_COLORS = ["#FFFFFF", "#FFD700", "#FF6B6B", "#4ECDC4", "#A78BFA"]
#              white     gold       coral      teal       lavender
BIN_LABELS = ["Gigantous (25+ min)", "Epic jams", "Extended", "Standard", "Short"]


# ── Hilbert curve helpers ─────────────────────────────────────────────

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


def hilbert_points(order):
    """Return list of (x, y) points for a Hilbert curve of given order."""
    n = 2 ** order
    return [_d2xy(n, d) for d in range(n * n)]


def chaikin_smooth(xs, ys, iterations=2):
    """Round corners of a polyline using Chaikin's corner-cutting algorithm.

    Each iteration replaces every segment with two points at 25 % and 75 %,
    progressively turning sharp turns into smooth arcs.  Two iterations are
    enough to make a Hilbert curve look organic rather than grid-like.
    """
    pts = np.column_stack([xs, ys])
    for _ in range(iterations):
        q = 0.75 * pts[:-1] + 0.25 * pts[1:]   # 25 % along each segment
        r = 0.25 * pts[:-1] + 0.75 * pts[1:]   # 75 % along each segment
        new_pts = np.empty((2 * len(q), 2))
        new_pts[0::2] = q
        new_pts[1::2] = r
        pts = new_pts
    return pts[:, 0], pts[:, 1]


def smooth_hilbert(order, iterations=2):
    """Return a smoothed Hilbert curve normalized to [0, 1].

    The raw integer-grid Hilbert points are normalized, then Chaikin-smoothed.
    Returns (xs, ys) ready for ``local = margin + arr * span``.
    """
    raw = hilbert_points(order)
    grid_n = 2 ** order
    denom = max(grid_n - 1, 1)
    xs = np.array([p[0] / denom for p in raw])
    ys = np.array([p[1] / denom for p in raw])
    return chaikin_smooth(xs, ys, iterations)


# ── Gosper curve helpers ──────────────────────────────────────────────

def gosper_points(order):
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


def precompute_gosper(orders):
    """Pre-compute normalized Gosper curves and intrinsic angles.

    Returns (gosper_norm, gosper_angle) dicts keyed by order.
    """
    gosper_norm = {}
    gosper_angle = {}
    for order in orders:
        raw = gosper_points(order)
        delta = raw[-1] - raw[0]
        gosper_angle[order] = np.arctan2(delta[1], delta[0])
        mid = (raw[0] + raw[-1]) / 2
        centered = raw - mid
        extent = max(centered[:, 0].max() - centered[:, 0].min(),
                     centered[:, 1].max() - centered[:, 1].min())
        if extent > 0:
            centered /= extent
        gosper_norm[order] = centered
    return gosper_norm, gosper_angle
