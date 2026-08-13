"""Prove the RLS policies actually isolate — for every workspace-scoped table.

``test_rls_coverage`` asserts the policies *exist* and are shaped correctly.
This asserts they *work*, by driving real rows through them:

1. write a row into workspace A with the migration role (RLS does not apply);
2. bind workspace B on the runtime role and assert the row is invisible;
3. bind workspace B and assert an INSERT carrying workspace A's id is rejected.

Step 3 is the one people skip. Reads and writes are policed by different halves
of a policy, and a table can be perfectly filtered on SELECT while accepting a
cross-tenant INSERT.

Rows are synthesized from column metadata, so tables added by later migration
phases are covered without touching this file. Tables whose required foreign
keys cannot be synthesized are skipped here and covered by the hand-written
scenarios in ``app/tests/test_rls_isolation.py``.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any, NamedTuple

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError, IntegrityError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.rls import set_rls_session_context
from app.models import Base
from app.tests.conformance.test_rls_coverage import workspace_scoped_tables

# Tables whose rows cannot be synthesized generically because they carry
# required foreign keys to rows this fixture does not create.
GENERIC_INSERT_EXEMPT: dict[str, str] = {
    "messages": "requires a conversation row; covered by test_rls_isolation",
    "memory_embeddings": "requires an agent_memories row; covered by test_chat_recall",
}


class WorkspacePair(NamedTuple):
    tenant_a: uuid.UUID
    workspace_a: uuid.UUID
    tenant_b: uuid.UUID
    workspace_b: uuid.UUID
    user_id: uuid.UUID
    symbol_id: uuid.UUID


# Foreign keys that point at platform-global rows the fixture does seed. Without
# these, most of the interesting tables (recommendations, trades, alerts) skip.
def _shared_fk_values(pair: WorkspacePair) -> dict[str, uuid.UUID]:
    return {
        "symbol_id": pair.symbol_id,
        "user_id": pair.user_id,
        "created_by_user_id": pair.user_id,
        "owner_user_id": pair.user_id,
    }


@pytest.fixture
async def workspace_pair(
    db_session: AsyncSession,  # ordering: db_session truncates, so seed after it
    privileged_session: AsyncSession,
) -> AsyncIterator[WorkspacePair]:
    """Two fully-formed tenants, each with one workspace."""
    pair = WorkspacePair(
        tenant_a=uuid.uuid4(),
        workspace_a=uuid.uuid4(),
        tenant_b=uuid.uuid4(),
        workspace_b=uuid.uuid4(),
        user_id=uuid.uuid4(),
        symbol_id=uuid.uuid4(),
    )
    owner_id = pair.user_id

    users = Base.metadata.tables["users"]
    organizations = Base.metadata.tables["organizations"]
    workspaces = Base.metadata.tables["workspaces"]
    symbols = Base.metadata.tables["symbols"]

    await privileged_session.execute(
        sa.insert(users).values(
            id=owner_id,
            email=f"conformance-{owner_id.hex[:10]}@example.com",
            status="ACTIVE",
            mfa_enabled=False,
        )
    )
    await privileged_session.execute(
        sa.insert(organizations),
        [
            {
                "id": pair.tenant_a,
                "name": "Tenant A",
                "slug": f"a-{pair.tenant_a.hex[:10]}",
                "status": "ACTIVE",
            },
            {
                "id": pair.tenant_b,
                "name": "Tenant B",
                "slug": f"b-{pair.tenant_b.hex[:10]}",
                "status": "ACTIVE",
            },
        ],
    )
    await privileged_session.execute(
        sa.insert(workspaces),
        [
            {
                "id": pair.workspace_a,
                "tenant_id": pair.tenant_a,
                "name": "Workspace A",
                "slug": f"wa-{pair.workspace_a.hex[:10]}",
                "owner_user_id": owner_id,
                "settings_json": {},
                "status": "ACTIVE",
            },
            {
                "id": pair.workspace_b,
                "tenant_id": pair.tenant_b,
                "name": "Workspace B",
                "slug": f"wb-{pair.workspace_b.hex[:10]}",
                "owner_user_id": owner_id,
                "settings_json": {},
                "status": "ACTIVE",
            },
        ],
    )
    await privileged_session.execute(
        sa.insert(symbols).values(
            id=pair.symbol_id,
            code=f"S{pair.symbol_id.hex[:6].upper()}",
            base_currency="EUR",
            quote_currency="USD",
            asset_class="FOREX",
            pip_location=-4,
            is_active=True,
            provider_mappings_json={},
        )
    )
    await privileged_session.commit()
    yield pair


def _sample_value(column: sa.Column[Any]) -> Any:
    """A minimal legal value for a column, chosen from its type alone."""
    if isinstance(column.type, sa.Enum):
        return column.type.enums[0]

    try:
        python_type: type[Any] | None = column.type.python_type
    except NotImplementedError:
        return None

    if python_type is uuid.UUID:
        return uuid.uuid4()
    if python_type is bool:
        return False
    if python_type is int:
        return 1
    if python_type is float:
        return 1.0
    if python_type is Decimal:
        return Decimal("1")
    if python_type is dt.datetime:
        return dt.datetime.now(tz=dt.UTC)
    if python_type is dt.date:
        return dt.date.today()
    if python_type is dict:
        return {}
    if python_type is list:
        return []
    if python_type is str:
        length = getattr(column.type, "length", None)
        value = f"conf-{uuid.uuid4().hex}"
        return value[:length] if length else value
    return None


def _build_row(table: sa.Table, *, pair: WorkspacePair) -> dict[str, Any] | None:
    """Values for every column the database will not fill in itself."""
    shared = _shared_fk_values(pair)
    row: dict[str, Any] = {}
    for column in table.columns:
        if column.name == "tenant_id":
            row[column.name] = pair.tenant_a
            continue
        if column.name == "workspace_id":
            row[column.name] = pair.workspace_a
            continue
        if column.nullable or column.server_default is not None or column.default is not None:
            continue
        if column.foreign_keys:
            if column.name in shared:
                row[column.name] = shared[column.name]
                continue
            return None  # required FK to something the fixture does not create
        value = _sample_value(column)
        if value is None:
            return None
        row[column.name] = value
    return row


def _candidate_tables() -> list[sa.Table]:
    scoped = set(workspace_scoped_tables()) - set(GENERIC_INSERT_EXEMPT)
    return [table for table in Base.metadata.sorted_tables if table.name in scoped]


CANDIDATES = _candidate_tables()


def test_candidate_set_is_not_empty() -> None:
    """Guard against the parameter list silently collapsing to nothing."""
    assert len(CANDIDATES) >= 15, (
        f"expected the generic isolation sweep to cover many tables, got "
        f"{[t.name for t in CANDIDATES]}"
    )


@pytest.mark.parametrize("table", CANDIDATES, ids=lambda table: str(table.name))
async def test_row_written_in_one_workspace_is_invisible_in_another(
    table: sa.Table,
    workspace_pair: WorkspacePair,
    privileged_session: AsyncSession,
    db_session: AsyncSession,
) -> None:
    row = _build_row(table, pair=workspace_pair)
    if row is None:
        pytest.skip(f"cannot synthesize a row for {table.name} without extra fixtures")

    try:
        await privileged_session.execute(sa.insert(table).values(**row))
        await privileged_session.commit()
    except (IntegrityError, ProgrammingError, DBAPIError) as exc:
        await privileged_session.rollback()
        pytest.skip(f"{table.name} needs richer fixtures: {type(exc).__name__}")

    await set_rls_session_context(
        db_session,
        tenant_id=workspace_pair.tenant_b,
        workspace_id=workspace_pair.workspace_b,
    )
    visible = await db_session.execute(sa.select(sa.func.count()).select_from(table))
    assert visible.scalar_one() == 0, (
        f"{table.name}: workspace B can read a row belonging to workspace A"
    )

    await set_rls_session_context(
        db_session,
        tenant_id=workspace_pair.tenant_a,
        workspace_id=workspace_pair.workspace_a,
    )
    own = await db_session.execute(sa.select(sa.func.count()).select_from(table))
    assert own.scalar_one() == 1, (
        f"{table.name}: workspace A cannot read its own row — the policy is too strict"
    )


@pytest.mark.parametrize("table", CANDIDATES, ids=lambda table: str(table.name))
async def test_insert_into_a_foreign_workspace_is_rejected(
    table: sa.Table,
    workspace_pair: WorkspacePair,
    db_session: AsyncSession,
) -> None:
    """Bound to workspace B, you must not be able to write a row owned by A."""
    row = _build_row(table, pair=workspace_pair)
    if row is None:
        pytest.skip(f"cannot synthesize a row for {table.name} without extra fixtures")

    await set_rls_session_context(
        db_session,
        tenant_id=workspace_pair.tenant_b,
        workspace_id=workspace_pair.workspace_b,
    )
    with pytest.raises(DBAPIError) as caught:
        await db_session.execute(sa.insert(table).values(**row))
        await db_session.flush()
    await db_session.rollback()

    message = str(caught.value).lower()
    assert "row-level security" in message, (
        f"{table.name}: the cross-workspace INSERT failed, but not because of RLS: {caught.value}"
    )
