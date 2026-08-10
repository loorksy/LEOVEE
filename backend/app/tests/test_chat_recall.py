from __future__ import annotations

from app.models.conversation import Conversation, ConversationMode
from app.providers.llm.base import LLMMessage
from app.services.chat_service import RECALL_CONTEXT_LABEL, build_llm_messages


def test_build_llm_messages_injects_recall_bundle() -> None:
    conv = Conversation(
        tenant_id=None,  # type: ignore[arg-type]
        workspace_id=None,  # type: ignore[arg-type]
        user_id=None,  # type: ignore[arg-type]
        title="t",
        mode=ConversationMode.CHAT,
        symbol="EURUSD",
    )
    recall = {
        "label": RECALL_CONTEXT_LABEL,
        "count": 1,
        "items": [{"key": "symbol:EURUSD", "content": {"note": "lesson"}}],
    }
    messages = build_llm_messages(
        conversation=conv,
        recall=recall,
        history=[],
        user_content="What is bias?",
    )
    system = messages[0].content
    assert RECALL_CONTEXT_LABEL in system
    assert "symbol:EURUSD" in system
    assert messages[-1] == LLMMessage(role="user", content="What is bias?")
