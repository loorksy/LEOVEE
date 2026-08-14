import { screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/renderWithProviders";
import { ResearchPage } from "./ResearchPage";

const listNews = vi.fn();
vi.mock("../../api/news", () => ({
  listNews: (...args: unknown[]) => listNews(...args),
}));

// The shared harness, not a private one: it carries the locale provider the
// translated page (and the provider banner inside it) requires.
function renderPage() {
  return renderWithProviders(<ResearchPage />);
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
    expect(screen.getByTestId("news-provider-not-configured")).toHaveTextContent(
      "FINNHUB_API_KEY",
    );
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
    await waitFor(() => expect(screen.getByTestId("news-n1")).toBeInTheDocument());
    expect(screen.getByTestId("news-n1")).toHaveTextContent("Fed holds");
  });
});
