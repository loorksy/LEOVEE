import { describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "@/test/renderWithProviders";
import {
  AnalysisPage,
  formatAnalysisNarrative,
  getAnalysisDegradedReason,
} from "./AnalysisPage";
import * as analysisApi from "@/api/analysis";
import * as chartApi from "@/api/chart";
import * as providersApi from "@/api/providers";

const runResponse: analysisApi.AnalysisRunResponse = {
  agent_run_id: "run-1",
  workspace_id: "ws-1",
  symbol: "XAUUSD",
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

const providersOk = {
  finnhub: { configured: true, status: "ok" as const },
  oanda: { configured: true, status: "ok" as const, environment: "practice" },
  anthropic: { configured: true, status: "ok" as const },
  openai: { configured: false, status: "not_configured" as const },
  openrouter: { configured: false, status: "not_configured" as const },
};

async function waitForRunEnabled() {
  const button = await screen.findByRole("button", { name: /run analysis/i });
  await waitFor(() => expect(button).not.toBeDisabled());
  return button;
}

describe("AnalysisPage", () => {
  it("runs analysis and displays the decision plus recall count", async () => {
    vi.spyOn(providersApi, "getProvidersStatus").mockResolvedValue(providersOk);
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
    fireEvent.click(await waitForRunEnabled());

    expect(await screen.findByText(/XAUUSD · H1 — BUY/)).toBeInTheDocument();
    expect(screen.getByText(/recalled 3 memories/i)).toBeInTheDocument();
    expect(await screen.findByTestId("chart-status")).toHaveTextContent(
      "1 chart annotation(s) published",
    );
    expect(screen.getByRole("button", { name: /view chart/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /view recommendation/i })).toBeInTheDocument();
  });

  it("surfaces an error message when the analysis run fails", async () => {
    vi.spyOn(providersApi, "getProvidersStatus").mockResolvedValue(providersOk);
    vi.spyOn(analysisApi, "runAnalysis").mockRejectedValue(new Error("entitlement limit reached"));

    renderWithProviders(<AnalysisPage />);
    fireEvent.click(await waitForRunEnabled());

    expect(await screen.findByText("entitlement limit reached")).toBeInTheDocument();
  });

  it("renders LLM unavailable as an explicit degraded NO_TRADE state", async () => {
    vi.spyOn(providersApi, "getProvidersStatus").mockResolvedValue(providersOk);
    vi.spyOn(analysisApi, "runAnalysis").mockResolvedValue({
      ...runResponse,
      decision: {
        direction: "NO_TRADE",
        confidence: null,
        degraded: true,
        degraded_reason: "LLM_UNAVAILABLE",
      },
      narrative: { llm_unavailable: "No LLM provider API key configured" },
      recommendation_id: undefined,
    });
    vi.spyOn(chartApi, "buildSemanticModel").mockResolvedValue({
      model: { version: 1, operations: [] },
    });

    renderWithProviders(<AnalysisPage />);
    fireEvent.click(await waitForRunEnabled());

    expect(await screen.findByTestId("analysis-degraded")).toBeInTheDocument();
    expect(screen.getByText(/analysis degraded/i)).toBeInTheDocument();
    expect(screen.getByText("NO_TRADE")).toBeInTheDocument();
    expect(screen.getByText("LLM_UNAVAILABLE")).toBeInTheDocument();
    expect(screen.queryByText(/XAUUSD · H1 — BUY/)).not.toBeInTheDocument();
    expect(screen.queryByText(/N\/A/)).not.toBeInTheDocument();
  });

  it("shows provider banners and disables run when OANDA or LLM is missing", async () => {
    vi.spyOn(providersApi, "getProvidersStatus").mockResolvedValue({
      ...providersOk,
      oanda: { configured: false, status: "not_configured", environment: "practice" },
      anthropic: { configured: false, status: "not_configured" },
    });

    renderWithProviders(<AnalysisPage />);

    expect(await screen.findByTestId("analysis-oanda-not-configured")).toBeInTheDocument();
    expect(screen.getByTestId("analysis-llm-not-configured")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /run analysis/i })).toBeDisabled();
  });
});

describe("formatAnalysisNarrative", () => {
  it("formats string and llm_unavailable object shapes", () => {
    expect(formatAnalysisNarrative("plain")).toBe("plain");
    expect(formatAnalysisNarrative({ llm_unavailable: "missing key" })).toBe(
      "Narrative unavailable: missing key",
    );
    expect(formatAnalysisNarrative({ llm: { summary: "Bias bullish" } })).toBe("Bias bullish");
  });
});

describe("getAnalysisDegradedReason", () => {
  it("reads degraded_reason from decision or narrative", () => {
    expect(
      getAnalysisDegradedReason({
        ...runResponse,
        decision: { direction: "NO_TRADE", degraded_reason: "LLM_UNAVAILABLE" },
      }),
    ).toBe("LLM_UNAVAILABLE");
    expect(
      getAnalysisDegradedReason({
        ...runResponse,
        decision: { direction: "NO_TRADE" },
        narrative: { llm_unavailable: "missing" },
      }),
    ).toBe("LLM_UNAVAILABLE");
  });
});
