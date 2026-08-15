import { useEffect, useRef, useState } from "react";
import { Menu, PanelLeftClose, PanelLeftOpen, X } from "lucide-react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { logout } from "@/api/auth";
import { cn } from "@/lib/cn";
import { useAuth } from "@/hooks/useAuth";
import { WorkspaceBootstrap } from "@/features/workspace/WorkspaceBootstrap";
import { useLocale } from "@/i18n/context";
import { LocaleSwitcher } from "@/i18n/LocaleSwitcher";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { IconButton } from "@/components/ui/IconButton";
import { NAV_ITEMS, type NavItem } from "@/components/shell/navConfig";

const FOCUS_RING =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-sidebar";

/**
 * Shared geometry for every rail destination, desktop and drawer alike.
 * 44px touch target, tightened to 40px from `lg` where the pointer is a mouse
 * (DESIGN.md §8). `aria-label`/`title` are set unconditionally on the link
 * itself so the accessible name is correct whether or not the visible label
 * text is CSS-hidden (tablet icon rail, collapsed desktop rail) — no JS
 * breakpoint tracking needed to keep it right.
 *
 * `isActive` is threaded in explicitly rather than read off a `.active` CSS
 * class: NavLink only auto-applies that class when `className` is left
 * untouched, and this needs a computed class list, so the render-prop form
 * (`children`/`className` as a function of `{ isActive }`) is the only
 * correct source for it here.
 */
function navLinkClass(iconOnly: boolean, isActive: boolean): string {
  return cn(
    "group relative flex min-h-11 items-center gap-3 rounded-lg px-3 text-sm font-medium transition-colors duration-150 lg:min-h-10",
    isActive
      ? "bg-sidebar-active-bg text-sidebar-active-text"
      : "text-muted-foreground hover:bg-muted hover:text-foreground",
    FOCUS_RING,
    iconOnly && "md:justify-center md:px-0",
  );
}

function ActiveMarker({ active }: { active: boolean }) {
  if (!active) return null;
  return (
    <span
      aria-hidden
      className="pointer-events-none absolute inset-y-2 start-0 w-0.5 rounded-full bg-foreground"
    />
  );
}

function NavLinks({
  onNavigate,
  testIdPrefix,
  iconOnly,
}: {
  onNavigate?: () => void;
  testIdPrefix: string;
  iconOnly: boolean;
}) {
  const { t } = useLocale();
  return (
    <nav aria-label={t("shell.navigation")} className="flex flex-1 flex-col gap-0.5 overflow-y-auto p-2">
      {NAV_ITEMS.map((item: NavItem) => {
        const label = t(item.labelKey);
        const Icon = item.icon;
        return (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            onClick={onNavigate}
            data-testid={`${testIdPrefix}${item.testId.replace(/^nav-/, "")}`}
            aria-label={label}
            title={label}
            className={({ isActive }) => navLinkClass(iconOnly, isActive)}
          >
            {({ isActive }) => (
              <>
                <ActiveMarker active={isActive} />
                <Icon className="size-4 shrink-0" aria-hidden />
                <span className={cn("truncate", iconOnly && "hidden lg:inline")}>{label}</span>
              </>
            )}
          </NavLink>
        );
      })}
    </nav>
  );
}

