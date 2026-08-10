import { NavLink, Outlet } from "react-router-dom";

const navItems = [
  { to: "/", label: "Home" },
  { to: "/", label: "AI Analyst", disabled: true },
  { to: "/", label: "Chat", disabled: true },
];

export function AppShell() {
  return (
    <div className="flex min-h-screen">
      <aside className="flex w-56 flex-col border-r border-slate-800 bg-leovee-panel p-4">
        <div className="mb-8 flex items-center gap-2">
          <img src="/leovee.svg" alt="" className="h-8 w-8" />
          <span className="text-lg font-semibold tracking-tight">Leovee</span>
        </div>
        <nav className="flex flex-col gap-1 text-sm">
          {navItems.map((item) => (
            <NavLink
              key={item.label}
              to={item.to}
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
        <p className="mt-auto text-xs text-slate-500">Phase 2 scaffold</p>
      </aside>
      <main className="flex flex-1 flex-col">
        <Outlet />
      </main>
    </div>
  );
}
