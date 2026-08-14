"""Telegram as a second door into the same agent (ADR 0009).

Not a bot with canned replies — the same analyst, the same constitution, the
same engines and the same tools, reached from a different place. A simplified
Telegram bot would be cheaper and would produce **two agents** whose behaviour
drifts apart, saying different things about the same market in two windows. That
is precisely the gap this migration exists to close.

**Conversation only.** Nothing here can start a conversation. The single
outbound function takes its destination from the message it is answering, so an
unsolicited notification is not something to remember not to write — it is
something there is no function for. D5 stands, enforced by shape.
"""

from app.services.telegram.identity import (
    LinkResolution,
    consume_link_code,
    issue_link_code,
    resolve_sender,
    revoke_link,
)
from app.services.telegram.transport import TelegramTransport, reply_to
from app.services.telegram.webhook import handle_update

__all__ = [
    "LinkResolution",
    "TelegramTransport",
    "consume_link_code",
    "handle_update",
    "issue_link_code",
    "reply_to",
    "resolve_sender",
    "revoke_link",
]
