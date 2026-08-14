"""The dev impersonation header is opt-in, off by default.

`X-Leovee-User-Id` lets a request name any user with no token. That is only
acceptable as an explicit, off-by-default convenience: a deployment that forgot
`ENVIRONMENT=production` (the default is "development") must NOT thereby accept
the header. The gate is `dev_auth_bypass`, and these tests pin both directions.
"""

from __future__ import annotations

import uuid
from typing import Any, cast

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.core.config import Settings

pytestmark = pytest.mark.no_db


def _settings(**overrides: Any) -> Settings:
    base = {"environment": "development", "dev_auth_bypass": False}
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


async def test_header_is_ignored_when_bypass_is_off() -> None:
    """The insecure default: no bypass flag, so the header authenticates nobody."""
    with pytest.raises(HTTPException) as excinfo:
        await get_current_user_id(
            settings=_settings(dev_auth_bypass=False),
            session=cast(AsyncSession, None),
            credentials=None,
            x_leovee_user_id=str(uuid.uuid4()),
        )
    assert excinfo.value.status_code == 401


async def test_header_works_only_with_explicit_opt_in() -> None:
    user_id = uuid.uuid4()
    resolved = await get_current_user_id(
        settings=_settings(environment="test", dev_auth_bypass=True),
        session=cast(AsyncSession, None),
        credentials=None,
        x_leovee_user_id=str(user_id),
    )
    assert resolved == user_id


async def test_bypass_flag_does_nothing_outside_a_dev_environment() -> None:
    """Even armed, the header is inert unless the environment is dev/test."""
    with pytest.raises(HTTPException) as excinfo:
        await get_current_user_id(
            settings=_settings(environment="production", dev_auth_bypass=True),
            session=cast(AsyncSession, None),
            credentials=None,
            x_leovee_user_id=str(uuid.uuid4()),
        )
    assert excinfo.value.status_code == 401
