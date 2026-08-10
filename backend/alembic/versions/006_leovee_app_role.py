"""Create leovee_app role for RLS enforcement in tests and runtime."""

from collections.abc import Sequence

from alembic import op

revision: str = "006_leovee_app_role"
down_revision: str | None = "005_learning_rls_candles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'leovee_app') THEN
            CREATE ROLE leovee_app NOINHERIT;
          END IF;
        END$$;
        """
    )
    op.execute("GRANT USAGE ON SCHEMA public TO leovee_app")
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO leovee_app"
    )
    op.execute("GRANT leovee_app TO postgres")


def downgrade() -> None:
    op.execute("REVOKE leovee_app FROM postgres")
    op.execute("DROP ROLE IF EXISTS leovee_app")
