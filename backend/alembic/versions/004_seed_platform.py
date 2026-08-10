"""Seed roles, permissions, and FREE plan."""

from collections.abc import Sequence

import sqlalchemy as sa
import uuid

from alembic import op

revision: str = "004_seed_platform"
down_revision: str | None = "003_platform_core"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLE_DEFINITIONS = [
    ("SUPER_ADMIN", "PLATFORM"),
    ("ADMIN", "PLATFORM"),
    ("SUPPORT", "PLATFORM"),
    ("ANALYST", "WORKSPACE"),
    ("USER", "WORKSPACE"),
]

PERMISSION_CODES = [
    "workspace.read",
    "workspace.write",
    "workspace.admin",
    "memory.read",
    "memory.manage",
    "analysis.run",
    "chat.send",
    "admin.audit.read",
]

ROLE_PERMISSION_MAP = {
    "SUPER_ADMIN": PERMISSION_CODES,
    "ADMIN": PERMISSION_CODES,
    "SUPPORT": ["workspace.read", "memory.read", "admin.audit.read"],
    "ANALYST": ["workspace.read", "memory.read", "analysis.run", "chat.send"],
    "USER": ["workspace.read", "memory.read", "analysis.run", "chat.send"],
}

FREE_PLAN_LIMITS = '{"messages_per_month": 100, "analysis_runs_per_month": 20, "memory_depth": 50}'
FREE_PLAN_FEATURES = '{"tier": "free"}'


def upgrade() -> None:
    conn = op.get_bind()
    perm_ids: dict[str, uuid.UUID] = {}
    for code in PERMISSION_CODES:
        perm_id = uuid.uuid4()
        perm_ids[code] = perm_id
        conn.execute(
            sa.text("INSERT INTO permissions (id, code) VALUES (:id, :code) ON CONFLICT (code) DO NOTHING"),
            {"id": perm_id, "code": code},
        )

    for role_code, scope in ROLE_DEFINITIONS:
        role_id = uuid.uuid4()
        conn.execute(
            sa.text(
                """
                INSERT INTO roles (id, code, scope, tenant_id, created_at, updated_at)
                VALUES (:id, :code, :scope, NULL, now(), now())
                ON CONFLICT (code) DO NOTHING
                """
            ),
            {"id": role_id, "code": role_code, "scope": scope},
        )
        row = conn.execute(sa.text("SELECT id FROM roles WHERE code = :code"), {"code": role_code}).fetchone()
        if row is None:
            continue
        role_id = row[0]
        for perm_code in ROLE_PERMISSION_MAP.get(role_code, []):
            conn.execute(
                sa.text(
                    """
                    INSERT INTO role_permissions (role_id, permission_id)
                    SELECT :role_id, p.id FROM permissions p WHERE p.code = :perm_code
                    ON CONFLICT DO NOTHING
                    """
                ),
                {"role_id": role_id, "perm_code": perm_code},
            )

    conn.execute(
        sa.text(
            """
            INSERT INTO plans (id, code, name, limits_json, features_json, is_active, created_at, updated_at)
            VALUES (:id, 'FREE', 'Free', CAST(:limits AS JSON), CAST(:features AS JSON), true, now(), now())
            ON CONFLICT (code) DO NOTHING
            """
        ),
        {
            "id": uuid.uuid4(),
            "limits": FREE_PLAN_LIMITS,
            "features": FREE_PLAN_FEATURES,
        },
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM role_permissions"))
    op.execute(sa.text("DELETE FROM permissions"))
    op.execute(sa.text("DELETE FROM roles"))
    op.execute(sa.text("DELETE FROM plans WHERE code = 'FREE'"))
