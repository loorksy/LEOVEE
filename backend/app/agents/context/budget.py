"""What a conversation costs, before sending it.

A four-characters-per-token estimate rather than a real tokenizer. It is
approximate, and that is acceptable here for a specific reason: it is used to
decide *what to drop*, and being 10% wrong changes which message sits at the
margin, not whether the compaction works. Loading a tokenizer per provider — and
keeping it in step with whichever model the router picked this minute — buys
precision the decision does not need.

Arabic runs closer to three characters per token than four, so the estimate
under-counts for this product's default locale. Under-counting is the wrong
direction to be wrong in, so the per-message overhead is charged generously.
"""

from __future__ import annotations

from collections.abc import Iterable
from math import ceil

from app.agents.context.messages import ContextMessage

__all__ = [
    "CHARS_PER_TOKEN",
    "MESSAGE_OVERHEAD_TOKENS",
    "estimate_text_tokens",
    "estimate_message_tokens",
    "estimate_context_tokens",
]

CHARS_PER_TOKEN = 4
#: Role, delimiters and framing every provider adds per message.
MESSAGE_OVERHEAD_TOKENS = 6


def estimate_text_tokens(text: str) -> int:
    return max(1, ceil(len(text) / CHARS_PER_TOKEN)) if text else 0


def estimate_message_tokens(message: ContextMessage) -> int:
    return (
        estimate_text_tokens(message.content)
        + MESSAGE_OVERHEAD_TOKENS
        + estimate_text_tokens(message.tool_arguments)
    )


def estimate_context_tokens(messages: Iterable[ContextMessage]) -> int:
    return sum(estimate_message_tokens(message) for message in messages)
