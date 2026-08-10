"""Market engine artifact tables (Phase 11)."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "008_market_engine_artifacts"
down_revision: str | None = "007_leovee_app_login"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "market_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("symbol_id", sa.Uuid(), sa.ForeignKey("symbols.id", ondelete="CASCADE"), nullable=False),
        sa.Column("timeframe", sa.String(length=8), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("price", sa.Numeric(18, 8), nullable=True),
        sa.Column("strength", sa.Numeric(6, 4), nullable=True),
        sa.Column("confidence", sa.Numeric(6, 4), nullable=True),
        sa.Column("evidence_json", sa.dialects.postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("invalidation_json", sa.dialects.postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_market_events_symbol_tf_ts", "market_events", ["symbol_id", "timeframe", "ts"])

    op.create_table(
        "structures",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("symbol_id", sa.Uuid(), sa.ForeignKey("symbols.id", ondelete="CASCADE"), nullable=False),
        sa.Column("timeframe", sa.String(length=8), nullable=False),
        sa.Column("structure_type", sa.String(length=64), nullable=False),
        sa.Column("start_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_ts", sa.DateTime(timezone=True), nullable=True),
        sa.Column("geometry_json", sa.dialects.postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("confidence", sa.Numeric(6, 4), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_structures_symbol_tf", "structures", ["symbol_id", "timeframe"])

    op.create_table(
        "price_zones",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("symbol_id", sa.Uuid(), sa.ForeignKey("symbols.id", ondelete="CASCADE"), nullable=False),
        sa.Column("timeframe", sa.String(length=8), nullable=False),
        sa.Column("zone_type", sa.String(length=32), nullable=False),
        sa.Column("price_low", sa.Numeric(18, 8), nullable=False),
        sa.Column("price_high", sa.Numeric(18, 8), nullable=False),
        sa.Column("start_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_ts", sa.DateTime(timezone=True), nullable=True),
        sa.Column("strength", sa.Numeric(6, 4), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_price_zones_symbol_tf", "price_zones", ["symbol_id", "timeframe"])

    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON market_events, structures, price_zones TO leovee_app"
    )


def downgrade() -> None:
    op.drop_index("ix_price_zones_symbol_tf", table_name="price_zones")
    op.drop_table("price_zones")
    op.drop_index("ix_structures_symbol_tf", table_name="structures")
    op.drop_table("structures")
    op.drop_index("ix_market_events_symbol_tf_ts", table_name="market_events")
    op.drop_table("market_events")
