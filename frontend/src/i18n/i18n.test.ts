import { describe, expect, it } from "vitest";

import { ar } from "./ar";
import {
  DEFAULT_LOCALE,
  LOCALE_DIRECTION,
  LOCALE_NATIVE_NAMES,
  LOCALES,
  applyDocumentLocale,
  dictionaryFor,
  interpolate,
  isLocale,
  translate,
} from "./index";

describe("locale registry", () => {
  it("every registered locale carries a direction and a native name", () => {
    // These records are what a new locale must fill in, and the compiler
    // enforces them — this test exists so a *runtime*-constructed locale list
    // (from config, some day) cannot outgrow the records silently.
    for (const locale of LOCALES) {
      expect(LOCALE_DIRECTION[locale]).toMatch(/^(rtl|ltr)$/);
      expect(LOCALE_NATIVE_NAMES[locale].length).toBeGreaterThan(0);
    }
  });

  it("native names are autonyms, not translations", () => {
    // "العربية" must read as العربية in every locale: a reader stranded in the
    // wrong language finds their own in the switcher precisely because it is
    // not rendered in the language they cannot read.
    expect(LOCALE_NATIVE_NAMES.ar).toBe("العربية");
    expect(LOCALE_NATIVE_NAMES.en).toBe("English");
  });
});

describe("dictionary parity", () => {
  // Iterated over LOCALES rather than written as ar-versus-en: the product
  // supports Arabic and English today and possibly more languages later, and a
  // parity test naming the pair would quietly stop covering the third the day
  // it arrives. Every locale is measured against the source dictionary
  // (Arabic).
  const source = ar;

  it("every locale defines exactly the source key set", () => {
    const sourceKeys = Object.keys(source).sort();
    for (const locale of LOCALES) {
      expect(Object.keys(dictionaryFor(locale)).sort(), `locale "${locale}"`).toEqual(sourceKeys);
    }
  });

  it("no locale has an empty value", () => {
    for (const locale of LOCALES) {
      for (const [key, value] of Object.entries(dictionaryFor(locale))) {
        expect(value.trim().length, `"${key}" in "${locale}"`).toBeGreaterThan(0);
      }
    }
  });

  it("placeholders match the source in every locale", () => {
    const placeholders = (template: string) => (template.match(/{[a-zA-Z]+}/g) ?? []).sort();
    for (const locale of LOCALES) {
      const dictionary = dictionaryFor(locale);
      for (const key of Object.keys(source) as (keyof typeof source)[]) {
        expect(
          placeholders(dictionary[key]),
          `placeholders differ for "${key}" in "${locale}"`,
        ).toEqual(placeholders(source[key]));
      }
    }
  });
});

describe("locale resolution", () => {
  it("defaults to Arabic", () => {
    expect(DEFAULT_LOCALE).toBe("ar");
  });

  it("maps Arabic to RTL and English to LTR", () => {
    expect(LOCALE_DIRECTION.ar).toBe("rtl");
    expect(LOCALE_DIRECTION.en).toBe("ltr");
  });

  it("recognises only supported locales", () => {
    expect(isLocale("ar")).toBe(true);
    expect(isLocale("fr")).toBe(false);
    expect(isLocale(undefined)).toBe(false);
  });
});

describe("translate", () => {
  it("returns the string for the active locale", () => {
    expect(translate("ar", "direction.buy")).toBe("شراء");
    expect(translate("en", "direction.buy")).toBe("Buy");
  });

  it("substitutes placeholders", () => {
    expect(translate("en", "analysis.blockedReason", { reason: "ENGINE_UNAVAILABLE" })).toBe(
      "Reason: ENGINE_UNAVAILABLE",
    );
  });

  it("leaves an unknown placeholder visible rather than blanking it", () => {
    // A visible {reason} points at the bug; an empty string hides it.
    expect(interpolate("Reason: {reason}", {})).toBe("Reason: {reason}");
  });

  it("does not phrase a blocked analysis as a trading verdict", () => {
    // ADR 0002: NO_TRADE is an operational failure, not an analytical outcome.
    expect(translate("en", "analysis.blocked").toLowerCase()).not.toContain("no trade");
    expect(translate("ar", "analysis.blocked")).not.toContain("لا صفقة");
  });
});

describe("applyDocumentLocale", () => {
  it("sets lang and dir on the document element", () => {
    applyDocumentLocale("ar");
    expect(document.documentElement.lang).toBe("ar");
    expect(document.documentElement.dir).toBe("rtl");

    applyDocumentLocale("en");
    expect(document.documentElement.dir).toBe("ltr");
  });
});
