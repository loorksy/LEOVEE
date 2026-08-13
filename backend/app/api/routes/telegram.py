"""The Telegram surface: one webhook in, and the linking controls (ADR 0009).

The webhook is the only unauthenticated route in the application, which makes
its guard the whole security boundary:

**The secret token is checked before the body is read.** Telegram echoes the
value registered with `setWebhook` in `X-Telegram-Bot-Api-Secret-Token`. Without
that check the endpoint is a public URL anyone can POST a forged "message" to,
naming any sender id they like — and the sender id is what resolves to a
workspace. Comparing it in constant time, and rejecting before parsing, keeps
the attack surface to a header comparison.

**With no secret configured the endpoint refuses everything.** Not "allow while
unconfigured" — an unconfigured deployment would be wide open, and open by
default is how this kind of endpoint gets forgotten in staging.

**The reply to Telegram is always 200.** Telegram retries a non-2xx, and a
message that failed to process will fail identically on the retry while the
queue backs up behind it. What went wrong goes to the logs; the delivery is
acknowledged.
"""

from __future__ import annotations

import hmac
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_workspace_context
from app.core.config import get_settings
from app.core.tenant import TenantContext
from app.core.tenant_rls import bind_workspace_rls
from app.infrastructure.database import get_db_session
from app.models.telegram import TelegramLink
from app.services.telegram.identity import issue_link_code, revoke_link
from app.services.telegram.transport import TelegramTransport
from app.services.telegram.webhook import handle_update

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/telegram", tags=["telegram"])


class LinkCodeResponse(BaseModel):
    code: str
    expires_at: str
    #: Stated to the user at the moment they generate a code, because it is when
    #: they are deciding whether to link at all.
    note: str = "الرمز صالح لعشر دقائق ويُستخدم مرة واحدة. لن يصلك شيء ما لم تسأل."


class LinkedAccount(BaseModel):
    telegram_user_id: int
    telegram_username: str | None
    linked_at: str
    last_message_at: str | None


def _transport() -> TelegramTransport | None:
    token = get_settings().telegram_bot_token
    return TelegramTransport(bot_token=token) if token else None


@router.post("/webhook", status_code=status.HTTP_200_OK)
async def telegram_webhook(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    x_telegram_bot_api_secret_token: Annotated[str | None, Header()] = None,
) -> dict[str, bool]:
    settings = get_settings()
    expected = settings.telegram_webhook_secret
    if not expected:
        # Refusing while unconfigured, not allowing. An open webhook forgotten
        # in staging is a workspace takeover waiting for someone to find the URL.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if not x_telegram_bot_api_secret_token or not hmac.compare_digest(
        x_telegram_bot_api_secret_token, expected
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    try:
        update: dict[str, Any] = await request.json()
    except Exception:  # noqa: BLE001 — a malformed body is not worth a retry
        return {"ok": True}
    if not isinstance(update, dict):
        return {"ok": True}

    try:
        outcome = await handle_update(session, update, transport=_transport())
        await session.commit()
        logger.info("telegram_update", action=outcome.action)
    except Exception as exc:  # noqa: BLE001 — never make Telegram retry a poison message
        await session.rollback()
        logger.warning("telegram_webhook_failed", error=str(exc)[:200])
    # Always 200: a non-2xx makes Telegram retry, and a message that failed once
    # fails identically on the retry while the queue backs up behind it.
    return {"ok": True}


@router.post("/link-code", response_model=LinkCodeResponse)
async def create_link_code(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(get_workspace_context)],
) -> LinkCodeResponse:
    """Mint a one-time code, inside the platform where the user is authenticated."""
    issued = await issue_link_code(session, tenant, user_id=tenant.user_id)
    await session.commit()
    return LinkCodeResponse(code=issued.code, expires_at=issued.expires_at.isoformat())


@router.get("/links", response_model=list[LinkedAccount])
async def list_links(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(get_workspace_context)],
) -> list[LinkedAccount]:
    await bind_workspace_rls(session, tenant)
    rows = (
        await session.execute(
            select(TelegramLink).where(
                TelegramLink.tenant_id == tenant.tenant_id,
                TelegramLink.workspace_id == tenant.workspace_id,
                TelegramLink.revoked_at.is_(None),
            )
        )
    ).scalars()
    return [
        LinkedAccount(
            telegram_user_id=row.telegram_user_id,
            telegram_username=row.telegram_username,
            linked_at=row.linked_at.isoformat(),
            last_message_at=row.last_message_at.isoformat() if row.last_message_at else None,
        )
        for row in rows
    ]


@router.delete("/links/{telegram_user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_link(
    telegram_user_id: int,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant: Annotated[TenantContext, Depends(get_workspace_context)],
) -> None:
    """Cut a linked account off immediately.

    Whoever holds the Telegram account holds the agent, and no design avoids
    that. Being able to sever it in one click is the mitigation.
    """
    if not await revoke_link(session, tenant, telegram_user_id=telegram_user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    await session.commit()
