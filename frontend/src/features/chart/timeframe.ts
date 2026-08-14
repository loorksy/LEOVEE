import type { SupportedTimeframe } from "@/chart";

/**
 * Backend frame codes (`app/models/enums.py`) to the chart's own spelling.
 *
 * Two vocabularies for the same six frames, differing only in the order of a
 * letter and a number — `M15` against `15M`. Both look right, so a mix-up is
 * invisible on inspection and shows up as a chart quietly rendering the wrong
 * timeframe. This table is the only place either spelling is converted.
 *
 * **M30 and D1 are gone (D11).** They were still offered in the timeframe
 * picker after the platform became scalp-only, so the UI listed two frames the
 * API now rejects with 422 — an option that cannot work is worse than no
 * option, because the failure looks like a bug in the analysis.
 */
const BACKEND_TO_CHART: Record<string, SupportedTimeframe> = {
  M1: "1M",
  M5: "5M",
  M15: "15M",
  H1: "1H",
  H4: "4H",
};

const CHART_TO_BACKEND: Record<string, string> = Object.fromEntries(
  Object.entries(BACKEND_TO_CHART).map(([backend, chart]) => [chart, backend]),
);

export function backendTimeframeToChart(timeframe: string): SupportedTimeframe {
  return BACKEND_TO_CHART[timeframe] ?? "15M";
}

export function chartTimeframeToBackend(timeframe: string): string {
  return CHART_TO_BACKEND[timeframe] ?? "M15";
}

/**
 * The frames a *decision* may be made on (D11). H4 and H1 are context: fetched,
 * stored and read for bias, never traded — so they are not offered here.
 */
export const DECISION_TIMEFRAMES = ["M1", "M5", "M15"];

export const BACKEND_TIMEFRAMES = Object.keys(BACKEND_TO_CHART);
