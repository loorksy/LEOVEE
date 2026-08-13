# Architecture decision records

One file per decision that departs from `LEOVEE_SPEC.md`, or that later phases
of the AiChart migration must not silently reverse.

`LEOVEE_SPEC.md` was written as a greenfield specification and states outright
that no legacy system exists and that no migration plan should be produced. That
turned out to be wrong — AiChart implements the same product — and the cost was
an engine layer stubbed against a spec instead of ported from a working
implementation. Keeping the spec saying one thing while the code does another is
exactly how that happened, so every deviation gets recorded here and the spec
gets amended alongside.

| ADR | Decision | Supersedes |
|-----|----------|------------|
| [0001](0001-migrate-aichart-into-leovee.md) | AiChart is ported into Leovee; Leovee's architecture is final | §0 |
| [0002](0002-direction-is-always-required.md) | A successful analysis always carries a direction; NO_TRADE is operational | §110 |
| [0003](0003-no-backtesting.md) | No backtesting or statistical validation | §64 |
| [0004](0004-tradingview-not-klinechart.md) | TradingView Advanced Charts, vendored in-repo | §43, §44 |
| [0005](0005-analysis-only-no-execution.md) | No execution, brokers, or notifications | §17, §19, §57, §105 |
| [0006](0006-float-in-engines-decimal-at-the-money-boundary.md) | Engines compute in float; Decimal at the money boundary | — |
| [0007](0007-gold-only.md) | The tradable universe is XAUUSD alone | §17, §60 |
| [0008](0008-scalp-only-agent-chosen-timeframe.md) | Scalp only; the agent picks M1/M5/M15 | §21, §49, §106 |