function AuthStatus() {
  const { t } = useLocale();
  const { isAuthenticated } = useAuth();
  const navigate = useNavigate();

  if (!isAuthenticated) {
    return (
      <NavLink
        to="/login"
        className={cn(
          "inline-flex h-11 items-center rounded-md px-3 text-sm font-medium text-primary hover:underline sm:h-9",
          FOCUS_RING,
        )}
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
      className={cn(
        "inline-flex h-11 items-center rounded-md px-3 text-sm text-muted-foreground hover:text-foreground sm:h-9",
        FOCUS_RING,
      )}
      data-testid="nav-signout"
    >
      {t("auth.logout")}
    </button>
  );
}

function Brand({ compact = false }: { compact?: boolean }) {
  const { t } = useLocale();
  return (
    <NavLink to="/" className={cn("flex min-w-0 items-center gap-2 rounded-lg", FOCUS_RING)}>
      <img src="/leovee.svg" alt="" className="size-8 shrink-0" />
      {!compact && (
        <span className="truncate text-[15px] font-semibold tracking-tight text-foreground">
          {t("app.name")}
        </span>
      )}
    </NavLink>
  );
}

/**
 * One responsive shell for every route, including `/admin` — there is no
 * separate admin chrome; `AdminPage` gates its own panels by role. Three
 * tiers, mobile-first (DESIGN.md §8):
 *
 * - **< md (phones):** no persistent rail — a hamburger opens a full drawer.
 * - **md–lg (tablets):** an icon-only rail, CSS-driven (no JS breakpoint
 *   tracking): the label span is `hidden lg:inline`.
 * - **≥ lg (laptop/desktop):** the full rail, optionally collapsed by hand
 *   to the same icon-only width.
 *
 * The persistent rail and the mobile drawer render the SAME nav items but
 * never both carry the canonical `nav-*` test ids at once: the drawer's
 * links are prefixed (`mobile-nav-*`) precisely so opening it can never
 * produce a duplicate-test-id collision with the always-mounted rail.
 */
export function AppShell() {
  const { t, dir } = useLocale();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const drawerRef = useRef<HTMLElement | null>(null);
  const openerRef = useRef<HTMLButtonElement | null>(null);

  // Close the drawer on every navigation rather than leaving it open behind
  // the new page — the common source of a "why is the menu still open" bug.
  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    if (!mobileOpen) return;
    document.body.style.overflow = "hidden";
    // Captured now, not read from the ref in the cleanup below: by the time
    // cleanup runs the drawer has unmounted and the button that opened it may
    // have too, so both are snapshotted at effect-setup time.
    const drawer = drawerRef.current;
    const opener = openerRef.current;
    const selector = 'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])';
    const focusables = () => Array.from(drawer?.querySelectorAll<HTMLElement>(selector) ?? []);
    focusables()[0]?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setMobileOpen(false);
        return;
      }
      if (event.key !== "Tab") return;
      const nodes = focusables();
      if (!nodes.length) return;
      const first = nodes[0]!;
      const last = nodes[nodes.length - 1]!;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = "";
      document.removeEventListener("keydown", onKeyDown);
      opener?.focus();
    };
  }, [mobileOpen]);

  return (
    <div dir={dir} data-testid="app-shell" className="flex h-dvh overflow-hidden bg-background">
      <WorkspaceBootstrap />

      {/* Persistent rail — hidden on phones, icon-only on tablets, full (or
          manually collapsed to icon-only) at lg+. Always mounted: this is
          the one place the canonical nav-* test ids live. */}
      <aside
        data-testid="app-sidebar"
        className={cn(
          "hidden shrink-0 flex-col border-e border-sidebar-border bg-sidebar text-sidebar-foreground transition-[width] duration-200 md:flex md:w-16",
          collapsed ? "lg:w-16" : "lg:w-64",
        )}
      >
        <div
          className={cn(
            "flex h-14 shrink-0 items-center border-b border-sidebar-border px-3",
            collapsed ? "lg:justify-center" : "justify-center lg:justify-between",
          )}
        >
          <div className={cn(collapsed ? "lg:hidden" : "hidden lg:block")}>
            <Brand compact={collapsed} />
          </div>
          <div className={cn(collapsed ? "hidden lg:block" : "block md:hidden lg:hidden")} aria-hidden>
            <img src="/leovee.svg" alt="" className="size-8" />
          </div>
          <IconButton
            aria-label={collapsed ? t("shell.expandSidebar") : t("shell.collapseSidebar")}
            title={collapsed ? t("shell.expandSidebar") : t("shell.collapseSidebar")}
            onClick={() => setCollapsed((value) => !value)}
            className="hidden lg:inline-flex"
          >
            {collapsed ? (
              <PanelLeftOpen className="size-4 rtl:-scale-x-100" aria-hidden />
            ) : (
              <PanelLeftClose className="size-4 rtl:-scale-x-100" aria-hidden />
            )}
          </IconButton>
        </div>
        <NavLinks testIdPrefix="nav-" iconOnly={!collapsed} />
      </aside>

      {/* Mobile drawer — only ever mounted while open, so it can never
          coexist with a duplicate set of the rail's test ids. */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 md:hidden" data-testid="app-mobile-drawer">
          <button
            type="button"
            className="absolute inset-0 bg-black/60"
            aria-label={t("shell.closeMenu")}
            onClick={() => setMobileOpen(false)}
          />
          <aside
            ref={drawerRef}
            role="dialog"
            aria-modal="true"
            aria-label={t("shell.navigation")}
            className="absolute inset-y-0 start-0 flex w-[min(85vw,18rem)] flex-col border-e border-sidebar-border bg-sidebar text-sidebar-foreground shadow-xl"
          >
            <div className="flex h-14 shrink-0 items-center justify-between border-b border-sidebar-border px-3">
              <Brand />
              <IconButton aria-label={t("shell.closeMenu")} onClick={() => setMobileOpen(false)}>
                <X className="size-5" aria-hidden />
              </IconButton>
            </div>
            <NavLinks
              onNavigate={() => setMobileOpen(false)}
              testIdPrefix="mobile-nav-"
              iconOnly={false}
            />
          </aside>
        </div>
      )}

      <div className="relative flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-background">
        <header
          data-testid="app-topbar"
          className="flex h-14 shrink-0 items-center gap-2 border-b border-border px-3 sm:px-4"
        >
          <IconButton
            ref={openerRef}
            aria-label={t("shell.openMenu")}
            onClick={() => setMobileOpen(true)}
            className="md:hidden"
          >
            <Menu className="size-5" aria-hidden />
          </IconButton>
          <div className="min-w-0 flex-1 md:hidden">
            <Brand />
          </div>
          <div className="ms-auto flex items-center gap-2 sm:gap-3">
            <LocaleSwitcher />
            <ThemeToggle />
            <AuthStatus />
          </div>
        </header>
        <main
          data-testid="app-main"
          className="flex min-h-0 flex-1 flex-col overflow-y-auto"
        >
          <Outlet />
        </main>
      </div>
    </div>
  );
}
