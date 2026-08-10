from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.learning import CalibrationBin
from app.services.learning.outcome_recorder import TerminalOutcome

N_PRIOR = Decimal("20")
P_PRIOR = Decimal("0.5")


def _bin_for_confidence(confidence: Decimal) -> tuple[Decimal, Decimal]:
    step = Decimal("0.1")
    lower = (confidence // step) * step
    upper = lower + step
    if upper > Decimal("1"):
        upper = Decimal("1")
    return lower, upper


async def update_calibration_bins(session: AsyncSession, terminal: TerminalOutcome) -> None:
    if terminal.confidence_stated is None:
        return
    lower, upper = _bin_for_confidence(terminal.confidence_stated)
    row = await session.scalar(
        select(CalibrationBin).where(
            CalibrationBin.workspace_id == terminal.workspace_id,
            CalibrationBin.bin_lower == lower,
            CalibrationBin.bin_upper == upper,
        )
    )
    if row is None:
        row = CalibrationBin(
            tenant_id=terminal.tenant_id,
            workspace_id=terminal.workspace_id,
            strategy_code=terminal.strategy_code,
            bin_lower=lower,
            bin_upper=upper,
        )
        session.add(row)
        await session.flush()
    row.predicted_count += 1
    if terminal.success:
        row.realized_success_count += 1


def apply_calibration(
    stated: Decimal,
    *,
    predicted_count: int,
    realized_success_count: int,
) -> Decimal:
    if predicted_count <= 0:
        return stated
    accuracy = Decimal(realized_success_count) / Decimal(predicted_count)
    n = Decimal(predicted_count)
    return (n * accuracy + N_PRIOR * P_PRIOR) / (n + N_PRIOR)
