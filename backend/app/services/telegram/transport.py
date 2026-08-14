"""The only way anything in this system reaches Telegram.

One function, and it takes `chat_id` from the update it is replying to. That is
the whole design: there is no way to *address* a conversation that has not just
spoken, so a proactive notification cannot be written by accident. It would have
to be a new function, and the conformance guard is what notices.

The bot token is a platform secret rather than an environment variable, so it
rotates without a redeploy and never appears in a process listing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
import structlog

from app.core.errors import ProviderConfigurationError

logger = structlog.get_logger(__name__)

__all__ = ["TelegramTransport", "reply_to", "TELEGRAM_API_BASE", "MAX_MESSAGE_CHARS"]

TELEGRAM_API_BASE = "https://api.telegram.org"

#: Telegram's own hard limit. A longer reply is split rather than truncated: an
#: analysis cut mid-sentence at 4096 characters loses its invalidation level,
#: which is the part the reader most needs.
MAX_MESSAGE_CHARS = 4096

_TIMEOUT_SECONDS = 20.0


@dataclass(frozen=True, slots=True)
class TelegramTransport:
    bot_token: str
    base_url: str = TELEGRAM_API_BASE
    timeout_seconds: float = _TIMEOUT_SECONDS

    @property
    def _endpoint(self) -> str:
        return f"{self.base_url}/bot{self.bot_token}/sendMessage"

    async def _post(self, chat_id: int, text: str) -> None:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                self._endpoint,
                json={
                    "chat_id": chat_id,
                    "text": text,
                    # Deliberately plain text. The agent's replies contain price
                    # levels with underscores and asterisks in them, and Markdown
                    # parsing turns an unbalanced one into a 400 that loses the
                    # whole answer.
                    "disable_web_page_preview": True,
                },
            )
        if response.status_code >= 400:
            # Logged, never raised into the analysis: a failed reply loses one
            # message, and raising would additionally lose the run that produced
            # it and everything it recorded.
            logger.warning(
                "telegram_send_failed",
                status=response.status_code,
                detail=response.text[:200],
            )


def _chunks(text: str, size: int = MAX_MESSAGE_CHARS) -> list[str]:
    """Split on line boundaries where possible, so a level never breaks in half."""
    if len(text) <= size:
        return [text]
    out: list[str] = []
    remaining = text
    while len(remaining) > size:
        window = remaining[:size]
        cut = window.rfind("\n")
        if cut < size // 2:
            cut = size
        out.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip("\n")
    if remaining:
        out.append(remaining)
    return out


async def reply_to(transport: TelegramTransport | None, update: dict[str, Any], text: str) -> int:
    """Answer the message in `update`. Returns how many parts were sent.

    The destination is read out of the update rather than passed in, which is
    what makes an unsolicited send impossible to express: without an inbound
    message there is no chat id, and there is no other function that has one.
    """
    if transport is None:
        raise ProviderConfigurationError("Telegram bot token is not configured")
    chat_id = _chat_id_of(update)
    if chat_id is None:
        return 0
    parts = _chunks(text.strip() or "…")
    for part in parts:
        await transport._post(chat_id, part)
    return len(parts)


def _chat_id_of(update: dict[str, Any]) -> int | None:
    message = update.get("message") or update.get("edited_message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    return int(chat_id) if isinstance(chat_id, int) else None
