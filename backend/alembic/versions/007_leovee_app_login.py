"""leovee_app login role for runtime RLS (non-superuser, no BYPASSRLS)."""

from collections.abc import Sequence

from alembic import op

revision: str = "007_leovee_app_login"
down_revision: str | None = "006_leovee_app_role"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER ROLE leovee_app WITH LOGIN PASSWORD 'leovee_app'")
    op.execute("ALTER ROLE leovee_app NOSUPERUSER NOBYPASSRLS NOINHERIT")
    op.execute("GRANT USAGE ON SCHEMA public TO leovee_app")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO leovee_app")
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO leovee_app")
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO leovee_app"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "GRANT USAGE, SELECT ON SEQUENCES TO leovee_app"
    )


def downgrade() -> None:
    op.execute("ALTER ROLE leovee_app WITH NOLOGIN")
