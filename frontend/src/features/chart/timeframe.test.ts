import { describe, expect, it } from "vitest";

import {
  BACKEND_TIMEFRAMES,
  DECISION_TIMEFRAMES,
  backendTimeframeToChart,
  chartTimeframeToBackend,
} from "./timeframe";

describe("timeframe mapping", () => {
  it("carries only the frames the platform actually supports", () => {
    // M30 and D1 were still listed after the platform became scalp-only (D11),
    // so the picker offered two frames the API now rejects with 422. An option
    // that cannot work is worse than no option: the failure reads as a bug in
    // the analysis rather than as a frame that does not exist.
    expect(BACKEND_TIMEFRAMES).toEqual(["M1", "M5", "M15", "H1", "H4"]);
    expect(BACKEND_TIMEFRAMES).not.toContain("M30");
    expect(BACKEND_TIMEFRAMES).not.toContain("D1");
  });

  it("round-trips every frame through both spellings", () => {
    // `M15` and `15M` differ only in the order of a letter and a number, so a
    // mix-up is invisible on inspection and shows up as the chart quietly
    // rendering a different timeframe than the one requested.
    for (const backend of BACKEND_TIMEFRAMES) {
      expect(chartTimeframeToBackend(backendTimeframeToChart(backend))).toBe(backend);
    }
  });

  it("names only the frames a decision may be made on", () => {
    // H4 and H1 are context (D11): fetched, stored and read for bias, never
    // traded. Offering them as decision frames would invite a scalp on a chart
    // the constitution says cannot carry one.
    expect(DECISION_TIMEFRAMES).toEqual(["M1", "M5", "M15"]);
    for (const frame of DECISION_TIMEFRAMES) {
      expect(BACKEND_TIMEFRAMES).toContain(frame);
    }
  });

  it("falls back to the default scalping frame, not to a context frame", () => {
    // The old fallback was H1 — a frame no scalp may be taken on. An unknown
    // value landing there put the chart on a timeframe the API would refuse.
    expect(backendTimeframeToChart("bogus")).toBe("15M");
    expect(chartTimeframeToBackend("bogus")).toBe("M15");
  });
});
