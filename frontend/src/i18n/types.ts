/**
 * Translation keys are a closed set, declared once.
 *
 * AiChart carries ~727 keys per locale with a parity test, and the discipline
 * that makes that survivable is that `t()` cannot be called with a string the
 * dictionary does not define. A missing key becomes a type error at build time
 * rather than a raw `settings.profile.title` rendered to a user.
 */
export type Locale = "ar" | "en";

/** Arabic is the product's default, not a translation of an English original. */
export const DEFAULT_LOCALE: Locale = "ar";

export const LOCALES: readonly Locale[] = ["ar", "en"] as const;

export const LOCALE_DIRECTION: Record<Locale, "rtl" | "ltr"> = {
  ar: "rtl",
  en: "ltr",
};

/** The key set is defined by the Arabic dictionary; English must match it. */
export type TranslationKey = keyof typeof import("./ar").ar;

export type Dictionary = Record<TranslationKey, string>;
