import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { ErrorBoundary } from "@/app/ErrorBoundary";
import { AppShell } from "@/components/AppShell";
import { HomePage } from "@/features/dashboard/HomePage";
import { LoginPage } from "@/features/auth/LoginPage";
import { SignupPage } from "@/features/auth/SignupPage";
import { RequireAuth } from "@/features/auth/RequireAuth";
import { ChatPage } from "@/features/chat/ChatPage";
import { AnalysisPage } from "@/features/analysis/AnalysisPage";
import { RecommendationsPage } from "@/features/recommendations/RecommendationsPage";
import { MemoryPage } from "@/features/memory/MemoryPage";
import { WatchlistPage } from "@/features/watchlist/WatchlistPage";
import { AlertsPage } from "@/features/alerts/AlertsPage";
import { JournalPage } from "@/features/journal/JournalPage";
import { PerformancePage } from "@/features/performance/PerformancePage";
import { AdminPage } from "@/features/admin/AdminPage";
import { ReplayPage } from "@/features/replay/ReplayPage";
import { MarketsPage } from "@/features/markets/MarketsPage";
import { TradesPage } from "@/features/trades/TradesPage";
import { ResearchPage } from "@/features/research/ResearchPage";
import { SettingsPage } from "@/features/settings/SettingsPage";

const queryClient = new QueryClient();

/** The chart lives inside /chat now (a companion pane/sheet, not a page).
 *  A bare `<Navigate>` drops query params — preserved here so a bookmarked
 *  or already-shared `/analyst?symbol=...&timeframe=...` still opens the
 *  right instrument instead of a blank chat. */
function AnalystRedirect() {
  const location = useLocation();
  const params = new URLSearchParams(location.search);
  params.set("chart", "1");
  return <Navigate to={`/chat?${params.toString()}`} replace />;
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ErrorBoundary>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/signup" element={<SignupPage />} />
            <Route element={<AppShell />}>
              <Route path="/" element={<HomePage />} />
              <Route element={<RequireAuth />}>
                <Route path="/analyst" element={<AnalystRedirect />} />
                <Route path="/chat" element={<ChatPage />} />
                <Route path="/markets" element={<MarketsPage />} />
                <Route path="/analysis" element={<AnalysisPage />} />
                <Route path="/recommendations" element={<RecommendationsPage />} />
                <Route path="/trades" element={<TradesPage />} />
                <Route path="/memory" element={<MemoryPage />} />
                <Route path="/watchlist" element={<WatchlistPage />} />
                <Route path="/alerts" element={<AlertsPage />} />
                <Route path="/journal" element={<JournalPage />} />
                <Route path="/research" element={<ResearchPage />} />
                <Route path="/performance" element={<PerformancePage />} />
                <Route path="/replay" element={<ReplayPage />} />
                <Route path="/admin" element={<AdminPage />} />
                <Route path="/settings" element={<SettingsPage />} />
              </Route>
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </ErrorBoundary>
    </QueryClientProvider>
  );
}
