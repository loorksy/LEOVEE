import { describe, expect, it } from "vitest";
import { filterCandlesForReplay, normalizeBackendCandle } from "./ChartDataAdapter";

describe("filterCandlesForReplay", () => {
  it("drops candles strictly after replay time", () => {
    const early = normalizeBackendCandle({
      ts: "2024-01-01T10:00:00.000Z",
      open: 1,
      high: 2,
      low: 0.5,
      close: 1.5,
    });
    const late = normalizeBackendCandle({
      ts: "2024-01-01T12:00:00.000Z",
      open: 1,
      high: 2,
      low: 0.5,
      close: 1.5,
    });
    const asOf = new Date("2024-01-01T11:00:00.000Z").getTime();
    const filtered = filterCandlesForReplay([early, late], asOf);
    expect(filtered).toHaveLength(1);
    expect(filtered[0].timestamp).toBe(early.timestamp);
  });
});
