import type { SemanticAnnotation } from "@/chart";

export type AnnotationStreamEvent = {
  event: "annotation_created" | "annotation_updated" | "annotations_batch" | string;
  annotation?: SemanticAnnotation;
  count?: number;
};

/**
 * Apply one WebSocket annotation event to a snapshot map (incremental update,
 * no full rebuild — mirrors backend `annotation_broadcaster` payloads §25).
 */
export function applyAnnotationEvent(
  current: Map<string, SemanticAnnotation>,
  event: AnnotationStreamEvent,
): Map<string, SemanticAnnotation> {
  if (!event.annotation) return current;
  const next = new Map(current);
  const ann = event.annotation;
  if (ann.status === "ARCHIVED") {
    next.delete(ann.id);
  } else {
    next.set(ann.id, ann);
  }
  return next;
}

export function annotationMapToList(map: Map<string, SemanticAnnotation>): SemanticAnnotation[] {
  return [...map.values()];
}

export function annotationListToMap(
  annotations: SemanticAnnotation[],
): Map<string, SemanticAnnotation> {
  return new Map(annotations.map((a) => [a.id, a]));
}

export type CandleStreamEvent = {
  ts: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
  complete?: boolean;
  symbol?: string;
};

export function isCandleEvent(payload: unknown): payload is CandleStreamEvent {
  if (typeof payload !== "object" || payload === null) return false;
  const candidate = payload as Record<string, unknown>;
  return (
    typeof candidate.ts === "string" &&
    typeof candidate.close === "number" &&
    typeof candidate.open === "number"
  );
}

export function isAnnotationEvent(payload: unknown): payload is AnnotationStreamEvent {
  if (typeof payload !== "object" || payload === null) return false;
  const candidate = payload as Record<string, unknown>;
  return (
    typeof candidate.event === "string" &&
    (candidate.event.startsWith("annotation") || candidate.event.startsWith("annotations"))
  );
}
