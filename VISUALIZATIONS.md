# Visualization Ideas

Design goal: use **two spatial dimensions plus color** to represent how song
performances evolve over time. Visualizations should be band-agnostic, working
from a SQLite database with a common schema (songs, releases, tracks tables
with columns like song name, date, duration, venue/city/state, set position,
etc.).

Code will live in a top-level `viz/` module, separate from band-specific
scraping packages like `gdtimings/`. The `viz/` module reads directly from the
SQLite database rather than CSV exports.

---

## 1. Streamgraph (River / Stream Plot)

- **X**: time
- **Y**: stacked duration contributions per song (streamgraph)
- **Color**: song identity
- Shows how total show time was allocated across songs over the years.
  Normalized to % of recorded time to remove Archive.org data-availability
  bias.

## 2. Hilbert Sunflower

- Golden-angle spiral of Hilbert-curve tiles for Playing in the Band.
- **Tile area**: ∝ performance duration.
- **Curve complexity** (order 2–5): ∝ duration.
- **Color**: duration (YlOrRd, power-law normalized).

## 3. Gosper Sunflower

- Same sunflower layout as #2, but using Gosper (flowsnake) curves.
- Gosper tiles scaled up ~30% to compensate for lower fill density.
- Tiles oriented radially outward from center.

## 4. Hilbert Year Strips

- Dense year-strip layout: one horizontal strip per year.
- Tiles placed center-out — longest jams at the center of each strip.
- Hilbert curves at orders 2–5 based on duration.
- Hiatus gap between 1974 and 1976.

## 5. Gosper Year Strips

- Same strip layout as #4, but using Gosper curves at orders 1–4.
- Gosper density compensation (1.3× size scaling).
