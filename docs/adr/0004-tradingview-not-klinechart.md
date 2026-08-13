# 0004 — TradingView Advanced Charts, vendored in-repo

**Status:** accepted · **Supersedes:** `LEOVEE_SPEC.md` §43, §44

## Context

The specification mandates KLineChart v9 as the primary chart renderer and
forbids replacing it. Leovee's frontend has KLineCharts 9.8.12 wired behind a
`ChartEngine` abstraction in `frontend/src/chart/`.

AiChart uses TradingView Advanced Charts — a licensed library, gitignored, 27 MB
provisioned at build time from a private URL by `scripts/provision-tradingview.mjs`
— with mature adapters for datafeed, drawings, studies and user drawings, plus a
semantic drawing vocabulary of 25 types and 18 roles. Leovee's semantic
vocabulary has 6 types.

## Decision

Leovee uses TradingView Advanced Charts, vendored **inside the repository**
rather than fetched at build time.

## Consequences

- This is the cheapest phase in the migration rather than the most expensive
  one. AiChart's adapters become a TypeScript-to-TypeScript port — the only
  conversion is Next.js/React 19 to Vite/React 18 — instead of 24 custom
  KLineChart overlay renderers written from scratch. The mature, tested drawing
  vocabulary comes with them.
- `frontend/src/chart/ChartTypes.ts` and its renderer-agnostic `ChartEngine`
  interface **stay**. Only the implementation beneath changes, which is what
  makes the swap cheap. The `klinecharts` dependency and its adapter files go.
- The library is committed under Git LFS. `scripts/provision-tradingview.mjs`
  and the `TRADINGVIEW_LIBRARY_URL` / `TRADINGVIEW_LIBRARY_TOKEN` variables are
  deleted; the build becomes self-contained with no private source.
- **The TradingView licence forbids public redistribution.** Vendoring into a
  private repository is normally acceptable, but the library becomes exposed the
  moment the repository becomes public. A CI guard fails the build if repository
  visibility changes. This constraint is the reason the decision is recorded
  rather than merely implemented.
