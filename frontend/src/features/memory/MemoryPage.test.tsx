import { describe, expect, it, vi } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import { renderWithProviders } from "@/test/renderWithProviders";
import { MemoryPage } from "./MemoryPage";
import * as memoryApi from "@/api/memory";

describe("MemoryPage", () => {
  it("lists memories and calibration bins", async () => {
    vi.spyOn(memoryApi, "listMemories").mockResolvedValue({
      items: [{ id: "mem-1", key: "eurusd.sweep.bias", type: "SEMANTIC" }],
    });
    vi.spyOn(memoryApi, "getCalibrationCurve").mockResolvedValue({
      bins: [{ bin_lower: 0.5, bin_upper: 0.6, predicted_count: 4, realized_success_count: 2 }],
    });

    renderWithProviders(<MemoryPage />);

    expect(await screen.findByText("eurusd.sweep.bias")).toBeInTheDocument();
  });

  it("deletes a memory and surfaces recompute statistics", async () => {
    vi.spyOn(memoryApi, "listMemories").mockResolvedValue({
      items: [{ id: "mem-1", key: "eurusd.sweep.bias", type: "SEMANTIC" }],
    });
    vi.spyOn(memoryApi, "getCalibrationCurve").mockResolvedValue({ bins: [] });
    const deleteSpy = vi.spyOn(memoryApi, "deleteMemory").mockResolvedValue({
      deleted: true,
      recompute: { orphan_embeddings_removed: 0, embeddings_indexed: 1 },
    });

    renderWithProviders(<MemoryPage />);

    fireEvent.click(await screen.findByRole("button", { name: /delete/i }));

    expect(deleteSpy).toHaveBeenCalledWith("mem-1");
    expect(await screen.findByTestId("recompute-stats")).toHaveTextContent("embeddings_indexed");
  });
});
