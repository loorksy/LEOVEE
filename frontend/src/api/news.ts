import { apiFetch } from "@/api/httpClient";

export type NewsItem = {
  id: string;
  headline: string;
  source: string | null;
  published_at: string;
  url: string | null;
};

export async function listNews(currency?: string): Promise<{ items: NewsItem[] }> {
  return apiFetch("/api/v1/news", {
    query: currency ? { currency, limit: 30 } : { limit: 30 },
  });
}
