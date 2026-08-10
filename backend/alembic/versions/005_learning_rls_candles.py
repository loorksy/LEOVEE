"""Learning tables, OANDA connections, RLS policies, candles partitioning, pgvector embeddings."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "005_learning_rls_candles"
down_revision: str | None = "004_seed_platform"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMEFRAMES = ("M1", "M5", "M15", "M30", "H1", "H4", "D1")

RLS_WORKSPACE_TABLES = (
    "conversations",
    "messages",
    "agent_episodes",
    "agent_memories",
    "memory_embeddings",
    "lessons",
    "symbol_profiles",
    "strategy_stats",
    "chart_annotations",
    "oanda_connections",
    "trades",
    "recommendations",
    "theses",
    "outcome_records",
    "agent_runs",
    "calibration_bins",
    "usage_records",
    "watchlists",
)


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
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("trigger", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=64), nullable=False, server_default="RUNNING"),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("decision", sa.String(length=64), nullable=True),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("tool_calls_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("memories_retrieved_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_runs_workspace", "agent_runs", ["workspace_id"])

    op.create_table(
        "agent_traces",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("agent_run_id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload_json", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_traces_run", "agent_traces", ["agent_run_id"])

    op.create_table(
        "outcome_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("thesis_id", sa.Uuid(), nullable=True),
        sa.Column("recommendation_id", sa.Uuid(), nullable=True),
        sa.Column("trade_id", sa.Uuid(), nullable=True),
        sa.Column("outcome", sa.String(length=64), nullable=False),
        sa.Column("r_multiple", sa.Numeric(10, 4), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="LIVE"),
        sa.Column("facts_json", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorder_version", sa.String(length=32), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_outcome_records_workspace", "outcome_records", ["workspace_id"])

    op.create_table(
        "strategy_stats",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("symbol_id", sa.Uuid(), nullable=True),
        sa.Column("strategy_code", sa.String(length=64), nullable=False),
        sa.Column("setup_type", sa.String(length=64), nullable=False, server_default="ANY"),
        sa.Column("regime_bucket", sa.String(length=64), nullable=False, server_default="ANY"),
        sa.Column("session_bucket", sa.String(length=32), nullable=False, server_default="ANY"),
        sa.Column("volatility_bucket", sa.String(length=32), nullable=False, server_default="ANY"),
        sa.Column("occurrences", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("wins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_r", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("profit_factor", sa.Numeric(10, 4), nullable=True),
        sa.Column("expectancy", sa.Numeric(10, 4), nullable=True),
        sa.Column("suspended", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("metadata_json", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "strategy_code",
            "setup_type",
            "regime_bucket",
            "session_bucket",
            "volatility_bucket",
            name="uq_strategy_stat_bucket",
        ),
    )

    op.create_table(
        "symbol_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("symbol_id", sa.Uuid(), nullable=False),
        sa.Column("profile_json", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("confidence", sa.Numeric(6, 4), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "symbol_id", name="uq_symbol_profile_ws_symbol"),
    )
    op.create_index("ix_symbol_profiles_symbol", "symbol_profiles", ["symbol_id"])

    op.create_table(
        "calibration_bins",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("strategy_code", sa.String(length=64), nullable=True),
        sa.Column("bin_lower", sa.Numeric(4, 3), nullable=False),
        sa.Column("bin_upper", sa.Numeric(4, 3), nullable=False),
        sa.Column("predicted_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("realized_success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "bin_lower", "bin_upper", name="uq_calibration_bin"),
    )

    op.create_table(
        "oanda_connections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("environment", sa.String(length=16), nullable=False, server_default="practice"),
        sa.Column("label", sa.String(length=128), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.execute(
        """
        ALTER TABLE memory_embeddings
        ADD COLUMN IF NOT EXISTS embedding vector(1536);
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS candles_partitioned (
            symbol_id uuid NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
            timeframe timeframe NOT NULL,
            ts timestamptz NOT NULL,
            open numeric(18, 8) NOT NULL,
            high numeric(18, 8) NOT NULL,
            low numeric(18, 8) NOT NULL,
            close numeric(18, 8) NOT NULL,
            volume numeric(18, 8),
            complete boolean NOT NULL,
            source text NOT NULL,
            ingested_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (symbol_id, timeframe, ts)
        ) PARTITION BY LIST (timeframe);
        """
    )
    for tf in TIMEFRAMES:
        op.execute(
            f"""
            CREATE TABLE IF NOT EXISTS candles_{tf.lower()}
            PARTITION OF candles_partitioned
            FOR VALUES IN ('{tf}');
            """
        )

    op.execute(
        """
        INSERT INTO candles_partitioned (
            symbol_id, timeframe, ts, open, high, low, close, volume, complete, source, ingested_at
        )
        SELECT symbol_id, timeframe, ts, open, high, low, close, volume, complete, source, ingested_at
        FROM candles
        ON CONFLICT (symbol_id, timeframe, ts) DO UPDATE SET
            open = EXCLUDED.open,
            high = EXCLUDED.high,
            low = EXCLUDED.low,
            close = EXCLUDED.close,
            volume = EXCLUDED.volume,
            complete = EXCLUDED.complete,
            source = EXCLUDED.source,
            ingested_at = EXCLUDED.ingested_at;
        """
    )
    op.execute("DROP TABLE IF EXISTS candles CASCADE")
    op.execute("ALTER TABLE candles_partitioned RENAME TO candles")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_candles_symbol_tf_ts_desc
        ON candles (symbol_id, timeframe, ts DESC);
        """
    )

    op.execute("DROP POLICY IF EXISTS agent_traces_via_run ON agent_traces")
    op.execute("ALTER TABLE agent_traces ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE agent_traces FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY agent_traces_via_run ON agent_traces
        USING (
            EXISTS (
                SELECT 1 FROM agent_runs r
                WHERE r.id = agent_traces.agent_run_id
                AND r.tenant_id = current_setting('app.tenant_id', true)::uuid
                AND r.workspace_id = current_setting('app.workspace_id', true)::uuid
            )
        )
        """
    )

    for table in RLS_WORKSPACE_TABLES:
        _workspace_rls_policy(table)


def downgrade() -> None:
    for table in reversed(RLS_WORKSPACE_TABLES):
        op.execute(f"DROP POLICY IF EXISTS {table}_workspace_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.execute("DROP POLICY IF EXISTS agent_traces_via_run ON agent_traces")
    op.drop_table("oanda_connections")
    op.drop_table("calibration_bins")
    op.drop_table("symbol_profiles")
    op.drop_table("strategy_stats")
    op.drop_table("outcome_records")
    op.drop_table("agent_traces")
    op.drop_table("agent_runs")
