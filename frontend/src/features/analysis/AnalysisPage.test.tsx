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

// Key-echoing translator for the unit tests of `formatAnalysisNarrative`,
// which takes `t` as a parameter: asserting on keys keeps the tests
// copy-independent, so retranslating a string never breaks them.
const stubT = ((key: string, values?: Record<string, string | number>) =>
  values ? `${key} ${Object.values(values).join(" ")}` : key) as Parameters<
  typeof formatAnalysisNarrative
>[1];

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
  const button = await screen.findByTestId("analysis-run");
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

    const title = await screen.findByTestId("analysis-result-title");
    expect(title).toHaveTextContent(/XAUUSD · H1/);
    const meta = screen.getByTestId("analysis-result-meta");
    expect(meta).toHaveTextContent("3");
    expect(await screen.findByTestId("chart-status")).toHaveTextContent("1");
    expect(screen.getByTestId("analysis-view-chart")).toBeInTheDocument();
    expect(screen.getByTestId("analysis-view-recommendation")).toBeInTheDocument();
  });

  it("surfaces an error message when the analysis run fails", async () => {
    vi.spyOn(providersApi, "getProvidersStatus").mockResolvedValue(providersOk);
    vi.spyOn(analysisApi, "runAnalysis").mockRejectedValue(new Error("entitlement limit reached"));

    renderWithProviders(<AnalysisPage />);
    fireEvent.click(await waitForRunEnabled());

    const error = await screen.findByTestId("analysis-error");
    expect(error).toHaveTextContent("entitlement limit reached");
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

    const degraded = await screen.findByTestId("analysis-degraded");
    expect(degraded).toBeInTheDocument();
    expect(screen.getByText("NO_TRADE")).toBeInTheDocument();
    expect(screen.getByText("LLM_UNAVAILABLE")).toBeInTheDocument();
    expect(screen.queryByTestId("analysis-result")).not.toBeInTheDocument();
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
    expect(screen.getByTestId("analysis-run")).toBeDisabled();
  });
});

describe("formatAnalysisNarrative", () => {
  it("formats string and llm_unavailable object shapes", () => {
    expect(formatAnalysisNarrative("plain", stubT)).toBe("plain");
    expect(formatAnalysisNarrative({ llm_unavailable: "missing key" }, stubT)).toBe(
      "analysis.narrative.unavailable missing key",
    );
    expect(formatAnalysisNarrative({ llm: { summary: "Bias bullish" } }, stubT)).toBe(
      "Bias bullish",
    );
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
