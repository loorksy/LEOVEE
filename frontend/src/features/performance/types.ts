export type CalibrationBinPoint = {
  bin_lower: number;
  bin_upper: number;
  predicted_count: number;
  realized_success_count: number;
};

export type PerformanceSummary = {
  as_of: string;
  recommendations: Record<string, number>;
  trade_ideas: number;
  outcome_records: number;
  terminal_recommendations: number;
  calibration: {
    bins: CalibrationBinPoint[];
    predicted_total: number;
    realized_success_total: number;
    rate: number;
  };
  invalidated_rate: number;
};
