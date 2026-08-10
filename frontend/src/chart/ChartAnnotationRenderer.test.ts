import { describe, expect, it, vi } from "vitest";

import { diffAnnotations, ChartAnnotationRenderer } from "./ChartAnnotationRenderer";
import type { KLineChartLike, SemanticAnnotation } from "./ChartTypes";

function sampleAnn(id: string, version = 1): SemanticAnnotation {
  return {
    id,
    semantic_type: "DRAW_LEVEL",
    geometry: { anchors: [{ ts: "2024-01-01T00:00:00.000Z", price: 1.1 }] },
    status: "ACTIVE",
    version,
  };
}

describe("ChartAnnotationRenderer", () => {
  it("applies incremental updates without rebuilding unchanged overlays", () => {
    const chart: KLineChartLike = {
      applyNewData: vi.fn(),
      updateData: vi.fn(),
      createOverlay: vi.fn(() => "overlay-1"),
      removeOverlay: vi.fn(),
    };
    const renderer = new ChartAnnotationRenderer(chart);
    const first = renderer.applyIncremental([sampleAnn("a")]);
    expect(first.added).toHaveLength(1);
    expect(chart.createOverlay).toHaveBeenCalledTimes(1);

    const second = renderer.applyIncremental([sampleAnn("a")]);
    expect(second.added).toHaveLength(0);
    expect(second.updated).toHaveLength(0);
    expect(chart.createOverlay).toHaveBeenCalledTimes(1);

    const third = renderer.applyIncremental([sampleAnn("a", 2)]);
    expect(third.updated).toHaveLength(1);
    expect(chart.createOverlay).toHaveBeenCalledTimes(2);
    expect(chart.removeOverlay).toHaveBeenCalledTimes(1);
  });

  it("diffAnnotations detects removals", () => {
    const prev = new Map<string, SemanticAnnotation>([
      ["a", sampleAnn("a")],
      ["b", sampleAnn("b")],
    ]);
    const diff = diffAnnotations(prev, [sampleAnn("a")]);
    expect(diff.removed).toEqual(["b"]);
  });
});
