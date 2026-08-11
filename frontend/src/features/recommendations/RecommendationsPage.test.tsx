import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "@/test/renderWithProviders";
import { RecommendationsPage } from "./RecommendationsPage";
import * as recommendationsApi from "@/api/recommendations";

describe("RecommendationsPage", () => {
  it("renders recommendation cards from the API", async () => {
    vi.spyOn(recommendationsApi, "listRecommendationCards").mockResolvedValue({
      items: [
        {
          id: "rec-1",
          symbol: "EURUSD",
          direction: "BUY",
          status: "READY",
          confidence: 0.72,
          headline: "EURUSD BUY",
          thesis: "Bullish structure break",
          badges: ["READY", "conf:72%"],
        },
      ],
    });

    renderWithProviders(<RecommendationsPage />);

    expect(await screen.findByText("EURUSD BUY")).toBeInTheDocument();
    expect(screen.getByText("Bullish structure break")).toBeInTheDocument();
  });

  it("shows an empty state when there are no recommendations", async () => {
    vi.spyOn(recommendationsApi, "listRecommendationCards").mockResolvedValue({ items: [] });

    renderWithProviders(<RecommendationsPage />);

    expect(await screen.findByText(/no recommendations yet/i)).toBeInTheDocument();
  });
});
