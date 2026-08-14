/**
 * Renderer-agnostic chart semantic types (mirror backend API).
 */

/**
 * What is being drawn. Mirrors `app/schemas/chart.py::ChartSemanticType`.
 *
 * Six coarse buckets used to stand in for these twenty-four, so a neckline, a
 * channel and a supply zone all arrived as `DRAW_STRUCTURE` and the renderer
 * had to guess the tool from the anchor count.
 *
 * Named for meaning, never for a drawing primitive — the moment this vocabulary
 * names a library's tool, the renderer stops being replaceable, which is the
 * whole property that made swapping KLineChart for TradingView cheap.
 */
export type ChartSemanticType =
  | "price_line"
  | "trend_line"
  | "forecast_path"
  | "channel"
  | "parallel_channel"
  | "regression_trend"
  | "zone"
  | "supply_zone"
  | "demand_zone"
  | "decision_zone"
  | "range_box"
  | "retest_zone"
  | "fib_retracement"
  | "baseline"
  | "marker"
  | "labeled_arrow"
  | "breakout_arrow"
  | "histogram_band"
  | "polyline_pattern"
  | "pattern_label"
  | "neckline"
  | "risk_reward_box"
  | "long_position"
  | "short_position";

/** Why it is being drawn. Orthogonal to the type, and both are needed. */
export type ChartSemanticRole =
  | "support"
  | "resistance"
  | "demand_zone"
  | "supply_zone"
  | "range"
  | "trendline"
  | "channel"
  | "neckline"
  | "breakout"
  | "retest"
  | "entry"
  | "stop_loss"
  | "take_profit"
  | "risk_reward"
  | "pattern"
  | "forecast"
  | "liquidity_sweep"
  | "decision_zone";

export type ChartAnnotationStatus = "CREATED" | "ACTIVE" | "ARCHIVED";

export type ChartAnchor = {
  ts: string;
  price: number;
  timeframe?: string | null;
};

export type ChartGeometry = {
  anchors: ChartAnchor[];
  metadata?: Record<string, unknown>;
};

export type ChartStyle = {
  color?: string | null;
  line_width?: number | null;
  fill_opacity?: number | null;
  label?: string | null;
  /** `solid` or `dashed` — semantic, not cosmetic: a forming pattern is dashed
   *  because it has not happened yet. */
  line_style?: string | null;
};

export type SemanticAnnotation = {
  id: string;
  semantic_type: ChartSemanticType | string;
  geometry: ChartGeometry;
  style?: ChartStyle;
  status: ChartAnnotationStatus;
  version: number;
  role?: ChartSemanticRole | string | null;
  pattern_type?: string | null;
  confidence?: number | null;
};

export type ChartSemanticModel = {
  version: number;
  symbol?: string | null;
  timeframe?: string | null;
  operations: Array<{
    semantic_type: ChartSemanticType;
    geometry: ChartGeometry;
    style?: ChartStyle;
    role?: ChartSemanticRole | null;
    pattern_type?: string | null;
    confidence?: number | null;
  }>;
};

export type NormalizedCandle = {
  timestamp: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  complete: boolean;
};

export type CandleUpdateKind = "NEW_CANDLE" | "CANDLE_UPDATED" | "PRICE_UPDATED";

export type ChartEngine = {
  setSymbol: (symbol: string) => void;
  setTimeframe: (timeframe: string) => void;
  applyCandles: (candles: NormalizedCandle[]) => void;
  applyCandlePatch: (candle: NormalizedCandle) => CandleUpdateKind;
  applyAnnotations: (annotations: SemanticAnnotation[]) => void;
  destroy: () => void;
};

/**
 * The minimum a renderer must offer to draw annotations.
 *
 * Deliberately not a library's interface. It replaced a KLineChart-shaped type
 * (`applyNewData`, `createOverlay`, …) that made the renderer's identity leak
 * into every consumer — which is what turned "swap the chart library" from a
 * one-file change into a rewrite the first time it was attempted.
 */
export type AnnotationSurface = {
  /** Draw one annotation; return a handle the surface can later address. */
  create: (annotation: SemanticAnnotation) => string | null;
  /** Redraw an existing one in place, when the surface supports it. */
  update?: (handle: string, annotation: SemanticAnnotation) => void;
  remove: (handle: string) => void;
};

export const SUPPORTED_TIMEFRAMES = ["1M", "5M", "15M", "30M", "1H", "4H", "1D"] as const;
export type SupportedTimeframe = (typeof SUPPORTED_TIMEFRAMES)[number];
