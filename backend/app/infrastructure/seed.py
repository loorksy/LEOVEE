"""Platform seed data: roles, permissions, FREE plan."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import PlanCode
from app.models.plan import Plan
from app.models.rbac import Permission, Role, RolePermission

ROLE_DEFINITIONS: list[tuple[str, str]] = [
    ("SUPER_ADMIN", "PLATFORM"),
    ("ADMIN", "PLATFORM"),
    ("SUPPORT", "PLATFORM"),
    ("ANALYST", "WORKSPACE"),
    ("USER", "WORKSPACE"),
]

PERMISSION_CODES: list[str] = [
    "workspace.read",
    "workspace.write",
    "workspace.admin",
    "memory.read",
    "memory.manage",
    "analysis.run",
    "chat.send",
    "admin.audit.read",
]

ROLE_PERMISSION_MAP: dict[str, list[str]] = {
    "SUPER_ADMIN": PERMISSION_CODES,
    "ADMIN": PERMISSION_CODES,
    "SUPPORT": ["workspace.read", "memory.read", "admin.audit.read"],
    "ANALYST": [
        "workspace.read",
        "memory.read",
        "analysis.run",
        "chat.send",
    ],
    "USER": [
        "workspace.read",
        "memory.read",
        "analysis.run",
        "chat.send",
    ],
}

FREE_PLAN_LIMITS = {
    "messages_per_month": 100,
    "analysis_runs_per_month": 20,
    "memory_depth": 50,
}


async def ensure_platform_seed(session: AsyncSession) -> Role:
    """Idempotent seed for roles, permissions, and FREE plan. Returns USER workspace role."""
    perm_by_code: dict[str, Permission] = {}
    for code in PERMISSION_CODES:
        existing = await session.scalar(select(Permission).where(Permission.code == code))
        if existing is None:
            perm = Permission(id=uuid.uuid4(), code=code)
            session.add(perm)
            perm_by_code[code] = perm
        else:
            perm_by_code[code] = existing

    user_role: Role | None = None
    for role_code, scope in ROLE_DEFINITIONS:
        role = await session.scalar(select(Role).where(Role.code == role_code))
        if role is None:
            role = Role(id=uuid.uuid4(), code=role_code, scope=scope, tenant_id=None)
            session.add(role)
            await session.flush()
        if role_code == "USER":
            user_role = role
        for perm_code in ROLE_PERMISSION_MAP.get(role_code, []):
            perm = perm_by_code[perm_code]
            link = await session.scalar(
                select(RolePermission).where(
                    RolePermission.role_id == role.id,
                    RolePermission.permission_id == perm.id,
                )
            )
            if link is None:
                session.add(RolePermission(role_id=role.id, permission_id=perm.id))

    plan = await session.scalar(select(Plan).where(Plan.code == PlanCode.FREE))
    if plan is None:
        session.add(
            Plan(
                code=PlanCode.FREE,
                name="Free",
                limits_json=FREE_PLAN_LIMITS,
                features_json={"tier": "free"},
                is_active=True,
            )
        )

    await session.flush()
    assert user_role is not None
    return user_role
