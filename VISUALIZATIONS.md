# Visualization Ideas

Design goal: use **two spatial dimensions plus color** to represent how song
performances evolve over time. Visualizations should be band-agnostic, working
from generic columns (song name, date, duration, venue/city/state, set
position, etc.) like the CSV export already provides.

Code will live in a top-level `viz/` module, separate from band-specific
scraping packages like `gdtimings/`.

---

## 1. Terrain Map / Topographic Song Profile

- **X**: date (year or chronological show number)
- **Y**: duration of that performance
- Render each performance as a vertical strip; fill the area under the curve
  like a mountain silhouette.
- **Color**: geographic region (e.g., West Coast = warm, East Coast = cool,
  Midwest = green). Reveals whether songs stretched out more in certain
  regions.

## 2. Heatmap Grid: Year x Song

- **X**: year
- **Y**: songs (ordered by first-played date or median duration)
- **Cell color**: mean duration that year
- **Cell size or opacity**: number of performances that year
- Bird's-eye view of the entire repertoire evolving. The jamming era would
  appear as a warm bloom that expands and contracts.

## 3. Radial / Polar Timeline

- **Angle**: date (one rotation = one year, or the whole career spiraling out)
- **Radius**: duration
- **Color**: set position (Set 1, Set 2, Encore)
- Each song gets its own polar plot. A consistent 5-minute song is a tight
  circle; a jam vehicle is an exploding star. Set-position coloring shows
  whether longer versions migrated to Set 2 over time.

## 4. River / Stream Plot (Stacked Areas)

- **X**: time
- **Y**: stacked duration contributions per song (streamgraph)
- **Color**: song identity
- Shows how total show time was allocated across songs over the years.
  "Drums/Space" grows as a wide band in the late 70s, "Dark Star" shrinks
  in the 80s, etc.

## 5. Geographic Heatmap

- **X, Y**: US map coordinates (lat/long from city/state)
- **Color**: mean duration of a song at that venue/city
- **Dot size**: number of times played there
- Literally see where songs stretched out. A landscape of jamming intensity.

## 6. Small Multiples / Tile Grid of Song "Shapes"

- Each song gets a small tile (sparkline-style).
- Within each tile: X = year, Y = duration, area filled.
- **Tile border/background color**: aggregate property like standard deviation
  (high variance = vibrant, consistent = muted) or song category (ballad,
  jam vehicle, cover).
- Arranged in a grid, this becomes a periodic table of songs where tile shape
  tells each song's temporal story at a glance.

## 7. Duration x Variability Scatterplot (Animated)

- **X**: median duration of a song in a given year
- **Y**: standard deviation of duration (show-to-show variability)
- **Color**: year (gradient from cool 60s to warm 90s)
- **Dot size**: number of performances
- Animated over time, songs migrate across the space -- starting tight and
  short, expanding into "long and unpredictable," then collapsing back.

## 8. Duration Envelope with Derivative Coloring

- **X**: time (each column is a year or show)
- **Y**: proportional to duration (filled silhouette)
- **Color of fill**: rate of change. Blue = shrinking, red = growing,
  white = stable. Or color by set position or geographic region.
- The shape gives the duration envelope; the color gives context about the
  direction and speed of change.

---

## Combinations

These ideas can be mixed. For example:
- Terrain silhouettes (#1) arranged as small multiples (#6) with geographic
  coloring (#5).
- Heatmap grid (#2) with cells clickable to reveal a polar plot (#3).
- Streamgraph (#4) where clicking a band opens an animated scatterplot (#7).
