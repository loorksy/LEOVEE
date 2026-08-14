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

## Implementation notes (M9)

**How it is stored.** Runtime assets (`frontend/public/charting_library/`, ~26 MB
across ~1,900 chunks) through Git LFS; type definitions
(`frontend/vendor/tradingview/*.d.ts`, ~1.2 MB of text) in plain git, because
TypeScript reads them on every `tsc` and an unsmudged LFS pointer would break
compilation anywhere the filter has not run.

**The licence is enforced by the build.** `scripts/check_repo_visibility.sh`
fails when the repository reports itself public while the vendored library is
present. "Keep the repo private" is a setting someone can flip in a web UI
months from now, with no diff and no review — and the moment it flips, 27 MB of
licensed third-party code becomes public redistribution.

**The boundary held.** Swapping the renderer touched `chart/index.ts` and the
new `TradingViewAdapter.ts`, and nothing else: every consumer binds to
`ChartEngine` and `AnnotationSurface`. `src/chart/rendererBoundary.test.ts`
keeps it that way — the first component to import the widget directly would
work perfectly and quietly cost the abstraction.

**Two things the port fixed along the way:**

- `ChartAnnotationRenderer` mapped semantic types onto KLineChart overlay names
  (`DRAW_ZONE` → `"rect"`) inside the one class that was supposed to be
  independent of the renderer. Choosing a tool is now the surface's job, since
  only the surface knows what tools it has.
- The timeframe picker still offered M30 and D1 after the platform became
  scalp-only (D11), so the UI listed two frames the API rejects with 422. An
  option that cannot work is worse than no option: the failure reads as a bug in
  the analysis rather than as a frame that does not exist.
