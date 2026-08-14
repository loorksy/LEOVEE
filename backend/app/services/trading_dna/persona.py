"""One name for how this reader trades, or the honest refusal to name one.

**`unclassified` is a real answer and the most common early one.** A persona
assigned from six plans is a stereotype the platform then reasons with, and it
will keep reasoning with it long after the evidence would have said something
else. So there are two gates: enough plans to look at, and enough agreement
among them for a name to describe anything.

Under D11 the platform is scalp-only, so the holding-time bands are narrow by
design. `swing` is still reachable and still worth naming — a reader whose plans
routinely run past a day is doing something the product did not intend, and
saying so is more useful than forcing them into `intraday`.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

from app.services.trading_dna.types import (
    EvidenceBundle,
    PersonaName,
    PlanRecord,
    TradingPersona,
)

__all__ = ["MIN_PERSONA_SAMPLE", "DOMINANCE_GATE", "derive_persona"]

#: Plans with a measurable holding time before a persona may be named.
MIN_PERSONA_SAMPLE = 10

#: How much of the sample must agree. Below it the reader trades several ways,
#: and averaging them produces a name describing none of them.
DOMINANCE_GATE = 0.6

SCALPER_HOURS = 4.0
INTRADAY_HOURS = 24.0


def _band(hours: float) -> PersonaName:
    if hours <= SCALPER_HOURS:
        return PersonaName.SCALPER
    if hours <= INTRADAY_HOURS:
        return PersonaName.INTRADAY
    return PersonaName.SWING


def derive_persona(bundle: EvidenceBundle) -> TradingPersona:
    plans: Sequence[PlanRecord] = [plan for plan in bundle.plans if plan.holding_hours is not None]
    if len(plans) < MIN_PERSONA_SAMPLE:
        return TradingPersona(
            name=PersonaName.UNCLASSIFIED,
            reason="PERSONA_INSUFFICIENT_SAMPLE",
            sample_size=len(plans),
        )

    bands = Counter(_band(plan.holding_hours or 0.0) for plan in plans)
    name, count = bands.most_common(1)[0]
    share = count / len(plans)
    if share < DOMINANCE_GATE:
        # No single band describes them. Naming the largest anyway would be a
        # label chosen by a plurality of as little as 40%.
        return TradingPersona(
            name=PersonaName.UNCLASSIFIED,
            reason="PERSONA_MIXED",
            sample_size=len(plans),
            support=round(share, 4),
        )

    return TradingPersona(
        name=name,
        reason="PERSONA_DOMINANT_BAND",
        sample_size=len(plans),
        support=round(share, 4),
    )
