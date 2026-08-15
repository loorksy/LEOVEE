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
          symbol: "XAUUSD",
          direction: "BUY",
          status: "READY",
          confidence: 0.72,
          headline: "XAUUSD BUY",
          thesis: "Bullish structure break",
          badges: ["READY", "conf:72%"],
        },
      ],
    });

    renderWithProviders(<RecommendationsPage />);

    expect(await screen.findByText("XAUUSD BUY")).toBeInTheDocument();
    expect(screen.getByText("Bullish structure break")).toBeInTheDocument();
  });

  it("shows an empty state when there are no recommendations", async () => {
    vi.spyOn(recommendationsApi, "listRecommendationCards").mockResolvedValue({ items: [] });

    renderWithProviders(<RecommendationsPage />);

    expect(await screen.findByTestId("recommendations-empty")).toBeInTheDocument();
  });

  it("shows the tradability badge for a card that carries an assessment", async () => {
    vi.spyOn(recommendationsApi, "listRecommendationCards").mockResolvedValue({
      items: [
        {
          id: "rec-2",
          symbol: "XAUUSD",
          direction: "SELL",
          status: "READY",
          confidence: 0.61,
          headline: "XAUUSD SELL",
          thesis: "Rejection at supply",
          badges: ["READY"],
          tradability: "soon",
          tradability_reason: "entry is 40 pips away",
        },
      ],
    });

    renderWithProviders(<RecommendationsPage />);

    expect(await screen.findByTestId("recommendation-card-rec-2-tradability")).toBeInTheDocument();
    expect(screen.getByText("entry is 40 pips away")).toBeInTheDocument();
  });

  it("never renders a card whose tradability was rejected", async () => {
    vi.spyOn(recommendationsApi, "listRecommendationCards").mockResolvedValue({
      items: [
        {
          id: "rec-3",
          symbol: "XAUUSD",
          direction: "BUY",
          status: "READY",
          confidence: 0.5,
          headline: "XAUUSD BUY — rejected",
          badges: ["READY"],
          tradability: "rejected",
          tradability_reason: "price already ran through the entry",
        },
      ],
    });

    renderWithProviders(<RecommendationsPage />);

    // The empty state is the observable proof the filtered list rendered
    // nothing — querying for the absence of a card by testid would pass
    // trivially even if the whole page failed to render.
    expect(await screen.findByTestId("recommendations-empty")).toBeInTheDocument();
    expect(screen.queryByText("XAUUSD BUY — rejected")).not.toBeInTheDocument();
  });
});
