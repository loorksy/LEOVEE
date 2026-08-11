import { apiFetch } from "@/api/httpClient";

export type TradeItem = {
  id: string;
  symbol?: string | null;
  direction: string;
  status?: string;
  entry?: number | null;
  stop?: number | null;
  targets?: number[];
};

export async function listTrades(): Promise<{ items: TradeItem[] }> {
  return apiFetch("/api/v1/trades");
}

export async function createTradeIdea(body: {
  symbol: string;
  direction: "BUY" | "SELL";
  entry?: number;
  stop?: number;
}): Promise<{ id: string }> {
  return apiFetch("/api/v1/trades", {
    method: "POST",
    body: { ...body, execution_enabled: false },
  });
}
