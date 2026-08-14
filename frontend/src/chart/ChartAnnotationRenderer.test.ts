import { describe, expect, it, vi } from "vitest";

import { ChartAnnotationRenderer, diffAnnotations } from "./ChartAnnotationRenderer";
import type { AnnotationSurface, SemanticAnnotation } from "./ChartTypes";

function sampleAnn(id: string, version = 1): SemanticAnnotation {
  return {
    id,
    semantic_type: "price_line",
    role: "stop_loss",
    geometry: { anchors: [{ ts: "2024-01-01T00:00:00.000Z", price: 2000.5 }] },
    status: "ACTIVE",
    version,
  };
}

function fakeSurface(withUpdate = false): AnnotationSurface & {
  create: ReturnType<typeof vi.fn>;
  remove: ReturnType<typeof vi.fn>;
  update?: ReturnType<typeof vi.fn>;
} {
  let next = 0;
  const surface = {
    create: vi.fn(() => `handle-${(next += 1)}`),
    remove: vi.fn(),
  } as AnnotationSurface & {
    create: ReturnType<typeof vi.fn>;
    remove: ReturnType<typeof vi.fn>;
    update?: ReturnType<typeof vi.fn>;
  };
  if (withUpdate) {
    surface.update = vi.fn();
  }
  return surface;
}

describe("ChartAnnotationRenderer", () => {
  it("redraws nothing when the annotation set has not changed", () => {
    // Re-evaluation republishes the whole set every cycle. Clearing and
    // redrawing would make the chart flicker each time one level moves.
    const surface = fakeSurface();
    const renderer = new ChartAnnotationRenderer(surface);

    const first = renderer.applyIncremental([sampleAnn("a")]);
    expect(first.added).toHaveLength(1);
    expect(surface.create).toHaveBeenCalledTimes(1);

    const second = renderer.applyIncremental([sampleAnn("a")]);
    expect(second.added).toHaveLength(0);
    expect(second.updated).toHaveLength(0);
    expect(surface.create).toHaveBeenCalledTimes(1);
    expect(surface.remove).not.toHaveBeenCalled();
  });

  it("updates in place when the surface can, without leaving the old drawing", () => {
    const surface = fakeSurface(true);
    const renderer = new ChartAnnotationRenderer(surface);
    renderer.applyIncremental([sampleAnn("a")]);
    renderer.applyIncremental([sampleAnn("a", 2)]);

    expect(surface.update).toHaveBeenCalledTimes(1);
    expect(surface.create).toHaveBeenCalledTimes(1);
    expect(surface.remove).not.toHaveBeenCalled();
  });

  it("removes before recreating when the surface has no in-place update", () => {
    // Otherwise a second drawing accumulates on top of the first every cycle,
    // and the chart slowly thickens with copies of the same level.
    const surface = fakeSurface();
    const renderer = new ChartAnnotationRenderer(surface);
    renderer.applyIncremental([sampleAnn("a")]);
    renderer.applyIncremental([sampleAnn("a", 2)]);

    expect(surface.remove).toHaveBeenCalledTimes(1);
    expect(surface.create).toHaveBeenCalledTimes(2);
  });

  it("removes annotations the analysis has retracted", () => {
    const surface = fakeSurface();
    const renderer = new ChartAnnotationRenderer(surface);
    renderer.applyIncremental([sampleAnn("a"), sampleAnn("b")]);
    const diff = renderer.applyIncremental([sampleAnn("a")]);

    expect(diff.removed).toEqual(["b"]);
    expect(surface.remove).toHaveBeenCalledTimes(1);
  });

  it("diffAnnotations detects removals", () => {
    const prev = new Map<string, SemanticAnnotation>([
      ["a", sampleAnn("a")],
      ["b", sampleAnn("b")],
    ]);
    expect(diffAnnotations(prev, [sampleAnn("a")]).removed).toEqual(["b"]);
  });
});
