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
    listNews.mockResolvedValue({
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
  });

  it("lists news items", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText("Fed holds")).toBeInTheDocument());
  });
});
