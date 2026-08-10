"""Model routing configuration (Phase 17)."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "010_model_router_embeddings"
down_revision: str | None = "009_news_research"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "model_configs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task", sa.String(length=64), nullable=False),
        sa.Column("primary_provider", sa.String(length=32), nullable=False),
        sa.Column("primary_model", sa.String(length=128), nullable=False),
        sa.Column("fallback_provider", sa.String(length=32), nullable=True),
        sa.Column("fallback_model", sa.String(length=128), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task", name="uq_model_configs_task"),
    )
    op.execute(
        """
        INSERT INTO model_configs (id, task, primary_provider, primary_model, fallback_provider, fallback_model)
        SELECT gen_random_uuid(), 'narrative', 'openai', 'gpt-4o-mini', 'anthropic', 'claude-3-5-haiku-latest'
        WHERE NOT EXISTS (SELECT 1 FROM model_configs WHERE task = 'narrative')
        """
    )
    op.execute(
        """
        INSERT INTO model_configs (id, task, primary_provider, primary_model, fallback_provider, fallback_model)
        SELECT gen_random_uuid(), 'reasoning', 'anthropic', 'claude-3-5-sonnet-latest', 'openai', 'gpt-4o'
        WHERE NOT EXISTS (SELECT 1 FROM model_configs WHERE task = 'reasoning')
        """
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON model_configs TO leovee_app"
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS memory_embeddings_hnsw
        ON memory_embeddings
        USING hnsw (embedding vector_cosine_ops)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS memory_embeddings_hnsw")
    op.drop_table("model_configs")
