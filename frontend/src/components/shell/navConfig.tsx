import {
  Activity,
  BarChart3,
  Bell,
  BookOpen,
  Brain,
  Eye,
  FlaskConical,
  Home,
  type LucideIcon,
  MessageSquare,
  RotateCcw,
  Settings,
  ShieldCheck,
  Sparkles,
  Target,
  TrendingUp,
  Wallet,
} from "lucide-react";
import type { TranslationKey } from "@/i18n";

export interface NavItem {
  to: string;
  labelKey: TranslationKey;
  testId: string;
  icon: LucideIcon;
}

export const NAV_ITEMS: NavItem[] = [
  { to: "/", labelKey: "nav.home", testId: "nav-home", icon: Home },
  { to: "/analyst", labelKey: "nav.analyst", testId: "nav-analyst", icon: Sparkles },
  { to: "/chat", labelKey: "nav.chat", testId: "nav-chat", icon: MessageSquare },
  { to: "/markets", labelKey: "nav.markets", testId: "nav-markets", icon: TrendingUp },
  { to: "/watchlist", labelKey: "nav.watchlist", testId: "nav-watchlist", icon: Eye },
  { to: "/analysis", labelKey: "nav.analysis", testId: "nav-analysis", icon: Activity },
  { to: "/trades", labelKey: "nav.trades", testId: "nav-trades", icon: Wallet },
  { to: "/recommendations", labelKey: "nav.recommendations", testId: "nav-recommendations", icon: Target },
  { to: "/alerts", labelKey: "nav.alerts", testId: "nav-alerts", icon: Bell },
  { to: "/journal", labelKey: "nav.journal", testId: "nav-journal", icon: BookOpen },
  { to: "/research", labelKey: "nav.research", testId: "nav-research", icon: FlaskConical },
  { to: "/memory", labelKey: "nav.memory", testId: "nav-memory", icon: Brain },
  { to: "/performance", labelKey: "nav.performance", testId: "nav-performance", icon: BarChart3 },
  { to: "/replay", labelKey: "nav.replay", testId: "nav-replay", icon: RotateCcw },
  { to: "/admin", labelKey: "nav.admin", testId: "nav-admin", icon: ShieldCheck },
  { to: "/settings", labelKey: "nav.settings", testId: "nav-settings", icon: Settings },
];
