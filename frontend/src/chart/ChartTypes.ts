/**
 * Chart engine abstraction — KLineChart is only imported in KLineChartAdapter (Phase 24).
 */
export type ChartEngine = {
  destroy: () => void;
};

export function createChartEnginePlaceholder(): ChartEngine {
  return {
    destroy: () => undefined,
  };
}
