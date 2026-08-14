"""Telegram as a conversation transport (ADR 0009).

Two tables, and one design point that is easy to get wrong.

**The inbound lookup runs before any tenant is known.** A webhook arrives
carrying a Telegram user id and nothing else; the workspace is the *answer* to
that lookup, not an input to it. So it cannot go through the workspace-scoped
RLS path — there is no ``app.workspace_id`` to set yet, and setting one from
untrusted input is exactly the escape this system exists to prevent.

The resolution is a `SECURITY DEFINER` function that returns the single row
matching a Telegram id and nothing else: no columns beyond the ids it must
return, no filtering the caller controls, no way to enumerate. Everything after
it — every read and write of the conversation — runs under normal RLS bound to
the workspace it returned.

Both tables still carry full workspace RLS for every *other* access path: the
settings page listing links, the code generator, the revoke button.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "020_telegram_transport"
down_revision: str | None = "019_prompt_vector_provenance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("telegram_links", "telegram_link_codes")


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
        "telegram_links",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        # Telegram ids exceed 32 bits.
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_username", sa.String(64), nullable=True),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "linked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
    )
    op.create_index("ix_telegram_links_workspace", "telegram_links", ["workspace_id"])

    op.create_table(
        "telegram_link_codes",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        # Hashed: a code is a bearer credential while it lives, and a database
        # read should not be enough to claim someone's workspace.
        sa.Column("code_hash", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
    )
    op.create_index("ix_telegram_link_codes_expires", "telegram_link_codes", ["expires_at"])

    for table in TABLES:
        _workspace_rls_policy(table)

    # The one path that cannot be workspace-scoped, because the workspace is what
    # it returns. Deliberately narrow: one argument, a fixed projection, no
    # caller-controlled predicate, and it cannot enumerate — an unknown id
    # returns nothing rather than an error that would confirm the table's shape.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION resolve_telegram_link(p_telegram_user_id bigint)
        RETURNS TABLE (tenant_id uuid, workspace_id uuid, user_id uuid, chat_id bigint)
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = public
        AS $$
            SELECT l.tenant_id, l.workspace_id, l.user_id, l.telegram_chat_id
            FROM telegram_links l
            WHERE l.telegram_user_id = p_telegram_user_id
              AND l.revoked_at IS NULL
            LIMIT 1
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION resolve_telegram_link(bigint) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION resolve_telegram_link(bigint) TO leovee_app")

    # Same reasoning for consuming a code: the sender proves which workspace
    # they may join by presenting the code, so the lookup cannot already be
    # scoped to one. Consumption is atomic — the UPDATE ... RETURNING is what
    # makes a code single-use under concurrent webhook deliveries.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION consume_telegram_link_code(p_code_hash text)
        RETURNS TABLE (tenant_id uuid, workspace_id uuid, user_id uuid)
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = public
        AS $$
            UPDATE telegram_link_codes
            SET consumed_at = now()
            WHERE id = (
                SELECT c.id FROM telegram_link_codes c
                WHERE c.code_hash = p_code_hash
                  AND c.consumed_at IS NULL
                  AND c.expires_at > now()
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            )
            RETURNING telegram_link_codes.tenant_id,
                      telegram_link_codes.workspace_id,
                      telegram_link_codes.user_id
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION consume_telegram_link_code(text) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION consume_telegram_link_code(text) TO leovee_app")

    # The link row itself is written by the definer too: at insert time the
    # session is still unbound, and binding RLS from a Telegram id would mean
    # trusting untrusted input to name its own workspace.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION create_telegram_link(
            p_tenant_id uuid,
            p_workspace_id uuid,
            p_user_id uuid,
            p_telegram_user_id bigint,
            p_telegram_chat_id bigint,
            p_username text
        )
        RETURNS void
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = public
        AS $$
            INSERT INTO telegram_links (
                id, tenant_id, workspace_id, user_id,
                telegram_user_id, telegram_chat_id, telegram_username
            )
            VALUES (
                gen_random_uuid(), p_tenant_id, p_workspace_id, p_user_id,
                p_telegram_user_id, p_telegram_chat_id, p_username
            )
            ON CONFLICT (telegram_user_id) DO UPDATE SET
                tenant_id = EXCLUDED.tenant_id,
                workspace_id = EXCLUDED.workspace_id,
                user_id = EXCLUDED.user_id,
                telegram_chat_id = EXCLUDED.telegram_chat_id,
                telegram_username = EXCLUDED.telegram_username,
                revoked_at = NULL,
                linked_at = now(),
                updated_at = now()
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION create_telegram_link(uuid, uuid, uuid, bigint, bigint, text) FROM PUBLIC")
    op.execute(
        "GRANT EXECUTE ON FUNCTION create_telegram_link(uuid, uuid, uuid, bigint, bigint, text) TO leovee_app"
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS create_telegram_link(uuid, uuid, uuid, bigint, bigint, text)")
    op.execute("DROP FUNCTION IF EXISTS consume_telegram_link_code(text)")
    op.execute("DROP FUNCTION IF EXISTS resolve_telegram_link(bigint)")
    for table in TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_workspace_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_telegram_link_codes_expires", table_name="telegram_link_codes")
    op.drop_table("telegram_link_codes")
    op.drop_index("ix_telegram_links_workspace", table_name="telegram_links")
    op.drop_table("telegram_links")
