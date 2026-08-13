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

  "telegram.title": "Telegram",
  "telegram.intro": "Link your account to talk to the agent from Telegram. **Nothing is ever sent unless you ask** — no alerts, no summaries.",
  "telegram.generate": "Generate a link code",
  "telegram.codeLabel": "Send this code to the agent on Telegram",
  "telegram.expires": "Expires",
  "telegram.linked": "Linked accounts",
  "telegram.none": "No account linked.",
  "telegram.revoke": "Unlink",
  "telegram.lastMessage": "Last message",
  "telegram.never": "Never messaged",
};
