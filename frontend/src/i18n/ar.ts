/**
 * Arabic — the source dictionary.
 *
 * This is the default locale, so keys are added here first and `en.ts` follows.
 * The parity test fails if the two drift apart in either direction.
 *
 * Scope note: this scaffold covers the surfaces that exist today. The bulk of
 * AiChart's ~727 keys arrive in M10 along with the component rollout, filtered
 * of the execution, broker, notification and backtest vocabulary that is out of
 * scope (ADR 0003, ADR 0005).
 */
export const ar = {
  "app.name": "ليوفي",

  "nav.home": "الرئيسية",
  "nav.analyst": "المحلّل الذكي",
  "nav.chat": "المحادثة",
  "nav.markets": "الأسواق",
  "nav.watchlist": "قائمة المتابعة",
  "nav.analysis": "التحليل",
  "nav.recommendations": "التوصيات",
  "nav.journal": "اليوميات",
  "nav.memory": "الذاكرة",
  "nav.performance": "الأداء",
  "nav.settings": "الإعدادات",

  "auth.login": "تسجيل الدخول",
  "auth.logout": "تسجيل الخروج",
  "auth.signup": "إنشاء حساب",
  "auth.email": "البريد الإلكتروني",
  "auth.password": "كلمة المرور",

  "direction.buy": "شراء",
  "direction.sell": "بيع",

  "tradability.now": "قابلة للتنفيذ الآن",
  "tradability.soon": "قريباً",
  "tradability.watchOnly": "للمراقبة فقط",

  "plan.immediate": "خطة فورية",
  "plan.anticipatory": "خطة استباقية",
  "plan.conditional": "خطة شرطية",

  "evidence.noStatisticalSupport": "تحليل مباشر بلا دعم إحصائي",

  // Deliberately not "no trade": this is an operational blocker, not a verdict
  // the analyst reached. See ADR 0002.
  "analysis.blocked": "تعذّر إكمال التحليل",
  "analysis.blockedReason": "السبب: {reason}",
  "analysis.running": "جارٍ التحليل…",

  "common.retry": "إعادة المحاولة",
  "common.cancel": "إلغاء",
  "common.save": "حفظ",
  "common.loading": "جارٍ التحميل…",
} as const;
