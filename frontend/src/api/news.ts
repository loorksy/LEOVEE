import { apiFetch } from "@/api/httpClient";

export type NewsItem = {
  id: string;
  headline: string;
  source: string | null;
  published_at: string;
  url: string | null;
};

export type NewsListResponse = {
  items: NewsItem[];
  provider: string;
  provider_configured: boolean;
  provider_status: string;
};

export async function listNews(currency?: string): Promise<NewsListResponse> {
  return apiFetch("/api/v1/news", {
    query: currency ? { currency, limit: 30 } : { limit: 30 },
  });
}
