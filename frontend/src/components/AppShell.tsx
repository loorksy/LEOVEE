import { NavLink, Outlet } from "react-router-dom";

/** LEOVEE_SPEC.md §9 — full sidebar; routes ship incrementally per IMPLEMENTATION_PLAN.md */
const navItems: { to: string; label: string; disabled?: boolean; phase?: string }[] = [
  { to: "/", label: "Home" },
  { to: "/analyst", label: "AI Analyst", disabled: true, phase: "26+" },
  { to: "/chat", label: "Chat", disabled: true, phase: "26" },
  { to: "/markets", label: "Markets", disabled: true, phase: "7–8" },
  { to: "/watchlist", label: "Watchlist", disabled: true, phase: "29" },
  { to: "/analysis", label: "Analysis", disabled: true, phase: "18–20" },
  { to: "/trades", label: "Trades", disabled: true, phase: "27" },
  { to: "/recommendations", label: "Recommendations", disabled: true, phase: "19–22" },
  { to: "/alerts", label: "Alerts", disabled: true, phase: "30" },
  { to: "/journal", label: "Journal", disabled: true, phase: "31" },
  { to: "/research", label: "Research", disabled: true, phase: "14" },
  { to: "/memory", label: "Memory", disabled: true, phase: "32" },
  { to: "/performance", label: "Performance", disabled: true, phase: "33" },
  { to: "/settings", label: "Settings", disabled: true, phase: "38" },
];

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
        <p className="mt-auto text-xs text-slate-500">Spec §9 nav · routes roll out by phase</p>
      </aside>
      <main className="flex flex-1 flex-col">
        <Outlet />
      </main>
    </div>
  );
}
