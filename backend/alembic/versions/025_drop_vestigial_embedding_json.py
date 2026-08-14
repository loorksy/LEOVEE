"""Drop the vestigial ``memory_embeddings.embedding_json`` column.

The column was created ``NOT NULL`` in 003 and never written since: the real
vector lives in ``embedding vector(1536)``, and ``index_memory_embedding``
constructs the row without ``embedding_json``. Under the NOT NULL constraint
*every* embedding INSERT therefore raised IntegrityError, so the memory-index
and memory-recompute jobs crashed on their first run in any workspace with a
stored memory. A grep across the app confirms nothing reads the column.

Dropping it is the honest fix: the field claimed to hold an embedding payload
that no writer ever produced.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "025_drop_embedding_json"
down_revision: str | None = "024_market_cases"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("memory_embeddings", "embedding_json")


def downgrade() -> None:
    # Recreate nullable on the way down: the original NOT NULL was itself the
    # defect, and a downgrade must not reintroduce a constraint no writer can
    # satisfy.
    op.add_column(
        "memory_embeddings",
        sa.Column("embedding_json", sa.JSON(), nullable=True),
    )
