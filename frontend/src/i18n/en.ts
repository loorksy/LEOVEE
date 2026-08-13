import type { Dictionary } from "./types";

/** English — must define exactly the keys `ar.ts` defines; the parity test enforces it. */
export const en: Dictionary = {
  "app.name": "Leovee",

  "nav.home": "Home",
  "nav.analyst": "AI Analyst",
  "nav.chat": "Chat",
  "nav.markets": "Markets",
  "nav.watchlist": "Watchlist",
  "nav.analysis": "Analysis",
  "nav.recommendations": "Recommendations",
  "nav.journal": "Journal",
  "nav.memory": "Memory",
  "nav.performance": "Performance",
  "nav.settings": "Settings",

  "auth.login": "Log in",
  "auth.logout": "Log out",
  "auth.signup": "Sign up",
  "auth.email": "Email",
  "auth.password": "Password",

  "direction.buy": "Buy",
  "direction.sell": "Sell",

  "tradability.now": "Tradable now",
  "tradability.soon": "Soon",
  "tradability.watchOnly": "Watch only",

  "plan.immediate": "Immediate plan",
  "plan.anticipatory": "Anticipatory plan",
  "plan.conditional": "Conditional plan",

  "evidence.noStatisticalSupport": "Direct analysis, no statistical support",

  "analysis.blocked": "Analysis could not be completed",
  "analysis.blockedReason": "Reason: {reason}",
  "analysis.running": "Analysing…",

  "common.retry": "Retry",
  "common.cancel": "Cancel",
  "common.save": "Save",
  "common.loading": "Loading…",
};
