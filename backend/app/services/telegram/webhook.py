"""Turning an inbound Telegram update into a turn with the agent.

The flow, and the reason for each step:

1. **The update is untrusted text.** It carries a sender id and a body, both
   from whoever holds that account, and neither is a fact about this system.
2. **Resolve, never trust.** The sender id is looked up; the workspace is the
   answer. Nothing in the message is allowed to name a workspace.
3. **An unknown sender learns nothing.** The reply is identical whether the
   account is unlinked or the code was wrong or the workspace does not exist.
   A distinguishable error would let anyone probe for linked accounts.
4. **Then it is an ordinary chat turn** — the same conversation, the same
   recall, the same model as the web client, with RLS bound to the resolved
   workspace.

Everything here answers; nothing initiates.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ProviderConfigurationError
from app.core.symbols import DEFAULT_SYMBOL
from app.core.tenant import TenantResolutionError
from app.core.tenant_rls import bind_workspace_rls
from app.models.conversation import Conversation, ConversationMode
from app.providers.llm.factory import get_llm_provider
from app.services.chat_service import run_chat_turn
from app.services.telegram.identity import consume_link_code, resolve_sender
from app.services.telegram.transport import TelegramTransport, reply_to

logger = structlog.get_logger(__name__)

__all__ = ["handle_update", "UpdateOutcome", "MESSAGES", "MAX_INBOUND_CHARS"]

#: Longer than this and the sender is not asking a question. Truncating rather
#: than refusing keeps a long paste usable, and the cap is what stops one
#: message consuming an analysis-sized token budget.
MAX_INBOUND_CHARS = 4000

#: Every operator-facing string in one place, in Arabic (the platform default).
#:
#: `unlinked` is deliberately the same answer for an unlinked account, a wrong
#: code and an expired one. Distinguishing them would let anyone with the bot's
#: handle test whether a given code or account exists.
MESSAGES = {
    "unlinked": (
        "لست مرتبطاً بحساب في Leovee.\n\n"
        "افتح المنصة ← الإعدادات ← تلجرام، وولّد رمز ربط، ثم أرسله هنا."
    ),
    "linked": (
        "تم الربط. اسألني عن الذهب — التحليل، أو مستوى معيّن، أو ما الذي يُبطل الفكرة.\n\n"
        "لن أرسل لك شيئاً ما لم تسألني."
    ),
    "empty": "أرسل سؤالاً نصياً.",
    "unsupported": "أتعامل مع النص فقط هنا.",
    "error": "تعذّر إكمال الطلب الآن. حاول مرة أخرى.",
}


@dataclass(frozen=True, slots=True)
class UpdateOutcome:
    """What happened, for the caller's logs. Never returned to the sender."""

    handled: bool
    action: str
    workspace_id: uuid.UUID | None = None


def _message_of(update: dict[str, Any]) -> dict[str, Any]:
    return update.get("message") or update.get("edited_message") or {}


def _sender_id(update: dict[str, Any]) -> int | None:
    sender = (_message_of(update).get("from") or {}).get("id")
    return int(sender) if isinstance(sender, int) else None


def _looks_like_a_link_code(body: str) -> bool:
    """A bare 8-character code, possibly behind /start or /link.

    Kept narrow on purpose: treating any short message as a code would send
    every "مرحبا" through the consuming path and burn rate limit on nothing.
    """
    candidate = body.strip().upper()
    for prefix in ("/START", "/LINK"):
        if candidate.startswith(prefix):
            candidate = candidate[len(prefix) :].strip()
    return len(candidate) == 8 and candidate.isalnum()


def _code_of(body: str) -> str:
    candidate = body.strip().upper()
    for prefix in ("/START", "/LINK"):
        if candidate.startswith(prefix):
            candidate = candidate[len(prefix) :].strip()
    return candidate


