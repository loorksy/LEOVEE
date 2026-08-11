import { apiFetch } from "@/api/httpClient";
import type { RecommendationCardData } from "@/features/recommendations/types";

export async function listRecommendationCards(): Promise<{ items: RecommendationCardData[] }> {
  return apiFetch<{ items: RecommendationCardData[] }>("/api/v1/recommendations", {
    query: { cards: true },
  });
}
