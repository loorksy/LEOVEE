import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { logout } from "@/api/auth";
import { useAuth } from "@/hooks/useAuth";

/** LEOVEE_SPEC.md §9 — full sidebar; routes ship incrementally per IMPLEMENTATION_PLAN.md */
const navItems: { to: string; label: string; disabled?: boolean; phase?: string }[] = [
  { to: "/", label: "Home" },
  { to: "/analyst", label: "AI Analyst" },
  { to: "/chat", label: "Chat" },
  { to: "/markets", label: "Markets", disabled: true, phase: "7–8" },
  { to: "/watchlist", label: "Watchlist" },
  { to: "/analysis", label: "Analysis" },
  { to: "/trades", label: "Trades", disabled: true, phase: "27" },
  { to: "/recommendations", label: "Recommendations" },
  { to: "/alerts", label: "Alerts" },
  { to: "/journal", label: "Journal" },
  { to: "/research", label: "Research", disabled: true, phase: "14" },
  { to: "/memory", label: "Memory" },
  { to: "/performance", label: "Performance" },
  { to: "/settings", label: "Settings", disabled: true, phase: "38" },
];

function AuthStatus() {
  const { isAuthenticated } = useAuth();
  const navigate = useNavigate();

  if (!isAuthenticated) {
    return (
      <NavLink to="/login" className="mt-4 block text-xs text-leovee-accent hover:underline">
        Sign in
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
      className="mt-4 text-left text-xs text-slate-500 hover:text-slate-300"
    >
      Sign out
    </button>
  );
}

export function AppShell() {
  return (
    <div className="flex min-h-screen">
      <aside className="flex w-56 flex-col border-r border-slate-800 bg-leovee-panel p-4">
        <div className="mb-8 flex items-center gap-2">
          <img src="/leovee.svg" alt="Leovee" className="h-8 w-8" />
          <span className="text-lg font-semibold tracking-tight">Leovee</span>
        </div>
        <nav className="flex flex-col gap-1 text-sm">
          {navItems.map((item) => (
            <NavLink
              key={item.label}
              to={item.to}
              title={item.disabled ? `Coming in phase ${item.phase}` : undefined}
              className={({ isActive }) =>
                [
                  "rounded-md px-3 py-2 transition-colors",
                  item.disabled ? "cursor-not-allowed text-slate-600" : "text-slate-300 hover:bg-slate-800",
                  isActive && !item.disabled ? "bg-slate-800 text-white" : "",
                ].join(" ")
              }
              onClick={(e) => item.disabled && e.preventDefault()}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto">
          <p className="text-xs text-slate-500">Spec §9 nav · routes roll out by phase</p>
          <AuthStatus />
        </div>
      </aside>
      <main className="flex flex-1 flex-col">
        <Outlet />
      </main>
    </div>
  );
}
