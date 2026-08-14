"""Close the watchlist_items cross-workspace read.

``watchlists`` is workspace-scoped and RLS-protected. ``watchlist_items`` is its
child, carries no tenant_id/workspace_id of its own, and had no policy at all —
so a session bound to workspace B could read (and write) the rows belonging to
workspace A's watchlists by querying the child table directly:

    SET ROLE leovee_app;
    SELECT set_config('app.workspace_id', '<workspace B>', false);
    SELECT count(*) FROM watchlists;       -- 0, correctly filtered
    SELECT count(*) FROM watchlist_items;  -- 1, workspace A's row

This mirrors the existing ``agent_traces_via_run`` policy: derive the scope from
the parent row rather than duplicating tenant columns onto the child. Note that
for a ``FOR ALL`` policy PostgreSQL reuses the USING expression as the WITH
CHECK expression, so this covers writes as well as reads.

Found by app/tests/conformance/test_rls_coverage.py on its first run.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "017_watchlist_items_rls"
down_revision: str | None = "016_platform_secrets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DROP POLICY IF EXISTS watchlist_items_via_watchlist ON watchlist_items")
    op.execute("ALTER TABLE watchlist_items ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE watchlist_items FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY watchlist_items_via_watchlist ON watchlist_items
        USING (
            EXISTS (
                SELECT 1 FROM watchlists w
                WHERE w.id = watchlist_items.watchlist_id
                AND w.tenant_id = current_setting('app.tenant_id', true)::uuid
                AND w.workspace_id = current_setting('app.workspace_id', true)::uuid
            )
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS watchlist_items_via_watchlist ON watchlist_items")
    op.execute("ALTER TABLE watchlist_items DISABLE ROW LEVEL SECURITY")
