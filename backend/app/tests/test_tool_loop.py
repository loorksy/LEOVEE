"""The tool-calling loop: bounded, deduplicated, and never left malformed."""

from __future__ import annotations

import json
from typing import Any, cast

import pytest

from app.agents.tools.loop import (
    MAX_TOOL_ITERATIONS,
    ToolLoopResult,
    repair_tool_pairs,
    run_tool_loop,
)
from app.agents.tools.registry import ToolContext
from app.providers.llm.base import LLMMessage, LLMResponse, LLMToolCall

pytestmark = pytest.mark.no_db


class _Model:
    """A scripted provider: each entry is one turn's reply."""

    def __init__(self, turns: list[LLMResponse]) -> None:
        self._turns = list(turns)
        self.calls: list[tuple[int, int]] = []
        self.tool_counts: list[int] = []

    async def __call__(
        self, messages: list[LLMMessage], tools: list[dict[str, Any]]
    ) -> LLMResponse:
        self.calls.append((len(messages), len(tools)))
        self.tool_counts.append(len(tools))
        if self._turns:
            return self._turns.pop(0)
        return _answer("done")


def _answer(content: str) -> LLMResponse:
    return LLMResponse(content=content, model="m", provider="p", usage={"total_tokens": 100})


def _wants(name: str, call_id: str = "c1", **arguments: Any) -> LLMResponse:
    return LLMResponse(
        content="",
        model="m",
        provider="p",
        usage={"total_tokens": 100},
        tool_calls=[LLMToolCall(id=call_id, name=name, arguments=arguments)],
    )


#: The scripted tool names in this module never reach a handler, so a context
#: holding a stand-in session exercises the loop's own logic without a database.
_CONTEXT = ToolContext(session=cast(Any, None))


async def _run(model: _Model, **kwargs: Any) -> ToolLoopResult:
    return await run_tool_loop(
        complete=model,
        messages=[LLMMessage(role="user", content="analyse")],
        context=_CONTEXT,
        **kwargs,
    )


async def test_a_model_that_asks_nothing_returns_immediately() -> None:
    model = _Model([_answer("BUY")])
    result = await _run(model)
    assert result.response.content == "BUY"
    assert result.iterations == 0
    assert result.calls == []
    assert result.truncated is False


async def test_an_unknown_tool_comes_back_as_data_not_an_exception() -> None:
    """A model that guesses a tool name should be corrected, not abort the run."""
    model = _Model([_wants("get_the_future"), _answer("BUY")])
    result = await _run(model)
    assert result.calls[0].error == "unknown_tool"
    assert result.response.content == "BUY"


async def test_a_repeated_identical_call_is_answered_from_cache_and_says_so() -> None:
    """The tools are pure reads. Re-running one is waste; hiding that invites a loop."""
    model = _Model([_wants("get_the_future", "a"), _wants("get_the_future", "b"), _answer("BUY")])
    result = await _run(model)
    assert [c.cached for c in result.calls] == [False, True]
    cached_message = json.loads(result.messages[-1].content)
    assert "note" in cached_message["result"]


async def test_the_iteration_cap_is_absolute() -> None:
    """A model that keeps asking one more question never returns on its own."""
    model = _Model([_wants("x", f"c{i}") for i in range(MAX_TOOL_ITERATIONS + 3)])
    result = await _run(model)
    assert result.iterations == MAX_TOOL_ITERATIONS
    assert result.stopped_on == "max_iterations"
    assert result.truncated is True


async def test_the_final_turn_is_asked_with_no_tools_attached() -> None:
    """Otherwise the model answers a forced turn with yet another request."""
    model = _Model([_wants("x", f"c{i}") for i in range(MAX_TOOL_ITERATIONS + 3)])
    await _run(model)
    assert model.tool_counts[-1] == 0
    assert model.tool_counts[0] > 0


async def test_the_loop_stops_before_it_cannot_afford_an_answer() -> None:
    """Spending the last token on a tool result leaves nothing to say about it."""
    model = _Model([_wants("x", f"c{i}") for i in range(6)])
    result = await _run(model, token_budget=2_050)
    assert result.stopped_on == "token_budget"
    assert result.iterations < MAX_TOOL_ITERATIONS


def test_an_orphaned_tool_call_is_given_an_explicit_error_result() -> None:
    """Most providers reject a dangling call with a malformed-history error that
    surfaces several layers from the cause. Repairing it keeps the shape valid
    and tells the model what actually happened."""
    announced = [
        LLMToolCall(id="a", name="get_candles", arguments={}),
        LLMToolCall(id="b", name="get_indicators", arguments={}),
    ]
    repaired = repair_tool_pairs([], announced, answered={"a"})
    assert len(repaired) == 1
    payload = json.loads(repaired[0].content)
    assert payload["tool_call_id"] == "b"
    assert payload["result"]["error"] == "tool_result_missing"
    assert "Do not assume" in payload["result"]["detail"]


def test_a_fully_answered_turn_needs_no_repair() -> None:
    announced = [LLMToolCall(id="a", name="get_candles", arguments={})]
    assert repair_tool_pairs([], announced, answered={"a"}) == []
