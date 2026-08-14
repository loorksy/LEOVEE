"""Record which prompt produced a run, and tell the truth about vectors.

Two provenance problems, both invisible until something downstream depends on
them.

**Prompts.** The learning loop (M8) attributes outcomes back to decisions in
order to calibrate confidence. Without knowing which prompt produced a decision,
a calibration curve spanning a prompt change averages two different analysts
together, and the resulting spread reads as ordinary noise. `prompt_versions` is
a platform-global catalogue of every prompt text ever sent, keyed by the SHA-256
of its body, and `agent_runs.prompt_hash` points into it.

The catalogue is deliberately **not** workspace-scoped: prompts are platform
assets, identical for every tenant, and a per-workspace copy of the same text
would fragment the very grouping the learning loop needs. Nothing tenant-derived
is stored in it.

**Embeddings.** `memory_embeddings.model` defaulted to `text-embedding-3-small`
while every vector in the table came from a SHA-256 hash — the column was
asserting a provenance no row had. Cosine distance between a hashed vector and a
real one is meaningless, and a single HNSW index holding both mixes them with no
way to tell which is which. This relabels existing rows as `deterministic-v1`,
which is what they actually are, and drops the misleading default so the writer
has to state what produced each vector.

The relabel is safe by construction: at this revision the only code path that
ever wrote a vector was the deterministic one.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "019_prompt_vector_provenance"
down_revision: str | None = "018_seed_gold_symbol"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DETERMINISTIC_MODEL = "deterministic-v1"


def upgrade() -> None:
    op.create_table(
        "prompt_versions",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        # The content hash IS the identity. Two deploys that ship the same text
        # are the same prompt version, whatever the file was called.
        sa.Column("hash", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("version", sa.String(32), nullable=False, server_default="0.0.0"),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.dialects.postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_prompt_versions_name", "prompt_versions", ["name"])

    op.add_column("agent_runs", sa.Column("prompt_hash", sa.String(64), nullable=True))
    op.create_index("ix_agent_runs_prompt_hash", "agent_runs", ["prompt_hash"])

    op.execute(
        sa.text("UPDATE memory_embeddings SET model = :model").bindparams(
            model=DETERMINISTIC_MODEL
        )
    )
    op.alter_column("memory_embeddings", "model", server_default=None)
    # Searches filter by model so generations never rank against each other;
    # without this index that filter scans the table on every retrieval.
    op.create_index("ix_memory_embeddings_model", "memory_embeddings", ["model"])


def downgrade() -> None:
    op.drop_index("ix_memory_embeddings_model", table_name="memory_embeddings")
    op.alter_column(
        "memory_embeddings",
        "model",
        server_default=sa.text("'text-embedding-3-small'"),
    )
    op.drop_index("ix_agent_runs_prompt_hash", table_name="agent_runs")
    op.drop_column("agent_runs", "prompt_hash")
    op.drop_index("ix_prompt_versions_name", table_name="prompt_versions")
    op.drop_table("prompt_versions")
