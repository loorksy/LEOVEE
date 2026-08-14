import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { LocaleProvider } from "@/i18n/LocaleProvider";
import { ReplayPage } from "@/features/replay/ReplayPage";

vi.mock("@/api/replay", () => ({
  previewReplay: vi.fn(),
}));

describe("ReplayPage", () => {
  it("renders replay controls", () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <LocaleProvider initialLocale="ar">
          <MemoryRouter>
            <ReplayPage />
          </MemoryRouter>
        </LocaleProvider>
      </QueryClientProvider>,
    );
    expect(screen.getByTestId("replay-title")).toBeInTheDocument();
    expect(screen.getByTestId("replay-preview-button")).toBeInTheDocument();
  });
});
