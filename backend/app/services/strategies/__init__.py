"""Strategy statistics: what past outcomes say about the setup in front of us.

Under D7 there is no simulated history. Every number here comes from
recommendations that actually closed, which makes the sample small, slow-growing
and honest — and makes saying so correctly the most important thing this package
does.
"""

from app.services.strategies.calibration import (
    MIN_TRADES_FOR_CALIBRATION,
    WinRateCalibration,
    calibrate_win_rate,
    wilson_score_interval,
)
from app.services.strategies.matching_keys import (
    ANY,
    UNKNOWN,
    Classification,
    classification_from_evidence,
    classify,
    read_ladder,
)
from app.services.strategies.support import (
    StatisticalSupport,
    SupportLevel,
    SupportReason,
    assess_support,
)

__all__ = [
    "ANY",
    "MIN_TRADES_FOR_CALIBRATION",
    "UNKNOWN",
    "Classification",
    "StatisticalSupport",
    "SupportLevel",
    "SupportReason",
    "WinRateCalibration",
    "assess_support",
    "calibrate_win_rate",
    "classification_from_evidence",
    "classify",
    "read_ladder",
    "wilson_score_interval",
]
