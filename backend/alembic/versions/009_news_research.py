"""News events and workspace-scoped research items (Phase 14)."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "009_news_research"
down_revision: str | None = "008_market_engine_artifacts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _workspace_rls_policy(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"DROP POLICY IF EXISTS {table}_workspace_isolation ON {table}")
    op.execute(
        f"""
        CREATE POLICY {table}_workspace_isolation ON {table}
        USING (
            tenant_id = current_setting('app.tenant_id', true)::uuid
            AND workspace_id = current_setting('app.workspace_id', true)::uuid
        )
        WITH CHECK (
            tenant_id = current_setting('app.tenant_id', true)::uuid
            AND workspace_id = current_setting('app.workspace_id', true)::uuid
        )
        """
    )


def upgrade() -> None:
    op.create_table(
        "news_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("headline", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=True),
        sa.Column("relevance", sa.Numeric(6, 4), nullable=True),
        sa.Column("market_impact", sa.String(length=32), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("external_id", sa.String(length=128), nullable=False),
        sa.Column("raw_json", sa.dialects.postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "external_id", name="uq_news_events_source_external"),
    )
    op.create_index("ix_news_events_published", "news_events", ["published_at"])

    op.create_table(
        "research_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("symbol_id", sa.Uuid(), nullable=True),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("items_json", sa.dialects.postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column(
            "contradictions_json",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("agent_run_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_research_items_workspace", "research_items", ["workspace_id"])

    _workspace_rls_policy("research_items")
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON news_events, research_items TO leovee_app"
    )


def downgrade() -> None:
    op.drop_index("ix_research_items_workspace", table_name="research_items")
    op.drop_table("research_items")
    op.drop_index("ix_news_events_published", table_name="news_events")
    op.drop_table("news_events")
