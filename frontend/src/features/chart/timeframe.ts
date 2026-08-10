import type { SupportedTimeframe } from "@/chart";

/** Backend `Timeframe` enum values (`app/models/enums.py`) map onto chart timeframe codes. */
const BACKEND_TO_CHART: Record<string, SupportedTimeframe> = {
  M1: "1M",
  M5: "5M",
  M15: "15M",
  M30: "30M",
  H1: "1H",
  H4: "4H",
  D1: "1D",
};

const CHART_TO_BACKEND: Record<string, string> = Object.fromEntries(
  Object.entries(BACKEND_TO_CHART).map(([backend, chart]) => [chart, backend]),
);

export function backendTimeframeToChart(timeframe: string): SupportedTimeframe {
  return BACKEND_TO_CHART[timeframe] ?? "1H";
}

export function chartTimeframeToBackend(timeframe: string): string {
  return CHART_TO_BACKEND[timeframe] ?? "H1";
}

export const BACKEND_TIMEFRAMES = Object.keys(BACKEND_TO_CHART);
