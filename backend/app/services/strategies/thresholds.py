"""Every governance constant the package reads, and nothing else.

A leaf module on purpose. In the reference implementation these numbers lived
next to the database layer, so importing a threshold dragged a driver into the
browser bundle. The Python version has no such build problem, but it keeps the
same shape for a better reason: **changing one of these is a decision, not a
refactor**, and a file with no imports is a file whose whole diff is the
decision.
"""

from __future__ import annotations

__all__ = [
    "MIN_OUTCOMES_FOR_SUPPORT",
    "MIN_OUTCOMES_FOR_BOOTSTRAP",
    "STRONG_INTERVAL_WIDTH",
    "MODERATE_INTERVAL_WIDTH",
    "DECAY_WINDOW",
    "MAX_WIN_RATE_DECAY",
]

#: Closed outcomes before a bucket may claim statistical support at all.
#:
#: Below it the recommendation still goes out — with a direction, a full plan and
#: an honest confidence — carrying a label that says the record is provisional.
#: Withholding the analysis until the record exists would mean the platform is
#: silent for as long as it takes to accumulate one, which is not caution, it is
#: not shipping.
MIN_OUTCOMES_FOR_SUPPORT = 20

#: Where a resample stops being degenerate and the interval switches from Wilson
#: to bootstrap. See `calibration.py` — at tiny n a bootstrap reports certainty.
MIN_OUTCOMES_FOR_BOOTSTRAP = 30

#: Confidence-interval widths, as fractions. A wide interval on a high midpoint
#: is weak evidence however good the midpoint looks, so the *width* grades the
#: support and the midpoint never does.
STRONG_INTERVAL_WIDTH = 0.20
MODERATE_INTERVAL_WIDTH = 0.30

#: How many recent outcomes decay is judged over, against the preceding same-size
#: window. A rolling comparison, not a comparison against an all-time average
#: captured once and kept forever.
DECAY_WINDOW = 30

#: Win-rate drop, in absolute terms, that marks an edge as decaying.
MAX_WIN_RATE_DECAY = 0.15
