"""Song statistics for Phish.

Reuses compute_song_stats and print_song_summary from gdtimings.analyze.
Skips classify_song_types (no utility songs) and detect_sandwiches
(no Drums/Space pattern in Phish).
"""

from gdtimings.analyze import compute_song_stats, print_song_summary

__all__ = ["compute_song_stats", "print_song_summary"]
