import type { KLineChartLike, SemanticAnnotation } from "./ChartTypes";

export type AnnotationDiff = {
  added: SemanticAnnotation[];
  updated: SemanticAnnotation[];
  removed: string[];
};

export function diffAnnotations(
  previous: Map<string, SemanticAnnotation>,
  next: SemanticAnnotation[],
): AnnotationDiff {
  const nextMap = new Map(next.map((a) => [a.id, a]));
  const added: SemanticAnnotation[] = [];
  const updated: SemanticAnnotation[] = [];
  const removed: string[] = [];

  for (const ann of next) {
    const prev = previous.get(ann.id);
    if (!prev) {
      added.push(ann);
    } else if (prev.version !== ann.version || JSON.stringify(prev) !== JSON.stringify(ann)) {
      updated.push(ann);
    }
  }
  for (const id of previous.keys()) {
    if (!nextMap.has(id)) {
      removed.push(id);
    }
  }
  return { added, updated, removed };
}

function overlayNameFor(annotation: SemanticAnnotation): string {
  switch (annotation.semantic_type) {
    case "DRAW_ZONE":
      return "rect";
    case "DRAW_LEVEL":
    case "DRAW_LIQUIDITY":
      return "horizontalStraightLine";
    case "DRAW_STRUCTURE":
    case "DRAW_SETUP":
      return "segment";
    case "LABEL":
      return "simpleAnnotation";
    default:
      return "segment";
  }
}

function overlayPoints(annotation: SemanticAnnotation): Array<{ timestamp: number; value: number }> {
  return annotation.geometry.anchors.map((anchor) => ({
    timestamp: new Date(anchor.ts).getTime(),
    value: anchor.price,
  }));
}

export class ChartAnnotationRenderer {
  private readonly chart: KLineChartLike;
  private readonly overlayByAnnotationId = new Map<string, string>();
  private readonly snapshot = new Map<string, SemanticAnnotation>();

  constructor(chart: KLineChartLike) {
    this.chart = chart;
  }

  applyIncremental(annotations: SemanticAnnotation[]): AnnotationDiff {
    const diff = diffAnnotations(this.snapshot, annotations);
    for (const id of diff.removed) {
      const overlayId = this.overlayByAnnotationId.get(id);
      if (overlayId) {
        this.chart.removeOverlay(overlayId);
        this.overlayByAnnotationId.delete(id);
      }
      this.snapshot.delete(id);
    }
    for (const ann of [...diff.added, ...diff.updated]) {
      const existing = this.overlayByAnnotationId.get(ann.id);
      const payload = {
        name: overlayNameFor(ann),
        id: ann.id,
        points: overlayPoints(ann),
        extendData: { semantic_type: ann.semantic_type, style: ann.style ?? {} },
      };
      if (existing && this.chart.overrideOverlay) {
        this.chart.overrideOverlay(existing, payload);
      } else {
        if (existing) {
          this.chart.removeOverlay(existing);
        }
        const overlayId = this.chart.createOverlay(payload);
        if (overlayId) {
          this.overlayByAnnotationId.set(ann.id, overlayId);
        }
      }
      this.snapshot.set(ann.id, ann);
    }
    return diff;
  }

  clear(): void {
    for (const overlayId of this.overlayByAnnotationId.values()) {
      this.chart.removeOverlay(overlayId);
    }
    this.overlayByAnnotationId.clear();
    this.snapshot.clear();
  }
}
