"""Billing webhook idempotency (phase 37)."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "014_billing_webhooks"
down_revision: str | None = "013_mcp_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "billing_webhook_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("external_event_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("payload_json", sa.dialects.postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "external_event_id", name="uq_billing_webhook_event"),
    )


def downgrade() -> None:
    op.drop_table("billing_webhook_events")
