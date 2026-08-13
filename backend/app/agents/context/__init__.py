"""Fitting a conversation into a context window without losing the thread.

Four jobs, and they have to happen in this order or they undo each other:

1. **estimate** what the conversation costs;
2. **score** each message for how much this turn actually needs it;
3. **drop** the cheapest-scoring messages until it fits — dropping tool calls
   and their results *together*, never one without the other;
4. **repair** whatever pairing the dropping broke.

Step 4 exists because step 3 can orphan a tool result whose call was scored out
from under it, and most providers reject a conversation with an unpaired call
outright — as a malformed-request error that surfaces nowhere near the cause.
"""

from app.agents.context.budget import (
    CHARS_PER_TOKEN,
    estimate_context_tokens,
    estimate_message_tokens,
    estimate_text_tokens,
)
from app.agents.context.compactor import CompactionResult, compact_conversation
from app.agents.context.messages import ContextMessage, MessageKind
from app.agents.context.relevance import context_terms, score_message

__all__ = [
    "CHARS_PER_TOKEN",
    "CompactionResult",
    "ContextMessage",
    "MessageKind",
    "compact_conversation",
    "context_terms",
    "estimate_context_tokens",
    "estimate_message_tokens",
    "estimate_text_tokens",
    "score_message",
]
