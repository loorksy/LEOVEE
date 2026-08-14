from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.learning import StrategyStat
from app.services.learning.outcome_recorder import TerminalOutcome


async def detect_strategy_decay(session: AsyncSession, terminal: TerminalOutcome) -> bool:
    settings = get_settings()
    # All six columns of the unique key, not three of them.
    #
    # The narrower filter matched every sibling bucket of the same strategy and
    # `scalar()` returned whichever row the plan happened to visit first — so a
    # London outcome could suspend the Asian bucket and leave its own untouched,
    # and `hist_avg_r` was written into whichever sibling was returned. It is
    # the same key `update_strategy_stats` writes under, which is the point:
    # decay has to read the row the outcome just moved.
    stmt = select(StrategyStat).where(
        StrategyStat.workspace_id == terminal.workspace_id,
        StrategyStat.strategy_code == terminal.strategy_code,
        StrategyStat.setup_type == terminal.setup_type,
        StrategyStat.regime_bucket == terminal.regime_bucket,
        StrategyStat.session_bucket == terminal.session_bucket,
        StrategyStat.volatility_bucket == terminal.volatility_bucket,
    )
    stat = await session.scalar(stmt)
    if stat is None or stat.occurrences < settings.strategy_decay_min_trades:
        return False

    hist = stat.metadata_json.get("hist_avg_r")
    if hist is None:
        stat.metadata_json = {**stat.metadata_json, "hist_avg_r": str(stat.avg_r)}
        return False

    hist_avg = Decimal(str(hist))
    if abs(stat.avg_r - hist_avg) > Decimal(str(settings.strategy_decay_threshold_avg_r)):
        stat.suspended = True
        return True
    return False
