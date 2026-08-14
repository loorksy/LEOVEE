import { createContext, useContext } from "react";
import type { Locale, TranslationKey } from "./index";

export type LocaleContextValue = {
  locale: Locale;
  dir: "rtl" | "ltr";
  setLocale: (locale: Locale) => void;
  t: (key: TranslationKey, values?: Record<string, string | number>) => string;
};

export const LocaleContext = createContext<LocaleContextValue | null>(null);

export function useLocale(): LocaleContextValue {
  const context = useContext(LocaleContext);
  if (!context) {
    // Rendering outside the provider would silently fall back to one locale and
    // leave the document direction wrong, which is hard to spot in review.
    throw new Error("useLocale must be used inside <LocaleProvider>");
  }
  return context;
}
