from __future__ import annotations

from enum import StrEnum
from typing import Any

from app.models.conversation import ConversationMode


class ChatActionType(StrEnum):
    RUN_ANALYSIS = "RUN_ANALYSIS"
    OPEN_SYMBOL = "OPEN_SYMBOL"
    VIEW_RECOMMENDATION = "VIEW_RECOMMENDATION"


def propose_chat_actions(
    *,
    mode: ConversationMode,
    user_content: str,
    symbol: str | None,
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    lowered = user_content.lower()
    if symbol and ("chart" in lowered or "price" in lowered):
        actions.append({"type": ChatActionType.OPEN_SYMBOL.value, "symbol": symbol.upper()})
    if mode == ConversationMode.ANALYZE or "analyze" in lowered or "analysis" in lowered:
        actions.append(
            {
                "type": ChatActionType.RUN_ANALYSIS.value,
                "symbol": (symbol or "EURUSD").upper(),
            }
        )
    return actions
