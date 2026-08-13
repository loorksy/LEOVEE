import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  applyDocumentLocale,
  LOCALE_DIRECTION,
  resolveInitialLocale,
  storeLocale,
  translate,
  type Locale,
} from "./index";
import { LocaleContext, type LocaleContextValue } from "./context";

export function LocaleProvider({
  children,
  initialLocale,
}: {
  children: ReactNode;
  /** Tests pin a locale; the app resolves one from storage or the browser. */
  initialLocale?: Locale;
}) {
  const [locale, setLocaleState] = useState<Locale>(initialLocale ?? resolveInitialLocale);

  useEffect(() => {
    applyDocumentLocale(locale);
  }, [locale]);

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    storeLocale(next);
  }, []);

  const value = useMemo<LocaleContextValue>(
    () => ({
      locale,
      dir: LOCALE_DIRECTION[locale],
      setLocale,
      t: (key, values) => translate(locale, key, values),
    }),
    [locale, setLocale],
  );

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}
