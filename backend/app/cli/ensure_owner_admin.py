#!/usr/bin/env python3
"""Create or update an owner admin user (SUPER_ADMIN) for staging bootstrap.

Usage (inside API container / venv):
  OWNER_EMAIL=loorksy@gmail.com OWNER_PASSWORD='...' \\
    python -m app.cli.ensure_owner_admin

Never commit passwords. Practice OANDA only — this script only touches auth/RBAC.
"""

from __future__ import annotations

import asyncio
import os
import sys


async def _run() -> None:
    email = (os.environ.get("OWNER_EMAIL") or "").strip().lower()
    password = os.environ.get("OWNER_PASSWORD") or ""
    org_name = os.environ.get("OWNER_ORG_NAME") or "Leovee Owner"
    if not email or not password:
        print("OWNER_EMAIL and OWNER_PASSWORD are required", file=sys.stderr)
        raise SystemExit(2)

    from sqlalchemy import select

    from app.core.config import get_settings
    from app.core.datetime_utils import utc_now
    from app.core.security import hash_password
    from app.infrastructure.database import get_session_factory
    from app.infrastructure.seed import ensure_platform_seed
    from app.models.base import OrganizationMemberRole, OrganizationStatus, UserStatus
    from app.models.organization import Organization
    from app.models.organization_member import OrganizationMember
    from app.models.rbac import Role
    from app.models.user import User
    from app.models.workspace_member import WorkspaceMember
    from app.services.workspace_service import create_default_workspace

    settings = get_settings()
    if not settings.database_url:
        print("DATABASE_URL is not configured", file=sys.stderr)
        raise SystemExit(2)

    factory = get_session_factory()
    if factory is None:
        print("Session factory unavailable", file=sys.stderr)
        raise SystemExit(2)

    async with factory() as session:
        await ensure_platform_seed(session)
        admin_role = await session.scalar(select(Role).where(Role.code == "SUPER_ADMIN"))
        if admin_role is None:
            print("SUPER_ADMIN role missing after seed", file=sys.stderr)
            raise SystemExit(1)

        user = await session.scalar(select(User).where(User.email == email))
        created = False
        if user is None:
            org = Organization(
                name=org_name,
                slug=f"owner-{email.split('@')[0][:24]}",
                status=OrganizationStatus.ACTIVE,
            )
            user = User(
                email=email,
                password_hash=hash_password(password),
                status=UserStatus.ACTIVE,
                email_verified_at=utc_now(),
            )
            session.add_all([org, user])
            await session.flush()
            session.add(
                OrganizationMember(
                    tenant_id=org.id,
                    user_id=user.id,
                    role=OrganizationMemberRole.ORG_OWNER,
                )
            )
            await session.flush()
            await create_default_workspace(
                session,
                tenant_id=org.id,
                owner_user_id=user.id,
                name="Owner Workspace",
            )
            created = True
        else:
            user.password_hash = hash_password(password)
            user.status = UserStatus.ACTIVE
            if user.email_verified_at is None:
                user.email_verified_at = utc_now()

        members = list(
            (
                await session.execute(
                    select(WorkspaceMember).where(WorkspaceMember.user_id == user.id)
                )
            ).scalars().all()
        )
        for member in members:
            member.role_id = admin_role.id

        await session.commit()
        print(
            f"{'created' if created else 'updated'} owner={email} "
            f"workspaces={len(members)} role=SUPER_ADMIN"
        )


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
