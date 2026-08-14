/**
 * The only file in the codebase that knows TradingView exists.
 *
 * That containment is the whole design. `ChartEngine` and `AnnotationSurface`
 * are the contracts everything else binds to, and this implements them — so
 * replacing the renderer again means replacing this file, not auditing every
 * consumer. The previous swap was cheap for exactly that reason, and it stays
 * cheap only while this stays the boundary.
 *
 * **Library indicators are for looking at, never for deciding with.** Anything
 * the agent reasons about comes from the Python engines through the API. Letting
 * the client re-derive a number the decision rests on is how the chart and the
 * narrative end up disagreeing by a rounding step, with nothing to say which is
 * right.
 */

import type { AnnotationSurface, SemanticAnnotation } from "./ChartTypes";

/**
 * The slice of the charting library this adapter uses.
 *
 * Declared structurally rather than imported from the vendored `.d.ts`: the
 * library is a runtime asset loaded from `/charting_library`, and a hard import
 * would make `tsc` and `vitest` require 27 MB of vendored bundles to be present
 * before a single unrelated test could run.
 */
export type TradingViewShapeApi = {
  createMultipointShape: (
    points: Array<{ time: number; price: number }>,
    options: Record<string, unknown>,
  ) => string | null;
  removeEntity: (id: string) => void;
  setSymbol?: (symbol: string, interval: string, callback?: () => void) => void;
};

export type TradingViewAdapterOptions = {
  shapes: TradingViewShapeApi;
};

/**
 * Semantic type → the library's native drawing tool.
 *
 * The one place a mapping like this belongs. A native tool renders and behaves
 * like the thing it is — a triangle stays editable as a triangle — where the
 * generic polyline fallback draws the same outline and loses that.
 */
const SHAPE_BY_SEMANTIC_TYPE: Record<string, string> = {
  price_line: "horizontal_line",
  trend_line: "trend_line",
  neckline: "trend_line",
  baseline: "horizontal_line",
  channel: "parallel_channel",
  parallel_channel: "parallel_channel",
  regression_trend: "regression_trend",
  zone: "rectangle",
  supply_zone: "rectangle",
  demand_zone: "rectangle",
  decision_zone: "rectangle",
  range_box: "rectangle",
  retest_zone: "rectangle",
  risk_reward_box: "rectangle",
  fib_retracement: "fib_retracement",
  marker: "icon",
  labeled_arrow: "arrow_marker",
  breakout_arrow: "arrow_marker",
  pattern_label: "text",
  long_position: "long_position",
  short_position: "short_position",
  polyline_pattern: "polyline",
  forecast_path: "polyline",
  histogram_band: "rectangle",
};

/** Anything unmapped draws as a polyline: the outline is still correct. */
const FALLBACK_SHAPE = "polyline";

export function shapeFor(annotation: SemanticAnnotation): string {
  return SHAPE_BY_SEMANTIC_TYPE[String(annotation.semantic_type)] ?? FALLBACK_SHAPE;
}

/**
 * Anchors to the library's point format.
 *
 * Seconds, not milliseconds — the library's time axis is in seconds, and
 * passing milliseconds silently places every drawing about fifty thousand years
 * into the future, where it renders perfectly and is never seen.
 */
export function pointsFor(
  annotation: SemanticAnnotation,
): Array<{ time: number; price: number }> {
  return annotation.geometry.anchors.map((anchor) => ({
    time: Math.floor(new Date(anchor.ts).getTime() / 1000),
    price: anchor.price,
  }));
}

export function overridesFor(annotation: SemanticAnnotation): Record<string, unknown> {
  const style = annotation.style ?? {};
  const overrides: Record<string, unknown> = {};
  if (style.color) {
    overrides.linecolor = style.color;
    overrides.color = style.color;
  }
  if (style.line_width != null) {
    overrides.linewidth = style.line_width;
  }
  if (style.fill_opacity != null) {
    overrides.transparency = Math.round((1 - style.fill_opacity) * 100);
    overrides.backgroundColor = style.color ?? undefined;
    overrides.fillBackground = true;
  }
  if (style.line_style === "dashed") {
    // 2 is the library's dashed line style. A forming pattern must not render
    // solid: that asserts a structure which has not happened yet.
    overrides.linestyle = 2;
  }
  if (style.label) {
    overrides.text = style.label;
    overrides.showLabel = true;
  }
  return overrides;
}

export class TradingViewAnnotationSurface implements AnnotationSurface {
  private readonly shapes: TradingViewShapeApi;

  constructor(options: TradingViewAdapterOptions) {
    this.shapes = options.shapes;
  }

  create(annotation: SemanticAnnotation): string | null {
    const points = pointsFor(annotation);
    if (points.length === 0) {
      return null;
    }
    return this.shapes.createMultipointShape(points, {
      shape: shapeFor(annotation),
      lock: true,
      disableSelection: false,
      disableSave: true,
      // Never undoable: an agent drawing is evidence, and letting Ctrl-Z remove
      // it leaves the chart disagreeing with the narrative that cites it.
      disableUndo: true,
      overrides: overridesFor(annotation),
      zOrder: "top",
    });
  }

  remove(handle: string): void {
    this.shapes.removeEntity(handle);
  }
}
