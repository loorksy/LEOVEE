"""Every table is either workspace-isolated or explicitly declared otherwise.

The migration plan (docs/AICHART_MIGRATION_PLAN.md) adds roughly thirty tables
across later phases. A hand-maintained list of "tables that need RLS" is a list
someone will forget to update, and the failure mode is a silent cross-tenant
read. So this walks SQLAlchemy metadata instead and forces every table into one
of three buckets, each of which has to be justified in code:

1. **workspace-isolated** — carries ``workspace_id`` and has a
   ``<table>_workspace_isolation`` policy with RLS enabled *and forced*;
2. **scoped via a parent** — no tenant columns of its own, protected by an
   EXISTS policy against its parent (``VIA_PARENT_POLICIES``);
3. **platform-global** — genuinely shared, listed in ``PLATFORM_GLOBAL_TABLES``
   with a reason, or boundary-defining and listed in ``BOUNDARY_TABLES``.

Anything that falls into none of them fails the suite. Absence of isolation
becomes a decision someone wrote down, never an omission.

A note on WITH CHECK: for a ``FOR ALL`` policy PostgreSQL reuses the USING
expression as the WITH CHECK expression, so a policy with only USING still
blocks cross-tenant INSERTs. What is *not* safe is a policy restricted to
``SELECT``, which leaves writes entirely unpoliced — that is what gets checked.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Base

# Child tables with no tenant columns, protected by an EXISTS policy against
# their parent. Maps table -> policy name.
VIA_PARENT_POLICIES: dict[str, str] = {
    "agent_traces": "agent_traces_via_run",
    "watchlist_items": "watchlist_items_via_watchlist",
}

# Tables that carry workspace_id but must NOT have the standard policy, because
# they define the boundary that the policy depends on.
BOUNDARY_TABLES: dict[str, str] = {
    "workspace_members": (
        "defines workspace access itself — get_workspace_context reads it to "
        "decide which workspace to bind, so it cannot be filtered by the "
        "binding it produces. Scoped in code by an explicit membership check."
    ),
}

# Tables that are deliberately NOT workspace-scoped. Every entry needs a reason:
# if you cannot write one, the table probably wants a workspace_id instead.
PLATFORM_GLOBAL_TABLES: dict[str, str] = {
    # Prompts are platform assets: identical text for every tenant, and a
    # per-workspace copy would fragment the grouping the learning loop needs
    # ("how did runs under this prompt perform" is a question about the
    # prompt). Nothing tenant-derived is stored in it.
    "prompt_versions": "platform-global prompt catalogue; no tenant data",
    # Identity and tenancy live above the workspace boundary.
    "organizations": "tenancy root",
    "organization_members": "tenant-scoped; guards workspace access itself",
    "users": "global identity; workspace access is via membership",
    "workspaces": "the boundary itself",
    "sessions": "user-scoped auth, not workspace-scoped",
    "auth_tokens": "user-scoped auth, not workspace-scoped",
    "roles": "platform RBAC catalog",
    "permissions": "platform RBAC catalog",
    "role_permissions": "platform RBAC catalog",
    # Billing is tenant-scoped, one level above workspaces.
    "plans": "platform billing catalog",
    "subscriptions": "tenant-scoped, not workspace-scoped",
    "billing_webhook_events": "platform webhook idempotency ledger",
    "feature_flags": "platform configuration",
    "platform_secrets": "platform configuration, admin-only",
    "model_configs": "platform LLM routing catalog",
    # Shared market reference data: the candles for XAUUSD are the same candles
    # for every workspace, and copying them per tenant would multiply storage by
    # the tenant count for no isolation benefit.
    "symbols": "platform market reference data",
    "candles": "platform market data, partitioned by timeframe",
    "news_events": "global market news, deliberately shared",
    # Deterministic engine artifacts: a swing high on XAUUSD H1 is a fact about
    # the market, identical for every workspace, so it is computed once and
    # shared. M4 rewrites these engines — if their outputs ever become
    # workspace-specific (per-workspace thresholds, user-tuned parameters),
    # these three tables must gain workspace_id at that point.
    "market_events": "deterministic market fact, shared across workspaces (revisit in M4)",
    # A fingerprint of a past moment on XAUUSD plus how it resolved. Objective
    # market history, in the same class as `candles`. Per-workspace copies would
    # multiply storage by the tenant count *and* leave every new workspace with
    # no memory of the market itself — not merely none of its own decisions.
    # What stays private is `strategy_stats`: how a workspace's own plans fared.
    "market_cases": "shared market history; no tenant-derived column",
    "structures": "deterministic market fact, shared across workspaces (revisit in M4)",
    "price_zones": "deterministic market fact, shared across workspaces (revisit in M4)",
}


def _model_tables() -> dict[str, set[str]]:
    """Table name -> column names, straight from SQLAlchemy metadata."""
    return {
        table.name: {column.name for column in table.columns}
        for table in Base.metadata.sorted_tables
    }


def workspace_scoped_tables() -> list[str]:
    """Tables that must carry the standard workspace isolation policy."""
    return sorted(
        name
        for name, columns in _model_tables().items()
        if "workspace_id" in columns and name not in BOUNDARY_TABLES
    )


async def _live_tables(session: AsyncSession) -> set[str]:
    result = await session.execute(
        text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    )
    return {row[0] for row in result}


async def _policies(
    session: AsyncSession,
) -> dict[str, list[tuple[str, str, str | None, str | None]]]:
    result = await session.execute(
        text(
            """
            SELECT tablename, policyname, cmd, qual, with_check
            FROM pg_policies
            WHERE schemaname = 'public'
            """
        )
    )
    policies: dict[str, list[tuple[str, str, str | None, str | None]]] = {}
    for table_name, policy_name, cmd, qual, with_check in result:
        policies.setdefault(table_name, []).append((policy_name, cmd, qual, with_check))
    return policies


@pytest.mark.no_db
def test_every_table_is_isolated_or_explicitly_exempt() -> None:
    """No table may be silently unscoped."""
    classified = set(PLATFORM_GLOBAL_TABLES) | set(VIA_PARENT_POLICIES) | set(BOUNDARY_TABLES)
    unclassified = sorted(
        name
        for name, columns in _model_tables().items()
        if "workspace_id" not in columns and name not in classified
    )
    assert not unclassified, (
        "These tables have no workspace_id and are not classified. Give them a "
        "workspace_id and an RLS policy, protect them via their parent "
        "(VIA_PARENT_POLICIES), or declare them platform-global with a reason: "
        + ", ".join(unclassified)
    )


@pytest.mark.no_db
def test_exemption_lists_have_no_stale_entries() -> None:
    """An exemption must not outlive the table it excuses."""
    known = set(_model_tables())
    for label, mapping in (
        ("PLATFORM_GLOBAL_TABLES", PLATFORM_GLOBAL_TABLES),
        ("VIA_PARENT_POLICIES", VIA_PARENT_POLICIES),
        ("BOUNDARY_TABLES", BOUNDARY_TABLES),
    ):
        stale = sorted(set(mapping) - known)
        assert not stale, f"{label} names tables that no longer exist: {stale}"

    tables = _model_tables()
    wrongly_global = sorted(
        name for name in PLATFORM_GLOBAL_TABLES if "workspace_id" in tables.get(name, set())
    )
    assert not wrongly_global, (
        "These tables gained a workspace_id but are still declared platform-global; "
        f"give them the standard policy instead: {wrongly_global}"
    )


async def test_workspace_tables_have_rls_enabled_and_forced(
    privileged_session: AsyncSession,
) -> None:
    """ENABLE alone is not enough — the table owner bypasses RLS without FORCE."""
    tables = workspace_scoped_tables() + list(VIA_PARENT_POLICIES)
    assert tables, "expected at least one workspace-scoped table"

    live = await _live_tables(privileged_session)
    result = await privileged_session.execute(
        text(
            """
            SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relkind = 'r'
            """
        )
    )
    flags = {row[0]: (row[1], row[2]) for row in result}

    missing = [
        f"{table} (enabled={flags.get(table, (False, False))[0]}, "
        f"forced={flags.get(table, (False, False))[1]})"
        for table in tables
        if table in live and not all(flags.get(table, (False, False)))
    ]
    assert not missing, "Isolated tables without ENABLE + FORCE ROW LEVEL SECURITY: " + ", ".join(
        missing
    )


async def test_workspace_tables_have_an_isolation_policy(
    privileged_session: AsyncSession,
) -> None:
    live = await _live_tables(privileged_session)
    policies = await _policies(privileged_session)

    problems: list[str] = []
    expected_policy = {table: f"{table}_workspace_isolation" for table in workspace_scoped_tables()}
    expected_policy.update(VIA_PARENT_POLICIES)

    for table, policy_name in sorted(expected_policy.items()):
        if table not in live:
            continue
        found = [entry for entry in policies.get(table, []) if entry[0] == policy_name]
        if not found:
            names = [entry[0] for entry in policies.get(table, [])]
            problems.append(f"{table}: no policy named {policy_name} (has {names})")
            continue
        _, cmd, qual, _with_check = found[0]
        if not qual:
            problems.append(f"{table}: policy {policy_name} has no USING clause")
        if cmd != "ALL":
            # A SELECT-only policy filters reads and leaves writes unpoliced.
            problems.append(
                f"{table}: policy {policy_name} applies to {cmd}, not ALL — "
                "writes would be unpoliced"
            )

    assert not problems, "RLS policy problems:\n  " + "\n  ".join(problems)


async def test_boundary_tables_have_no_workspace_policy(
    privileged_session: AsyncSession,
) -> None:
    """A boundary table with the standard policy would deadlock its own lookup."""
    policies = await _policies(privileged_session)
    for table in BOUNDARY_TABLES:
        names = [entry[0] for entry in policies.get(table, [])]
        assert f"{table}_workspace_isolation" not in names, (
            f"{table} is declared a boundary table but carries the standard "
            "workspace policy; one of the two is wrong"
        )


async def test_runtime_role_cannot_bypass_rls(privileged_session: AsyncSession) -> None:
    """The whole scheme collapses if leovee_app is superuser or BYPASSRLS."""
    result = await privileged_session.execute(
        text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'leovee_app'")
    )
    row = result.first()
    assert row is not None, "the leovee_app runtime role does not exist"
    is_super, bypasses = row
    assert not is_super, "leovee_app must not be a superuser — RLS would not apply"
    assert not bypasses, "leovee_app must not have BYPASSRLS"
