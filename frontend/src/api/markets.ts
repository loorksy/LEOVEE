import { apiFetch } from "@/api/httpClient";
import type { BackendCandlePayload } from "@/chart/ChartDataAdapter";

export type CandlesSnapshot = {
  symbol: string;
  timeframe: string;
  workspace_id: string;
  candles: BackendCandlePayload[];
};

export async function getCandles(
  symbol: string,
  timeframe: string,
  count = 200,
): Promise<CandlesSnapshot> {
  return apiFetch<CandlesSnapshot>(`/api/v1/markets/${symbol}/candles`, {
    query: { timeframe, count },
  });
}