async def _conversation_for(
    session: AsyncSession, tenant: Any, telegram_user_id: int
) -> Conversation:
    """One conversation per linked account, reused.

    A new conversation per message would throw away the thread — the agent would
    not remember the level it named two messages ago, which is most of what
    makes a chat useful.
    """
    title = f"Telegram {telegram_user_id}"
    existing = await session.scalar(
        select(Conversation).where(
            Conversation.tenant_id == tenant.tenant_id,
            Conversation.workspace_id == tenant.workspace_id,
            Conversation.title == title,
        )
    )
    if existing is not None:
        return existing
    conversation = Conversation(
        id=uuid.uuid4(),
        tenant_id=tenant.tenant_id,
        workspace_id=tenant.workspace_id,
        user_id=tenant.user_id,
        title=title,
        mode=ConversationMode.ANALYZE,
        symbol=DEFAULT_SYMBOL,
    )
    session.add(conversation)
    await session.flush()
    return conversation


async def handle_update(
    session: AsyncSession,
    update: dict[str, Any],
    *,
    transport: TelegramTransport | None,
) -> UpdateOutcome:
    """Answer one inbound update. Never raises into the webhook."""
    message = _message_of(update)
    sender_id = _sender_id(update)
    if sender_id is None:
        # Channel posts, edits to other people's messages, joins. Nothing to do,
        # and nothing to say to a conversation that did not ask.
        return UpdateOutcome(handled=False, action="no_sender")

    body = message.get("text")
    if not isinstance(body, str) or not body.strip():
        await reply_to(transport, update, MESSAGES["unsupported" if message else "empty"])
        return UpdateOutcome(handled=True, action="non_text")
    body = body[:MAX_INBOUND_CHARS]

    resolution = await resolve_sender(session, sender_id)

    if resolution is None:
        if _looks_like_a_link_code(body):
            chat_id = (message.get("chat") or {}).get("id")
            linked = await consume_link_code(
                session,
                code=_code_of(body),
                telegram_user_id=sender_id,
                telegram_chat_id=int(chat_id) if isinstance(chat_id, int) else sender_id,
                username=(message.get("from") or {}).get("username"),
            )
            if linked is not None:
                await reply_to(transport, update, MESSAGES["linked"])
                return UpdateOutcome(
                    handled=True, action="linked", workspace_id=linked.workspace_id
                )
        # One answer for unlinked, wrong code and expired code alike.
        await reply_to(transport, update, MESSAGES["unlinked"])
        return UpdateOutcome(handled=True, action="unlinked")

    try:
        tenant = await resolution.to_tenant_context(session)
    except TenantResolutionError:
        # The account was linked but the user is no longer a member. Treated as
        # unlinked rather than as an error: the membership check is the
        # authority, and it just said no.
        await reply_to(transport, update, MESSAGES["unlinked"])
        return UpdateOutcome(handled=True, action="membership_revoked")

    await bind_workspace_rls(session, tenant)
    try:
        conversation = await _conversation_for(session, tenant, sender_id)
        result = await run_chat_turn(
            session,
            tenant,
            conversation,
            user_content=body,
            llm=get_llm_provider(),
        )
        answer = result.assistant_message.content
    except ProviderConfigurationError:
        await reply_to(transport, update, MESSAGES["error"])
        return UpdateOutcome(
            handled=True, action="llm_unavailable", workspace_id=tenant.workspace_id
        )
    except Exception as exc:  # noqa: BLE001 — a chat turn must not break the webhook
        logger.warning("telegram_turn_failed", error=str(exc)[:200])
        await reply_to(transport, update, MESSAGES["error"])
        return UpdateOutcome(handled=True, action="failed", workspace_id=tenant.workspace_id)

    await session.execute(
        text(
            "UPDATE telegram_links SET last_message_at = :now, updated_at = :now "
            "WHERE telegram_user_id = :tg"
        ),
        {"now": datetime.now(UTC), "tg": sender_id},
    )
    await reply_to(transport, update, answer)
    return UpdateOutcome(handled=True, action="answered", workspace_id=tenant.workspace_id)
