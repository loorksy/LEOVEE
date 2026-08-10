export type MemoryListItem = {
  id: string;
  key: string;
  type: string;
  content?: Record<string, unknown>;
  confidence?: number | null;
  low_sample?: boolean;
};

export type CalibrationBin = {
  bin_lower: number;
  bin_upper: number;
  predicted_count: number;
  realized_success_count: number;
};
