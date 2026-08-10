import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "@/components/AppShell";
import { HomePage } from "@/features/dashboard/HomePage";
import { LoginPage } from "@/features/auth/LoginPage";
import { RequireAuth } from "@/features/auth/RequireAuth";
import { ChartPage } from "@/features/chart/ChartPage";
import { ChatPage } from "@/features/chat/ChatPage";
import { AnalysisPage } from "@/features/analysis/AnalysisPage";
import { RecommendationsPage } from "@/features/recommendations/RecommendationsPage";
import { MemoryPage } from "@/features/memory/MemoryPage";
import { WatchlistPage } from "@/features/watchlist/WatchlistPage";
import { AlertsPage } from "@/features/alerts/AlertsPage";
import { JournalPage } from "@/features/journal/JournalPage";
import { PerformancePage } from "@/features/performance/PerformancePage";

const queryClient = new QueryClient();

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route element={<AppShell />}>
            <Route path="/" element={<HomePage />} />
            <Route element={<RequireAuth />}>
              <Route path="/analyst" element={<ChartPage />} />
              <Route path="/chat" element={<ChatPage />} />
              <Route path="/analysis" element={<AnalysisPage />} />
              <Route path="/recommendations" element={<RecommendationsPage />} />
              <Route path="/memory" element={<MemoryPage />} />
              <Route path="/watchlist" element={<WatchlistPage />} />
              <Route path="/alerts" element={<AlertsPage />} />
              <Route path="/journal" element={<JournalPage />} />
              <Route path="/performance" element={<PerformancePage />} />
            </Route>
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
