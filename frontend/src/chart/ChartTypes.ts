/**
 * Renderer-agnostic chart semantic types (mirror backend API).
 */

export type ChartSemanticType =
  | "DRAW_ZONE"
  | "DRAW_STRUCTURE"
  | "DRAW_LIQUIDITY"
  | "DRAW_SETUP"
  | "DRAW_LEVEL"
  | "LABEL";

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
};

export type SemanticAnnotation = {
  id: string;
  semantic_type: ChartSemanticType | string;
  geometry: ChartGeometry;
  style?: ChartStyle;
  status: ChartAnnotationStatus;
  version: number;
};

export type ChartSemanticModel = {
  version: number;
  symbol?: string | null;
  timeframe?: string | null;
  operations: Array<{
    semantic_type: ChartSemanticType;
    geometry: ChartGeometry;
    style?: ChartStyle;
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

export type KLineChartLike = {
  applyNewData: (data: unknown[]) => void;
  updateData: (data: unknown) => void;
  createOverlay: (value: unknown) => string | null;
  removeOverlay: (id: string) => void;
  overrideOverlay?: (id: string, value: unknown) => void;
};

export const SUPPORTED_TIMEFRAMES = ["1M", "5M", "15M", "30M", "1H", "4H", "1D"] as const;
export type SupportedTimeframe = (typeof SUPPORTED_TIMEFRAMES)[number];
