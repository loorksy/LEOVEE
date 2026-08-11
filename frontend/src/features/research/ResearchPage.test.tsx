import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ResearchPage } from "./ResearchPage";

const listNews = vi.fn();
vi.mock("../../api/news", () => ({
  listNews: (...args: unknown[]) => listNews(...args),
}));

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ResearchPage />
    </QueryClientProvider>,
  );
}

describe("ResearchPage", () => {
  beforeEach(() => {
    listNews.mockReset();
  });

  it("shows explicit not-configured state without Finnhub", async () => {
    listNews.mockResolvedValue({
      provider: "finnhub",
      provider_configured: false,
      provider_status: "not_configured",
      items: [],
    });
    renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("news-provider-not-configured")).toBeInTheDocument(),
    );
    expect(screen.getByText(/News provider not configured/i)).toBeInTheDocument();
    expect(screen.getByText(/FINNHUB_API_KEY/)).toBeInTheDocument();
    expect(screen.getByText(/not an empty-data state/i)).toBeInTheDocument();
  });

  it("lists news items when provider is configured", async () => {
    listNews.mockResolvedValue({
      provider: "finnhub",
      provider_configured: true,
      provider_status: "ok",
      items: [
        {
          id: "n1",
          headline: "Fed holds",
          source: "Reuters",
          url: "https://example.com",
          published_at: "2026-01-01T00:00:00Z",
        },
      ],
    });
    renderPage();
    await waitFor(() => expect(screen.getByText("Fed holds")).toBeInTheDocument());
  });
});
