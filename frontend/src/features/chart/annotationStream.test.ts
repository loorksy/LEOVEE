import { describe, expect, it } from "vitest";
import {
  annotationListToMap,
  annotationMapToList,
  applyAnnotationEvent,
  isAnnotationEvent,
  isCandleEvent,
} from "./annotationStream";
import type { SemanticAnnotation } from "@/chart";

function ann(id: string, overrides: Partial<SemanticAnnotation> = {}): SemanticAnnotation {
  return {
    id,
    semantic_type: "DRAW_LEVEL",
    geometry: { anchors: [{ ts: "2024-01-01T00:00:00.000Z", price: 1.1 }] },
    status: "ACTIVE",
    version: 1,
    ...overrides,
  };
}

describe("applyAnnotationEvent", () => {
  it("adds a new annotation from a websocket event", () => {
    const map = applyAnnotationEvent(new Map(), {
      event: "annotation_created",
      annotation: ann("a"),
    });
    expect(annotationMapToList(map)).toHaveLength(1);
  });

  it("updates an existing annotation in place (incremental, no rebuild)", () => {
    const initial = annotationListToMap([ann("a", { version: 1 })]);
    const next = applyAnnotationEvent(initial, {
      event: "annotation_updated",
      annotation: ann("a", { version: 2 }),
    });
    expect(next.get("a")?.version).toBe(2);
    expect(next).not.toBe(initial);
  });

  it("removes an annotation when its status becomes ARCHIVED", () => {
    const initial = annotationListToMap([ann("a"), ann("b")]);
    const next = applyAnnotationEvent(initial, {
      event: "annotation_updated",
      annotation: ann("a", { status: "ARCHIVED" }),
    });
    expect(annotationMapToList(next).map((a) => a.id)).toEqual(["b"]);
  });

  it("is a no-op for events without an annotation payload", () => {
    const initial = annotationListToMap([ann("a")]);
    const next = applyAnnotationEvent(initial, { event: "annotations_batch", count: 3 });
    expect(next).toBe(initial);
  });
});

describe("isAnnotationEvent / isCandleEvent", () => {
  it("recognizes annotation events", () => {
    expect(isAnnotationEvent({ event: "annotation_created", annotation: ann("a") })).toBe(true);
    expect(isAnnotationEvent({ event: "annotations_batch" })).toBe(true);
    expect(isAnnotationEvent({ foo: "bar" })).toBe(false);
    expect(isAnnotationEvent(null)).toBe(false);
  });

  it("recognizes candle tick events", () => {
    expect(
      isCandleEvent({ ts: "2024-01-01T00:00:00.000Z", open: 1, high: 2, low: 0.5, close: 1.5 }),
    ).toBe(true);
    expect(isCandleEvent({ event: "annotation_created" })).toBe(false);
  });
});
