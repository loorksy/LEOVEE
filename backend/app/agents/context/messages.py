"""The message shape the context layer works on.

Deliberately richer than ``LLMMessage``. Scoring needs to know what a message is
*about* — which symbol, which timeframe, which recommendation — and that cannot
be recovered from a role and a string without parsing prose, which is exactly
the kind of guess that makes a compactor drop the wrong turn.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

__all__ = ["MessageKind", "ContextMessage"]


class MessageKind(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    MEMORY = "memory"
    RECOMMENDATION = "recommendation"


@dataclass(slots=True)
class ContextMessage:
    id: str
    kind: MessageKind
    content: str
    #: Position in the original conversation. Ties in scoring break on this, so
    #: compaction is deterministic rather than dependent on dict ordering.
    sequence: int
    symbol: str | None = None
    timeframe: str | None = None
    recommendation_id: str | None = None
    analysis_id: str | None = None
    #: Never dropped, whatever it scores: the constitution, the current user
    #: message, an explicit user instruction that still governs the run.
    important: bool = False
    #: Candles and indicator dumps from an *earlier* turn. They are large,
    #: they are stale, and the live ones are already in this turn's evidence —
    #: keeping them spends the budget on numbers that are actively wrong.
    historical_market_data: bool = False
    #: Links a call to its result. Both sides carry the same id.
    tool_call_id: str | None = None
    tool_arguments: str = ""
    metadata: dict[str, str] = field(default_factory=dict)
