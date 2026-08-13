"""Tool conversations, in each provider's own wire format.

These pin defects that a review found and no test would have: the tool loop
built a conversation both providers reject, and the tool *definitions* were in
Anthropic's shape while OpenAI is the preferred provider. Both failed as a 400,
which classifies non-retryable — so the decision stage returned
`provider_bad_request` without one repair attempt, and the tools looked wired.
"""

from __future__ import annotations

import json

import pytest

from app.agents.tools.registry import tool_definitions
from app.providers.llm.base import LLMMessage, LLMToolCall
from app.providers.llm.common import (
    to_anthropic_messages,
    to_openai_messages,
    to_openai_tools,
)

pytestmark = pytest.mark.no_db

CALL = LLMToolCall(id="call_1", name="get_candles", arguments={"timeframe": "M15"})
CONVERSATION = [
    LLMMessage(role="system", content="rules"),
    LLMMessage(role="user", content="analyse"),
    LLMMessage(role="assistant", content="", tool_calls=[CALL]),
    LLMMessage(
        role="tool", content='{"candles": []}', tool_call_id="call_1", tool_name="get_candles"
    ),
]


# --- OpenAI ------------------------------------------------------------------


def test_openai_puts_the_call_id_in_a_field_not_the_body() -> None:
    payload = to_openai_messages(CONVERSATION)
    result = payload[-1]
    assert result["role"] == "tool"
    assert result["tool_call_id"] == "call_1"


def test_openai_carries_the_tool_calls_on_the_assistant_turn() -> None:
    """Without them the result that follows answers nothing."""
    assistant = to_openai_messages(CONVERSATION)[2]
    assert assistant["tool_calls"][0]["id"] == "call_1"
    assert assistant["tool_calls"][0]["function"]["name"] == "get_candles"
    assert json.loads(assistant["tool_calls"][0]["function"]["arguments"]) == {"timeframe": "M15"}
    # A null content beside tool_calls is rejected outright.
    assert assistant["content"] == ""


def test_tool_definitions_are_translated_to_openais_nested_form() -> None:
    translated = to_openai_tools(tool_definitions())
    assert translated
    for tool in translated:
        assert tool["type"] == "function"
        assert tool["function"]["name"]
        assert isinstance(tool["function"]["parameters"], dict)


def test_translating_twice_does_not_corrupt() -> None:
    once = to_openai_tools(tool_definitions())
    assert to_openai_tools(once) == once


# --- Anthropic ---------------------------------------------------------------


def test_anthropic_never_emits_a_tool_role() -> None:
    """The Messages API accepts only user and assistant."""
    payload = to_anthropic_messages(CONVERSATION)
    assert {m["role"] for m in payload} <= {"user", "assistant"}


def test_anthropic_expresses_a_result_as_a_user_turn_with_blocks() -> None:
    payload = to_anthropic_messages(CONVERSATION)
    result = payload[-1]
    assert result["role"] == "user"
    block = result["content"][0]
    assert block["type"] == "tool_result"
    assert block["tool_use_id"] == "call_1"


def test_anthropic_puts_tool_use_blocks_on_the_assistant_turn() -> None:
    assistant = to_anthropic_messages(CONVERSATION)[1]
    assert assistant["role"] == "assistant"
    block = assistant["content"][0]
    assert block["type"] == "tool_use"
    assert block["name"] == "get_candles"
    assert block["input"] == {"timeframe": "M15"}


def test_consecutive_results_merge_into_one_user_turn() -> None:
    """Two user turns in a row are rejected."""
    conversation = [
        LLMMessage(role="user", content="analyse"),
        LLMMessage(
            role="assistant",
            content="",
            tool_calls=[CALL, LLMToolCall(id="call_2", name="get_structure", arguments={})],
        ),
        LLMMessage(role="tool", content="{}", tool_call_id="call_1"),
        LLMMessage(role="tool", content="{}", tool_call_id="call_2"),
    ]
    payload = to_anthropic_messages(conversation)
    roles = [m["role"] for m in payload]
    assert roles == ["user", "assistant", "user"]
    assert len(payload[-1]["content"]) == 2


def test_the_system_turn_is_removed_because_it_travels_separately() -> None:
    assert all(m["role"] != "system" for m in to_anthropic_messages(CONVERSATION))
