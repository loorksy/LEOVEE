from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from typing import Any

from app.providers.llm.base import LLMMessage, LLMResponse, LLMStreamChunk


class FakeLLMProvider:
    """Test double only — inject via dependency overrides in tests."""

    def __init__(self, *, fail_times: int = 0, content: str | None = None) -> None:
        self.fail_times = fail_times
        self.calls = 0
        self._content = content

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        response_format: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
        timeout_seconds: float | None = None,
        max_retries: int | None = None,
    ) -> LLMResponse:
        self.calls += 1
        if self.fail_times > 0:
            self.fail_times -= 1
            raise RuntimeError("fake_primary_failure")
        last = messages[-1].content if messages else ""
        text = self._content if self._content is not None else f"Test narrative: {last[:80]}"
        structured = None
        if response_format is not None:
            structured = {
                "summary": f"Test analysis for: {last[:120]}",
                "confidence": 0.62,
                "bullets": ["test"],
            }
            text = (
                '{"summary":"Test analysis","confidence":0.62,"bullets":["test"]}'
                if self._content is None
                else self._content
            )
        return LLMResponse(
            content=text,
            model="test-model",
            provider="test",
            usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            structured=structured
            or {
                "summary": f"Test analysis for: {last[:120]}",
                "confidence": 0.62,
                "bullets": ["test"],
            },
        )

    async def stream(
        self,
        messages: list[LLMMessage],
        *,
        timeout_seconds: float | None = None,
    ) -> AsyncIterator[LLMStreamChunk]:
        result = await self.complete(messages)
        for word in result.content.split():
            yield LLMStreamChunk(text=word + " ", model=result.model, provider=result.provider)
        yield LLMStreamChunk(
            text="",
            model=result.model,
            provider=result.provider,
            done=True,
            usage=result.usage,
        )


class DecidingLLMProvider(FakeLLMProvider):
    """A double that answers the decision stage with a real, grounded plan.

    ``FakeLLMProvider`` returns a generic summary object, which the synthesizer
    correctly rejects — so every pipeline test using it exercises the fail-closed
    path and nothing past it. That leaves the *completed* path, which is the one
    users actually get, covered only in unit tests of its pieces.

    This double answers like a model that followed its instructions. It does not
    hardcode prices: it reads the measured-level menu out of the prompt it was
    sent and builds the plan from those levels. That makes the double depend on
    the same contract the real model does — if the menu stops being sent, or
    stops carrying usable levels, this stops producing a plan, which is exactly
    the failure a test should catch rather than paper over.
    """

    #: The marker the decision prompt uses to introduce the measured levels.
    LEVEL_MARKER = "المستويات المقاسة المتاحة"

    def __init__(self, *, direction: str = "BUY", confidence: float = 0.66) -> None:
        super().__init__()
        self.direction = direction
        self.confidence = confidence
        self.decisions = 0

    def _levels_from(self, messages: list[LLMMessage]) -> list[float]:
        for message in reversed(messages):
            if message.role != "user" or self.LEVEL_MARKER not in message.content:
                continue
            tail = message.content.split(self.LEVEL_MARKER, 1)[1]
            line = tail.split("\n", 1)[0]
            found: list[float] = []
            for token in re.findall(r"-?\d+\.\d+", line):
                found.append(float(token))
            return sorted(set(found))
        return []

    def _plan(self, levels: list[float]) -> dict[str, Any] | None:
        """Entry in the middle, stop and target at real measured levels.

        Widest available, deliberately: a plan built from the extremes of the
        menu clears the noise floor and the ATR target floor on any tape the
        engines could read, so a failure in this test means the *pipeline*
        rejected the plan rather than the fixture being marginal.
        """
        if len(levels) < 3:
            return None
        entry = levels[len(levels) // 2]
        below = [level for level in levels if level < entry]
        above = [level for level in levels if level > entry]
        if not below or not above:
            return None
        if self.direction == "BUY":
            return {"entry": entry, "stop": below[0], "targets": [above[-1]]}
        return {"entry": entry, "stop": above[-1], "targets": [below[0]]}

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        response_format: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
        timeout_seconds: float | None = None,
        max_retries: int | None = None,
    ) -> LLMResponse:
        levels = self._levels_from(messages)
        plan = self._plan(levels)
        if plan is None:
            # Not a decision stage call, or a menu this double cannot use. Fall
            # back rather than emit a plan from invented numbers — a double that
            # makes up prices would pass the grounding check by accident.
            return await super().complete(
                messages,
                response_format=response_format,
                tools=tools,
                timeout_seconds=timeout_seconds,
                max_retries=max_retries,
            )
        self.calls += 1
        self.decisions += 1
        payload = {
            "direction": self.direction,
            "confidence": self.confidence,
            "plan_type": "IMMEDIATE",
            "levels": plan,
            "rationale": "structure holds and the level is measured",
            "invalidation": f"a close beyond {plan['stop']:.2f}",
            "contradicting_evidence": [],
            "validity_candles": 12,
        }
        return LLMResponse(
            content=json.dumps(payload),
            model="test-decider",
            provider="test",
            usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            structured=payload,
        )
