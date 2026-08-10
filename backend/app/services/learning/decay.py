from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.learning import StrategyStat
from app.services.learning.outcome_recorder import TerminalOutcome


async def detect_strategy_decay(session: AsyncSession, terminal: TerminalOutcome) -> bool:
    settings = get_settings()
    stmt = select(StrategyStat).where(
        StrategyStat.workspace_id == terminal.workspace_id,
        StrategyStat.strategy_code == terminal.strategy_code,
        StrategyStat.setup_type == terminal.setup_type,
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
