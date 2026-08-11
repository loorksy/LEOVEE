import { apiFetch } from "@/api/httpClient";
import type { ReplayPreview } from "@/features/replay/ReplayPanel";

export async function previewReplay(body: {
  symbol: string;
  timeframe: string;
  as_of: string;
}): Promise<ReplayPreview> {
  return apiFetch<ReplayPreview>("/api/v1/replay/preview", {
    method: "POST",
    body: JSON.stringify(body),
  });
}
