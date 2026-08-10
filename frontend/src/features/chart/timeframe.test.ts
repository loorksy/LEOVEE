import { describe, expect, it } from "vitest";
import { BACKEND_TIMEFRAMES, backendTimeframeToChart, chartTimeframeToBackend } from "./timeframe";

describe("timeframe mapping", () => {
  it("maps every backend Timeframe enum value to a supported chart timeframe", () => {
    expect(BACKEND_TIMEFRAMES).toEqual(["M1", "M5", "M15", "M30", "H1", "H4", "D1"]);
    for (const backend of BACKEND_TIMEFRAMES) {
      const chart = backendTimeframeToChart(backend);
      expect(chartTimeframeToBackend(chart)).toBe(backend);
    }
  });

  it("falls back to H1/1H for unknown values", () => {
    expect(backendTimeframeToChart("bogus")).toBe("1H");
    expect(chartTimeframeToBackend("bogus")).toBe("H1");
  });
});
