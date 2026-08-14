import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { EvidenceReport } from "@/api/analysis";
import { LocaleProvider } from "@/i18n/LocaleProvider";
import { EvidencePanel } from "./EvidencePanel";

function renderPanel(report: EvidenceReport) {
  return render(
    <LocaleProvider initialLocale="en">
      <EvidencePanel report={report} />
    </LocaleProvider>,
  );
}

const okCheck = (name: string) => ({
  name,
  status: "ok" as const,
  blocking: true,
  detail: "",
});

describe("EvidencePanel", () => {
  it("lists every check with a localized label", () => {
    renderPanel({
      blocked: false,
      block_reason: null,
      warnings: [],
      checks: [okCheck("live_price"), okCheck("trading_session")],
    });
    expect(screen.getByTestId("evidence-panel")).toBeInTheDocument();
    expect(screen.getByText("Live-price verification")).toBeInTheDocument();
    expect(screen.getByText("Trading session")).toBeInTheDocument();
  });

  it("names the blocking reason when a run is blocked", () => {
    renderPanel({
      blocked: true,
      block_reason: "EVIDENCE_LIVE_PRICE",
      warnings: [],
      checks: [
        { name: "live_price", status: "stale", blocking: true, detail: "newest bar is 22h old" },
      ],
    });
    expect(screen.getByTestId("evidence-blocked-by")).toHaveTextContent("EVIDENCE_LIVE_PRICE");
    // A stale blocking check is called out as blocking, and its detail shown.
    expect(screen.getByText(/blocking/)).toBeInTheDocument();
    expect(screen.getByText(/22h old/)).toBeInTheDocument();
  });

  it("orders checks by the pipeline order regardless of input order", () => {
    renderPanel({
      blocked: false,
      block_reason: null,
      warnings: [],
      checks: [okCheck("live_price"), okCheck("market_structure")],
    });
    const items = screen.getAllByTestId(/^evidence-check-/);
    // market_structure precedes live_price in the pipeline, so it renders first
    // even though it arrived second.
    expect(items[0]).toHaveAttribute("data-testid", "evidence-check-market_structure");
    expect(items[1]).toHaveAttribute("data-testid", "evidence-check-live_price");
  });
});
