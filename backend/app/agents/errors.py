"""One vocabulary for every way a stage can fail.

A specialist that returns ``None`` tells the operator nothing. The cause has to
survive into the result envelope, the trace and the logs, or a degraded run
looks identical to a quiet market.

**Two audiences, kept strictly apart.** ``operator_detail`` is the technical
cause — provider messages, status codes, module names — and goes to traces and
logs only. ``user_message`` is a safe sentence for the interface, carrying no
provider payload, no key fragment and no internal name.

Two classification rules below are worth more than the rest of the module, and
both were bought by getting them wrong:

**Billing exhaustion is not a rate limit**, though it arrives as the same HTTP
429. "Try again shortly" is wrong *forever* when the account is out of credit,
so it is matched before the rate-limit branch precisely because they share a
status code.

**A provider 4xx is not an unknown error.** A bad model id, an unsupported
parameter or an oversized context surfaced as "unexpected error, retrying will
not help" with nothing pointing at the model configuration that caused it.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "FailureCode",
    "AgentStage",
    "StageFailure",
    "classify_error",
    "stage_failure_from_error",
    "stage_timeout_failure",
    "ledger_silent_timeout",
    "is_retryable",
]


class FailureCode(StrEnum):
    AUTH = "auth"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    NETWORK = "network"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    #: The provider rejected the request itself: bad model id, unsupported
    #: parameter, oversized context.
    PROVIDER_BAD_REQUEST = "provider_bad_request"
    #: Out of credit. Retrying never helps, however long you wait.
    PROVIDER_BILLING = "provider_billing"
    INVALID_PAYLOAD = "invalid_payload"
    SCHEMA_MISMATCH = "schema_mismatch"
    STALE_DATA = "stale_data"
    #: The session is closed. Not a fault — there is simply no tape to read.
    MARKET_CLOSED = "market_closed"
    INSUFFICIENT_DATA = "insufficient_data"
    ENGINE_UNAVAILABLE = "engine_unavailable"
    RESOURCE_EXHAUSTED = "resource_exhausted"
    CANCELLED = "cancelled"
    CONFIGURATION = "configuration"
    UNKNOWN = "unknown"


class AgentStage(StrEnum):
    GENERAL = "general"
    MARKET_DATA = "market_data"
    STRUCTURE = "structure"
    LIQUIDITY = "liquidity"
    SUPPLY_DEMAND = "supply_demand"
    GEOMETRY = "geometry"
    MULTI_TIMEFRAME = "multi_timeframe"
    NEWS = "news"
    RISK = "risk"
    #: Replaces AiChart's `execution_guard`: the same arithmetic, none of the
    #: order machinery (D4).
    PLAN_SANITY = "plan_sanity"
    TIMEFRAME_SELECTION = "timeframe_selection"
    FINAL_DECISION = "final_decision"
    DRAWING = "drawing"
    TRANSPORT = "transport"


_RETRYABLE = frozenset(
    {
        FailureCode.RATE_LIMIT,
        FailureCode.TIMEOUT,
        FailureCode.NETWORK,
        FailureCode.PROVIDER_UNAVAILABLE,
        FailureCode.STALE_DATA,
        FailureCode.RESOURCE_EXHAUSTED,
        FailureCode.INVALID_PAYLOAD,
    }
)

#: Kept short: an operator detail is for a log line, not a payload dump, and an
#: unbounded provider message can carry the whole request back into the trace.
MAX_DETAIL_CHARS = 500


def is_retryable(code: FailureCode) -> bool:
    return code in _RETRYABLE


@dataclass(frozen=True, slots=True)
class StageFailure:
    stage: AgentStage
    code: FailureCode
    retryable: bool
    #: Technical cause. Traces and logs only — never rendered to a user.
    operator_detail: str
    provider: str | None = None

    def to_dict(self) -> dict[str, str | bool | None]:
        return {
            "stage": self.stage.value,
            "code": self.code.value,
            "retryable": self.retryable,
            "operator_detail": self.operator_detail,
            "provider": self.provider,
        }


_STATUS = re.compile(r"\b(\d{3})\b")


def _has_status(message: str, codes: tuple[str, ...]) -> bool:
    return any(match.group(1) in codes for match in _STATUS.finditer(message))


def classify_error(error: BaseException | str) -> tuple[FailureCode, str]:
    """Map a raw failure onto the taxonomy. Order of the branches is the logic."""
    message = str(error)
    lower = message.lower()

    if isinstance(error, TimeoutError):
        return FailureCode.TIMEOUT, message
    # A cancellation is a deliberate stop, not a fault, and must not be
    # presented to an operator as something that went wrong.
    if isinstance(error, asyncio.CancelledError) or "cancelled" in lower:
        return FailureCode.CANCELLED, message
    if isinstance(error, ValueError) and ("json" in lower or "expecting" in lower):
        return FailureCode.INVALID_PAYLOAD, message

    if _has_status(message, ("401", "403")) or any(
        token in lower for token in ("api key", "unauthorized", "forbidden")
    ):
        return FailureCode.AUTH, message

    # Before the rate-limit branch, deliberately: billing exhaustion arrives as
    # a 429 and "try again shortly" is wrong forever.
    if any(
        token in lower
        for token in (
            "no credits",
            "insufficient_quota",
            "insufficient quota",
            "exceeded your current quota",
            "billing",
        )
    ):
        return FailureCode.PROVIDER_BILLING, message
    if _has_status(message, ("429",)) or "rate limit" in lower or "quota" in lower:
        return FailureCode.RATE_LIMIT, message

    if _has_status(message, ("400", "404", "409", "413", "422")) or any(
        token in lower
        for token in (
            "bad request",
            "does not exist",
            "context length",
            "maximum context",
            "unsupported parameter",
        )
    ):
        return FailureCode.PROVIDER_BAD_REQUEST, message
    if _has_status(message, ("500", "502", "503", "504")) or any(
        token in lower for token in ("overloaded", "unavailable")
    ):
        return FailureCode.PROVIDER_UNAVAILABLE, message

    if any(token in lower for token in ("timeout", "timed out", "deadline")):
        return FailureCode.TIMEOUT, message
    if any(
        token in lower
        for token in ("connection reset", "connection refused", "name resolution", "socket")
    ):
        return FailureCode.NETWORK, message
    if "stale" in lower:
        return FailureCode.STALE_DATA, message
    if "market closed" in lower or "session closed" in lower:
        return FailureCode.MARKET_CLOSED, message
    if any(token in lower for token in ("insufficient", "not enough", "missing candles")):
        return FailureCode.INSUFFICIENT_DATA, message
    if any(token in lower for token in ("out of memory", "no space left", "disk is full")):
        return FailureCode.RESOURCE_EXHAUSTED, message
    if any(token in lower for token in ("not configured", "missing env", "misconfig")):
        return FailureCode.CONFIGURATION, message
    return FailureCode.UNKNOWN, message


def stage_failure_from_error(
    stage: AgentStage, error: BaseException | str, provider: str | None = None
) -> StageFailure:
    code, detail = classify_error(error)
    return StageFailure(
        stage=stage,
        code=code,
        retryable=is_retryable(code),
        operator_detail=detail[:MAX_DETAIL_CHARS],
        provider=provider,
    )


def stage_timeout_failure(stage: AgentStage, deadline_seconds: float) -> StageFailure:
    return StageFailure(
        stage=stage,
        code=FailureCode.TIMEOUT,
        retryable=True,
        operator_detail=f"Stage exceeded its {deadline_seconds:.0f}s deadline.",
    )


def ledger_silent_timeout(
    failures: list[StageFailure],
    stage: AgentStage,
    value: object,
    deadline_seconds: float,
) -> None:
    """Record a deadline that produced no exception.

    The subtlest failure in the whole pipeline. A stage run under a timeout that
    resolves to a fallback rather than raising leaves *no* exception for the
    catch to see — so a run whose specialists all timed out still reports itself
    healthy, with every stage quietly empty.

    An empty value with no ledgered failure for that stage can only mean the
    deadline hit. That inference is the entire mechanism.
    """
    if value is not None:
        return
    if any(failure.stage is stage for failure in failures):
        return
    failures.append(stage_timeout_failure(stage, deadline_seconds))
