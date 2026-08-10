from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.learning import StrategyStat
from app.services.learning.outcome_recorder import TerminalOutcome


async def update_strategy_stats(session: AsyncSession, terminal: TerminalOutcome) -> StrategyStat:
    stmt = select(StrategyStat).where(
        StrategyStat.workspace_id == terminal.workspace_id,
        StrategyStat.strategy_code == terminal.strategy_code,
        StrategyStat.setup_type == terminal.setup_type,
        StrategyStat.regime_bucket == terminal.regime_bucket,
        StrategyStat.session_bucket == terminal.session_bucket,
        StrategyStat.volatility_bucket == terminal.volatility_bucket,
    )
    stat = await session.scalar(stmt)
    if stat is None:
        stat = StrategyStat(
            tenant_id=terminal.tenant_id,
            workspace_id=terminal.workspace_id,
            symbol_id=terminal.symbol_id,
            strategy_code=terminal.strategy_code,
            setup_type=terminal.setup_type,
            regime_bucket=terminal.regime_bucket,
            session_bucket=terminal.session_bucket,
            volatility_bucket=terminal.volatility_bucket,
        )
        session.add(stat)
        await session.flush()

    stat.occurrences += 1
    if terminal.success:
        stat.wins += 1
    if terminal.r_multiple is not None:
        prev_total = stat.avg_r * Decimal(stat.occurrences - 1)
        stat.avg_r = (prev_total + terminal.r_multiple) / Decimal(stat.occurrences)
    return stat


async def update_symbol_profile(
    session: AsyncSession,
    terminal: TerminalOutcome,
) -> None:
    if terminal.symbol_id is None:
        return
    from app.models.learning import SymbolProfile

    profile = await session.scalar(
        select(SymbolProfile).where(
            SymbolProfile.workspace_id == terminal.workspace_id,
            SymbolProfile.symbol_id == terminal.symbol_id,
        )
    )
    if profile is None:
        profile = SymbolProfile(
            tenant_id=terminal.tenant_id,
            workspace_id=terminal.workspace_id,
            symbol_id=terminal.symbol_id,
            profile_json={},
            sample_size=0,
        )
        session.add(profile)
        await session.flush()

    profile.sample_size += 1
    outcomes = profile.profile_json.get("outcomes", [])
    outcomes.append(
        {
            "outcome": terminal.outcome,
            "r_multiple": str(terminal.r_multiple) if terminal.r_multiple is not None else None,
            "session": terminal.session_bucket,
            "regime": terminal.regime_bucket,
        }
    )
    profile.profile_json = {**profile.profile_json, "outcomes": outcomes[-100:]}
