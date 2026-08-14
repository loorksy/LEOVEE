"""The tool-calling loop: let the model browse the data, within a hard budget.

``LLMToolCall`` existed with nothing to dispatch it. This is the dispatcher.

**Three bounds, and each closes a different failure.**

*Iterations.* A model that keeps asking one more question never returns. The cap
is absolute and independent of the token budget, because a loop of cheap calls
exhausts wall-clock and a request timeout long before it exhausts tokens.

*Tokens.* The router already meters spend per task. The loop reports into the
same accounting rather than keeping its own, or a runaway loop would drain the
analysis budget mid-run and the router would report a healthy total.

*Repeats.* The same tool with the same arguments returns the same answer — the
tools are pure reads of stored candles. Re-running it is pure waste, so the
cached result is returned with a note. Answering identically without the note
invites the model to loop on it forever, which is how a stuck run stays stuck.

**Tool pairing is repaired, not assumed.** Every assistant message announcing
tool calls must be followed by exactly one result per call, in the same order.
A truncated stream, a provider that drops a call, or a mid-flight failure leaves
a dangling call — and most providers reject the next request outright with a
malformed-history error, which surfaces as an authentication-shaped failure
several layers away from the cause. Synthesising an explicit error result for
the orphan keeps the conversation well-formed and tells the model what happened.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from app.agents.tools.registry import ToolContext, dispatch_tool, tool_definitions
from app.observability.prometheus import tool_loop_iterations
from app.providers.llm.base import LLMMessage, LLMResponse, LLMToolCall

__all__ = [
    "MAX_TOOL_ITERATIONS",
    "ToolCallRecord",
    "ToolLoopResult",
    "run_tool_loop",
    "repair_tool_pairs",
]

#: Absolute ceiling on browse-and-answer rounds.
#:
#: Five is enough to look at three timeframes and a chart and still answer. It
#: is deliberately not configurable per call: an "unlimited for this one run"
#: switch is the shape every runaway loop takes.
MAX_TOOL_ITERATIONS = 5

#: The loop stops asking for more when this little of the budget remains, so the
#: final answer is still affordable. A loop that spends its last token on a tool
#: result leaves the model unable to say anything about it.
MIN_TOKENS_FOR_ANSWER = 2_000

CompleteFn = Callable[[list[LLMMessage], list[dict[str, Any]]], Awaitable[LLMResponse]]


@dataclass(slots=True)
class ToolCallRecord:
    name: str
    arguments: dict[str, Any]
    iteration: int
    cached: bool = False
    error: str | None = None


@dataclass(slots=True)
class ToolLoopResult:
    response: LLMResponse
    messages: list[LLMMessage]
    calls: list[ToolCallRecord] = field(default_factory=list)
    iterations: int = 0
    #: Set when the loop stopped on a bound rather than because the model
    #: finished. Never silent: the caller has to be able to tell a considered
    #: answer from a truncated one.
    stopped_on: str | None = None

    @property
    def truncated(self) -> bool:
        return self.stopped_on is not None


def _key(name: str, arguments: dict[str, Any]) -> str:
    return f"{name}:{json.dumps(arguments, sort_keys=True, default=str)}"


def _result_message(call: LLMToolCall, payload: dict[str, Any]) -> LLMMessage:
    """A tool result as *structure*, not as JSON stuffed into a body.

    The id has to be a field. Embedding it in the content produced a
    conversation both providers rejected on the second turn — Anthropic takes
    only user and assistant roles, OpenAI wants `tool_call_id` as a field — and
    the rejection surfaced as a malformed-request error far from this function.
    """
    return LLMMessage(
        role="tool",
        content=json.dumps(payload, ensure_ascii=False, default=str),
        tool_call_id=call.id,
        tool_name=call.name,
    )


def repair_tool_pairs(
    messages: list[LLMMessage], announced: list[LLMToolCall], answered: set[str]
) -> list[LLMMessage]:
    """Give every announced call a result, inventing an error for the orphans."""
    repaired = list(messages)
    for call in announced:
        if call.id in answered:
            continue
        repaired.append(
            _result_message(
                call,
                {
                    "error": "tool_result_missing",
                    "detail": (
                        "This call produced no result — the run was interrupted "
                        "before it completed. Do not assume its output."
                    ),
                },
            )
        )
    return repaired


async def run_tool_loop(
    *,
    complete: CompleteFn,
    messages: list[LLMMessage],
    context: ToolContext,
    max_iterations: int = MAX_TOOL_ITERATIONS,
    token_budget: int | None = None,
) -> ToolLoopResult:
    """Run the model until it answers without asking for another tool."""
    conversation = list(messages)
    definitions = tool_definitions()
    calls: list[ToolCallRecord] = []
    cache: dict[str, dict[str, Any]] = {}
    spent = 0
    iteration = 0
    response: LLMResponse | None = None

    while iteration < max_iterations:
        response = await complete(conversation, definitions)
        spent += int(response.usage.get("total_tokens") or 0)

        if not response.tool_calls:
            tool_loop_iterations.observe(iteration)
            return ToolLoopResult(
                response=response,
                messages=conversation,
                calls=calls,
                iterations=iteration,
            )

        iteration += 1
        # The assistant turn must carry the calls it made, or the results that
        # follow answer nothing and the provider rejects the pairing.
        conversation.append(
            LLMMessage(
                role="assistant",
                content=response.content or "",
                tool_calls=list(response.tool_calls),
            )
        )

        answered: set[str] = set()
        for call in response.tool_calls:
            key = _key(call.name, call.arguments)
            if key in cache:
                payload = {
                    **cache[key],
                    "note": (
                        "Identical call already made in this run; the cached "
                        "result is returned. Ask something different or answer."
                    ),
                }
                calls.append(ToolCallRecord(call.name, call.arguments, iteration, cached=True))
            else:
                payload = await dispatch_tool(context, call.name, call.arguments)
                cache[key] = payload
                calls.append(
                    ToolCallRecord(
                        call.name,
                        call.arguments,
                        iteration,
                        error=str(payload.get("error")) if payload.get("error") else None,
                    )
                )
            conversation.append(_result_message(call, payload))
            answered.add(call.id)

        conversation = repair_tool_pairs(conversation, response.tool_calls, answered)

        if token_budget is not None and token_budget - spent < MIN_TOKENS_FOR_ANSWER:
            break

    # Out of iterations or out of budget. Ask once more with no tools attached,
    # so the model has to answer from what it already gathered rather than
    # returning another unanswerable request.
    assert response is not None
    stopped_on = (
        "token_budget"
        if token_budget is not None and (token_budget - spent < MIN_TOKENS_FOR_ANSWER)
        else "max_iterations"
    )
    conversation.append(
        LLMMessage(
            role="user",
            content=(
                "No further tool calls are available. Answer now using the "
                "evidence already gathered, and say plainly what you could not "
                "check."
            ),
        )
    )
    final = await complete(conversation, [])
    tool_loop_iterations.observe(iteration)
    return ToolLoopResult(
        response=final,
        messages=conversation,
        calls=calls,
        iterations=iteration,
        stopped_on=stopped_on,
    )
