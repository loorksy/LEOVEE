import { describe, expect, it } from "vitest";
import { ar } from "./ar";
import { en } from "./en";
import {
  DEFAULT_LOCALE,
  LOCALE_DIRECTION,
  LOCALES,
  applyDocumentLocale,
  interpolate,
  isLocale,
  translate,
} from "./index";

describe("dictionary parity", () => {
  it("defines the same keys in every locale", () => {
    const arabic = Object.keys(ar).sort();
    const english = Object.keys(en).sort();
    expect(english).toEqual(arabic);
  });

  it("has no empty translations", () => {
    for (const [locale, dictionary] of [
      ["ar", ar],
      ["en", en],
    ] as const) {
      for (const [key, value] of Object.entries(dictionary)) {
        expect(value.trim(), `${locale}.${key} is empty`).not.toBe("");
      }
    }
  });

  it("keeps placeholders consistent across locales", () => {
    // A key that interpolates {reason} in one locale and not the other renders
    // a partial sentence in production and nowhere else.
    const placeholders = (text: string) => (text.match(/\{(\w+)\}/g) ?? []).sort();
    for (const key of Object.keys(ar) as (keyof typeof ar)[]) {
      expect(placeholders(en[key]), `placeholders differ for "${key}"`).toEqual(
        placeholders(ar[key]),
      );
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

  it("covers every declared locale with a direction", () => {
    for (const locale of LOCALES) {
      expect(LOCALE_DIRECTION[locale]).toBeDefined();
    }
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
