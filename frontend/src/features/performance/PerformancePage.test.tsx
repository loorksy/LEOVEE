import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "@/test/renderWithProviders";
import { PerformancePage } from "./PerformancePage";
import * as performanceApi from "@/api/performance";

describe("PerformancePage", () => {
  it("renders the performance dashboard with calibration data from the summary endpoint", async () => {
    vi.spyOn(performanceApi, "getPerformanceSummary").mockResolvedValue({
      as_of: "2024-01-01T00:00:00.000Z",
      recommendations: { READY: 2 },
      trade_ideas: 3,
      outcome_records: 5,
      terminal_recommendations: 1,
      calibration: {
        bins: [{ bin_lower: 0.5, bin_upper: 0.6, predicted_count: 4, realized_success_count: 2 }],
        predicted_total: 4,
        realized_success_total: 2,
        rate: 0.5,
      },
      invalidated_rate: 0,
    });

    renderWithProviders(<PerformancePage />);

    expect(await screen.findByTestId("performance-title")).toBeInTheDocument();
    expect(await screen.findByText("3")).toBeInTheDocument();
    expect(screen.getByText("0.500")).toBeInTheDocument();
  });

  it("shows an error message when the summary request fails", async () => {
    vi.spyOn(performanceApi, "getPerformanceSummary").mockRejectedValue(new Error("boom"));

    renderWithProviders(<PerformancePage />);

    expect(await screen.findByTestId("performance-error")).toBeInTheDocument();
  });
});
