import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { logout } from "@/api/auth";
import { useAuth } from "@/hooks/useAuth";
import { WorkspaceBootstrap } from "@/features/workspace/WorkspaceBootstrap";
import { useLocale } from "@/i18n/context";
import { LocaleSwitcher } from "@/i18n/LocaleSwitcher";
import type { TranslationKey } from "@/i18n";

/** LEOVEE_SPEC.md §9 — full sidebar; routes ship incrementally per IMPLEMENTATION_PLAN.md */
const navItems: { to: string; labelKey: TranslationKey; testId: string; disabled?: boolean; phase?: string }[] = [
  { to: "/", labelKey: "nav.home", testId: "nav-home" },
  { to: "/analyst", labelKey: "nav.analyst", testId: "nav-analyst" },
  { to: "/chat", labelKey: "nav.chat", testId: "nav-chat" },
  { to: "/markets", labelKey: "nav.markets", testId: "nav-markets" },
  { to: "/watchlist", labelKey: "nav.watchlist", testId: "nav-watchlist" },
  { to: "/analysis", labelKey: "nav.analysis", testId: "nav-analysis" },
  { to: "/trades", labelKey: "nav.trades", testId: "nav-trades" },
  { to: "/recommendations", labelKey: "nav.recommendations", testId: "nav-recommendations" },
  { to: "/alerts", labelKey: "nav.alerts", testId: "nav-alerts" },
  { to: "/journal", labelKey: "nav.journal", testId: "nav-journal" },
  { to: "/research", labelKey: "nav.research", testId: "nav-research" },
  { to: "/memory", labelKey: "nav.memory", testId: "nav-memory" },
  { to: "/performance", labelKey: "nav.performance", testId: "nav-performance" },
  { to: "/replay", labelKey: "nav.replay", testId: "nav-replay" },
  { to: "/admin", labelKey: "nav.admin", testId: "nav-admin" },
  { to: "/settings", labelKey: "nav.settings", testId: "nav-settings" },
];

function AuthStatus() {
  const { t } = useLocale();
  const { isAuthenticated } = useAuth();
  const navigate = useNavigate();

  if (!isAuthenticated) {
    return (
      <NavLink
        to="/login"
        className="mt-4 block text-xs text-leovee-accent hover:underline"
        data-testid="nav-signin"
      >
        {t("auth.login")}
      </NavLink>
    );
  }
  return (
    <button
      type="button"
      onClick={() => {
        logout();
        navigate("/login", { replace: true });
      }}
      className="mt-4 text-start text-xs text-slate-500 hover:text-slate-300"
      data-testid="nav-signout"
    >
      {t("auth.logout")}
    </button>
  );
}

export function AppShell() {
  const { t } = useLocale();
  return (
    <div className="flex min-h-screen">
      <WorkspaceBootstrap />
      <aside className="flex w-56 flex-col border-e border-slate-800 bg-leovee-panel p-4">
        <div className="mb-8 flex items-center gap-2">
          <img src="/leovee.svg" alt={t("app.name")} className="h-8 w-8" />
          <span className="text-lg font-semibold tracking-tight">{t("app.name")}</span>
        </div>
        <nav className="flex flex-col gap-1 text-sm">
          {navItems.map((item) => (
            <NavLink
              key={item.labelKey}
              to={item.to}
              data-testid={item.testId}
              title={item.disabled ? t("nav.comingInPhase", { phase: item.phase ?? "" }) : undefined}
              className={({ isActive }) =>
                [
                  "rounded-md px-3 py-2 transition-colors",
                  item.disabled ? "cursor-not-allowed text-slate-600" : "text-slate-300 hover:bg-slate-800",
                  isActive && !item.disabled ? "bg-slate-800 text-white" : "",
                ].join(" ")
              }
              onClick={(e) => item.disabled && e.preventDefault()}
            >
              {t(item.labelKey)}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto flex flex-col gap-3">
          <LocaleSwitcher />
          <p className="text-xs text-slate-500">{t("nav.specNote")}</p>
          <AuthStatus />
        </div>
      </aside>
      <main className="flex flex-1 flex-col">
        <Outlet />
      </main>
    </div>
  );
}
