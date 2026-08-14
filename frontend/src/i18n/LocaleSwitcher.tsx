/**
 * The language control: a select over `LOCALES`, never a two-way toggle.
 *
 * A toggle hardwires "there are exactly two languages" into the interface, and
 * it is precisely the component nobody revisits when a third arrives — the
 * locale union grows, the compiler is satisfied, and the UI silently keeps
 * offering a binary choice. A select renders whatever `LOCALES` holds.
 *
 * Option labels are autonyms (`LOCALE_NATIVE_NAMES`): a reader stranded in the
 * wrong language must be able to find their own.
 */

import { LOCALES, LOCALE_NATIVE_NAMES, isLocale } from "./index";
import { useLocale } from "./context";

export function LocaleSwitcher() {
  const { locale, setLocale, t } = useLocale();
  return (
    <label className="flex items-center gap-2 text-sm text-muted-foreground">
      <span>{t("settings.language")}</span>
      <select
        data-testid="locale-switcher"
        value={locale}
        onChange={(event) => {
          if (isLocale(event.target.value)) setLocale(event.target.value);
        }}
        className="rounded border border-border bg-card px-2 py-1 text-foreground"
      >
        {LOCALES.map((code) => (
          <option key={code} value={code}>
            {LOCALE_NATIVE_NAMES[code]}
          </option>
        ))}
      </select>
    </label>
  );
}
