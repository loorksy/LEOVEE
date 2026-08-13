import type { ReactElement } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { render } from "@testing-library/react";
import { LocaleProvider } from "@/i18n/LocaleProvider";
import type { Locale } from "@/i18n";

/**
 * Shared test harness: React Query, Router and locale, matching the real shell.
 *
 * The locale provider belongs here and not in each test. `useLocale` throws
 * outside a provider — deliberately, so a component cannot silently render in
 * the wrong direction — which meant every translated component was untestable
 * until the harness carried it. The scaffold landed before any component used
 * it, so nothing noticed.
 *
 * The locale is pinned to Arabic by default rather than resolved from storage,
 * because a test that reads `navigator.language` passes or fails depending on
 * the machine it runs on.
 */
export function renderWithProviders(
  ui: ReactElement,
  { route = "/", locale = "ar" as Locale }: { route?: string; locale?: Locale } = {},
) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return {
    queryClient,
    ...render(
      <QueryClientProvider client={queryClient}>
        <LocaleProvider initialLocale={locale}>
          <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
        </LocaleProvider>
      </QueryClientProvider>,
    ),
  };
}
