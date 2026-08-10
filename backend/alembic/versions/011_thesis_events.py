"""Thesis monitoring events (Phase 22)."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "011_thesis_events"
down_revision: str | None = "010_model_router_embeddings"
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
        "thesis_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("thesis_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload_json", sa.dialects.postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_thesis_events_thesis", "thesis_events", ["thesis_id", "created_at"])

    _workspace_rls_policy("thesis_events")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON thesis_events TO leovee_app")


def downgrade() -> None:
    op.drop_index("ix_thesis_events_thesis", table_name="thesis_events")
    op.drop_table("thesis_events")
