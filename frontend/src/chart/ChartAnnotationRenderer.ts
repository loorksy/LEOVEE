import type { AnnotationSurface, SemanticAnnotation } from "./ChartTypes";

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

/**
 * Diffs annotations and tells a surface what changed.
 *
 * It knows nothing about which library draws. It used to map semantic types
 * onto KLineChart overlay names right here — `DRAW_ZONE` to `"rect"` — which
 * put the renderer's vocabulary in the one class that was supposed to be
 * independent of it. Choosing a tool is now the surface's job, because only the
 * surface knows what tools it has.
 */
export class ChartAnnotationRenderer {
  private readonly surface: AnnotationSurface;
  private readonly handleByAnnotationId = new Map<string, string>();
  private readonly snapshot = new Map<string, SemanticAnnotation>();

  constructor(surface: AnnotationSurface) {
    this.surface = surface;
  }

  /**
   * Apply only what changed.
   *
   * Clearing and redrawing would be simpler and wrong: re-evaluation republishes
   * the annotation set every cycle, and a full redraw makes the whole chart
   * flicker every time one level moves — including the user's own drawings, if
   * the surface cannot tell them apart.
   */
  applyIncremental(annotations: SemanticAnnotation[]): AnnotationDiff {
    const diff = diffAnnotations(this.snapshot, annotations);
    for (const id of diff.removed) {
      const handle = this.handleByAnnotationId.get(id);
      if (handle) {
        this.surface.remove(handle);
        this.handleByAnnotationId.delete(id);
      }
      this.snapshot.delete(id);
    }
    for (const ann of [...diff.added, ...diff.updated]) {
      const existing = this.handleByAnnotationId.get(ann.id);
      if (existing && this.surface.update) {
        this.surface.update(existing, ann);
      } else {
        // No in-place update available: remove first, so a surface without one
        // does not accumulate a second drawing on top of the first every cycle.
        if (existing) {
          this.surface.remove(existing);
          this.handleByAnnotationId.delete(ann.id);
        }
        const handle = this.surface.create(ann);
        if (handle) {
          this.handleByAnnotationId.set(ann.id, handle);
        }
      }
      this.snapshot.set(ann.id, ann);
    }
    return diff;
  }

  clear(): void {
    for (const handle of this.handleByAnnotationId.values()) {
      this.surface.remove(handle);
    }
    this.handleByAnnotationId.clear();
    this.snapshot.clear();
  }
}
