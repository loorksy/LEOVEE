"""Platform secrets store for admin-managed provider credentials."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "016_platform_secrets"
down_revision: str | None = "015_api_keys"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "platform_secrets",
        sa.Column("key", sa.String(length=64), primary_key=True),
        sa.Column("ciphertext", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("platform_secrets")
