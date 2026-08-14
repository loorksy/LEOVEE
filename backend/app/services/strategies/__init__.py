"""Strategy statistics: what past outcomes say about the setup in front of us.

Under D7 there is no backtest. Every number here comes from recommendations
that actually closed, which makes the sample small, slow-growing and honest —
and makes saying so correctly the most important thing this package does.
"""

from app.services.strategies.calibration import (
    MIN_TRADES_FOR_CALIBRATION,
    WinRateCalibration,
    calibrate_win_rate,
    wilson_score_interval,
)

__all__ = [
    "MIN_TRADES_FOR_CALIBRATION",
    "WinRateCalibration",
    "calibrate_win_rate",
    "wilson_score_interval",
]
