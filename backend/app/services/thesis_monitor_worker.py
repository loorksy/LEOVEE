from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import TenantContext, resolve_tenant_context
from app.infrastructure.rls import set_rls_session_context
from app.models.symbol import Symbol
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.services.thesis_monitor_service import list_active_theses, monitor_thesis_row


async def _context_for_workspace(session: AsyncSession, workspace: Workspace) -> TenantContext:
    member = await session.scalar(
        select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace.id).limit(1)
    )
    if member is None:
        raise RuntimeError(f"No workspace member for workspace {workspace.id}")
    return await resolve_tenant_context(session, member.user_id)


async def run_thesis_monitor_cycle(
    session: AsyncSession,
    *,
    price_by_symbol: dict[str, Decimal] | None = None,
    structure_by_symbol: dict[str, dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    prices = price_by_symbol or {}
    structures = structure_by_symbol or {}
    outcomes: list[dict[str, object]] = []

    workspaces = list((await session.execute(select(Workspace))).scalars().all())
    for workspace in workspaces:
        await set_rls_session_context(
            session,
            tenant_id=workspace.tenant_id,
            workspace_id=workspace.id,
        )
        ctx = await _context_for_workspace(session, workspace)
        pairs = await list_active_theses(session)
        for thesis, recommendation in pairs:
            symbol_row = await session.get(Symbol, recommendation.symbol_id)
            symbol_code = symbol_row.code if symbol_row else "EURUSD"
            last_price = prices.get(symbol_code, Decimal("1.1000"))
            structure = structures.get(symbol_code, {})
            result = await monitor_thesis_row(
                session,
                ctx,
                thesis,
                recommendation,
                last_price=last_price,
                structure=dict(structure),
            )
            outcomes.append(result)
    return outcomes
