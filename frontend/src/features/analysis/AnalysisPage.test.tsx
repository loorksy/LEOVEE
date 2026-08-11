import { describe, expect, it, vi } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import { renderWithProviders } from "@/test/renderWithProviders";
import { AnalysisPage } from "./AnalysisPage";
import * as analysisApi from "@/api/analysis";
import * as chartApi from "@/api/chart";

const runResponse: analysisApi.AnalysisRunResponse = {
  agent_run_id: "run-1",
  workspace_id: "ws-1",
  symbol: "EURUSD",
  timeframe: "H1",
  perceive: {},
  recall: { count: 3 },
  engines: { structure: {} },
  decision: { direction: "BUY", confidence: 0.68 },
  narrative: "Bullish structure break with liquidity sweep confirmation.",
  as_of: "2024-01-01T12:00:00.000Z",
  recommendation_id: "rec-1",
  thesis_id: "thesis-1",
};

describe("AnalysisPage", () => {
  it("runs analysis and displays the decision plus recall count", async () => {
    vi.spyOn(analysisApi, "runAnalysis").mockResolvedValue(runResponse);
    vi.spyOn(chartApi, "buildSemanticModel").mockResolvedValue({
      model: { version: 1, operations: [{ semantic_type: "DRAW_LEVEL", geometry: { anchors: [] } }] },
    });
    vi.spyOn(chartApi, "persistSemanticModel").mockResolvedValue({
      ids: ["ann-1"],
      count: 1,
      version: 1,
    });

    renderWithProviders(<AnalysisPage />);

    fireEvent.click(screen.getByRole("button", { name: /run analysis/i }));

    expect(await screen.findByText(/EURUSD · H1 — BUY/)).toBeInTheDocument();
    expect(screen.getByText(/recalled 3 memories/i)).toBeInTheDocument();
    expect(await screen.findByTestId("chart-status")).toHaveTextContent(
      "1 chart annotation(s) published",
    );
    expect(screen.getByRole("button", { name: /view chart/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /view recommendation/i })).toBeInTheDocument();
  });

  it("surfaces an error message when the analysis run fails", async () => {
    vi.spyOn(analysisApi, "runAnalysis").mockRejectedValue(new Error("entitlement limit reached"));

    renderWithProviders(<AnalysisPage />);
    fireEvent.click(screen.getByRole("button", { name: /run analysis/i }));

    expect(await screen.findByText("entitlement limit reached")).toBeInTheDocument();
  });
});
