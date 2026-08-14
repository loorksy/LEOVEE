/**
 * Framework-free i18n, matching the shape AiChart proved out.
 *
 * No library: the whole surface is a dictionary lookup and a direction flag,
 * and a dependency here would mostly add bundle weight and a migration later.
 *
 * Two properties matter more than features:
 *
 * - **Arabic is the default**, not a translation layered onto English. The
 *   document direction follows the locale, and RTL is the case that gets
 *   designed first rather than patched afterwards.
 * - **Keys are typed.** `t()` will not accept a string the dictionary does not
 *   define, so a missing translation is a build error rather than a raw key
 *   rendered to a user.
 */
import { ar } from "./ar";
import { en } from "./en";
import {
  DEFAULT_LOCALE,
  LOCALE_DIRECTION,
  LOCALES,
  type Dictionary,
  type Locale,
  type TranslationKey,
} from "./types";

export { DEFAULT_LOCALE, LOCALES, LOCALE_DIRECTION };
export { LOCALE_NATIVE_NAMES } from "./types";
export type { Locale, TranslationKey };

const DICTIONARIES: Record<Locale, Dictionary> = { ar, en };

const STORAGE_KEY = "leovee.locale";

export function isLocale(value: unknown): value is Locale {
  return typeof value === "string" && (LOCALES as readonly string[]).includes(value);
}

/** Stored choice, else the browser's preference, else Arabic. */
export function resolveInitialLocale(): Locale {
  if (typeof window === "undefined") return DEFAULT_LOCALE;

  const stored = window.localStorage.getItem(STORAGE_KEY);
  if (isLocale(stored)) return stored;

  for (const candidate of window.navigator?.languages ?? []) {
    const base = candidate.split("-")[0];
    if (isLocale(base)) return base;
  }
  return DEFAULT_LOCALE;
}

export function storeLocale(locale: Locale): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(STORAGE_KEY, locale);
}

/**
 * Set `lang` and `dir` on the document element.
 *
 * Direction lives on the document rather than on a wrapper so that portalled
 * content — dialogs, tooltips, anything rendered outside the React tree — is
 * laid out correctly too. That is the usual source of a stray LTR panel in an
 * otherwise RTL app.
 */
export function applyDocumentLocale(locale: Locale): void {
  if (typeof document === "undefined") return;
  document.documentElement.lang = locale;
  document.documentElement.dir = LOCALE_DIRECTION[locale];
}

/**
 * Substitute `{name}` placeholders.
 *
 * An unknown placeholder is left as written rather than blanked: a visible
 * `{reason}` in the UI points at the bug, while an empty string hides it.
 */
export function interpolate(template: string, values?: Record<string, string | number>): string {
  if (!values) return template;
  return template.replace(/\{(\w+)\}/g, (match, key: string) =>
    key in values ? String(values[key]) : match,
  );
}

export function translate(
  locale: Locale,
  key: TranslationKey,
  values?: Record<string, string | number>,
): string {
  const dictionary = DICTIONARIES[locale] ?? DICTIONARIES[DEFAULT_LOCALE];
  // Falling back to the default locale keeps a half-translated locale usable
  // instead of rendering a raw key; the parity test is what stops that state
  // from being reached in the first place.
  const template = dictionary[key] ?? DICTIONARIES[DEFAULT_LOCALE][key];
  return interpolate(template, values);
}

export function dictionaryFor(locale: Locale): Dictionary {
  return DICTIONARIES[locale];
}
