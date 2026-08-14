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

/**
 * Adding a locale is a four-line change, and the compiler walks you through it:
 * extend the `Locale` union above, then TypeScript demands an entry in each of
 * the three records below and a dictionary in `index.ts`. The parity and
 * placeholder tests iterate `LOCALES`, so a third language is covered by the
 * same guarantees as the first two the moment it is registered — nothing else
 * in the codebase knows how many locales exist.
 */
export const LOCALES: readonly Locale[] = ["ar", "en"] as const;

export const LOCALE_DIRECTION: Record<Locale, "rtl" | "ltr"> = {
  ar: "rtl",
  en: "ltr",
};

/**
 * Each language's name in itself — an autonym, deliberately not a translation
 * key. "العربية" is "العربية" in every locale: a reader lost in the wrong
 * language finds their own in the switcher precisely because it is *not*
 * rendered in the language they cannot read.
 */
export const LOCALE_NATIVE_NAMES: Record<Locale, string> = {
  ar: "العربية",
  en: "English",
};

/** The key set is defined by the Arabic dictionary; English must match it. */
export type TranslationKey = keyof typeof import("./ar").ar;

export type Dictionary = Record<TranslationKey, string>;
