/**
 * The design rules that survive by test, not by memory (M10, DESIGN.md).
 *
 * Each rule here was bought with a real defect in the reference product, and
 * each is checkable mechanically. What cannot be checked mechanically — "buy
 * colours mean trade direction only" — is enforced at the token layer instead:
 * components have no hex to misuse, only semantic names.
 */

import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, resolve } from "node:path";

import { describe, expect, it } from "vitest";

const SRC = resolve(process.cwd(), "src");

function sourceFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      out.push(...sourceFiles(full));
    } else if (/\.(ts|tsx|css)$/.test(entry)) {
      out.push(full);
    }
  }
  return out;
}

const FILES = sourceFiles(SRC).map((path) => ({
  path: path.replace(`${SRC}/`, "src/"),
  text: readFileSync(path, "utf8"),
}));

it("is actually reading the source tree", () => {
  // A guard that scans an empty list reports success by not running — the one
  // thing a guard must never do (learned on rendererBoundary.test.ts).
  expect(FILES.length).toBeGreaterThan(30);
});

describe("logical properties only", () => {
  it("no component uses a physical direction class", () => {
    // Arabic is the default locale and the document is RTL. `ml-4` puts the
    // margin on the wrong side for the majority of users; `ms-4` follows the
    // text direction. One physical class is invisible in an LTR review and
    // wrong in production — which is why this is a test and not a convention.
    // `(?:[^"'`]*\s)?` — the offending class either opens the attribute or
    // follows whitespace. The first version required the whitespace, so an
    // offender in first position (`className="ml-2 …"`) passed the guard;
    // found when TradesPage shipped exactly that.
    const physical =
      /className={?["'`](?:[^"'`]*\s)?(?:ml-|mr-|pl-|pr-|left-\d|right-\d|text-left|text-right|rounded-l-|rounded-r-|border-l(?:-|\s|")|border-r(?:-|\s|"))/;
    const offenders = FILES.filter(
      (file) =>
        file.path.endsWith(".tsx") &&
        !file.path.endsWith(".test.tsx") &&
        physical.test(file.text),
    ).map((file) => file.path);
    expect(offenders).toEqual([]);
  });
});

describe("colour goes through tokens", () => {
  it("no component carries a raw hex colour", () => {
    // A hex value in a component is a colour decision made outside the palette.
    // It renders identically today and silently diverges the first time the
    // tokens are retuned — including the buy/sell pair, where divergence means
    // two greens on screen claiming to be the same signal.
    const allowed = new Set([
      "src/styles/tokens.css",
      // The chart adapter passes colours to a third-party API that takes hex.
      "src/chart/TradingViewAdapter.ts",
      "src/engines/",
    ]);
    const offenders = FILES.filter(
      (file) =>
        (file.path.endsWith(".tsx") || file.path === "src/app/index.css") &&
        !file.path.endsWith(".test.tsx") &&
        ![...allowed].some((prefix) => file.path.startsWith(prefix)) &&
        /#[0-9a-fA-F]{6}\b/.test(file.text),
    ).map((file) => file.path);
    expect(offenders).toEqual([]);
  });
});

describe("AA contrast on the trading palette", () => {
  // The M10 exit criterion, mechanical: buy/sell/warning must stay legible as
  // text on both surfaces in both modes. This ran red on its first execution —
  // light warning was 3.19:1 and dark sell 4.19:1 on the card — so the tokens
  // were retuned, not the threshold.
  const tokensCss = FILES.find((file) => file.path === "src/styles/tokens.css");

  function parseBlock(source: string, selector: string): Record<string, string> {
    const match = source.match(new RegExp(`${selector}\\s*\\{([^}]*)\\}`));
    if (!match) return {};
    const out: Record<string, string> = {};
    for (const [, name, value] of match[1].matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{6})/g)) {
      out[name] = value;
    }
    return out;
  }

  function luminance(hex: string): number {
    const channel = (i: number) => {
      const v = parseInt(hex.slice(i, i + 2), 16) / 255;
      return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
    };
    return 0.2126 * channel(1) + 0.7152 * channel(3) + 0.0722 * channel(5);
  }

  function contrast(a: string, b: string): number {
    const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
    return (hi + 0.05) / (lo + 0.05);
  }

  //: Tokens that color text: AA normal text, 4.5:1.
  const TEXT_TOKENS = ["foreground", "muted-foreground", "buy", "sell", "success", "warning", "destructive"];
  //: Tokens that color UI components and large accents: AA non-text, 3:1.
  const COMPONENT_TOKENS = ["info", "accent"];
  const SURFACES = ["background", "card"];

  function paletteFor(mode: string): Record<string, string> {
    const light = parseBlock(tokensCss?.text ?? "", ":root");
    if (mode === "light") return light;
    // The cascade: a token the .dark block does not redefine inherits :root.
    return { ...light, ...parseBlock(tokensCss?.text ?? "", "\\.dark") };
  }

  it("parses both palettes from the tokens file", () => {
    expect(tokensCss).toBeDefined();
    for (const palette of [paletteFor("light"), paletteFor("dark")]) {
      for (const token of [...TEXT_TOKENS, ...COMPONENT_TOKENS, ...SURFACES]) {
        expect(palette[token], token).toMatch(/^#[0-9a-fA-F]{6}$/);
      }
    }
  });

  it.each(["light", "dark"])("%s mode meets AA on every surface", (mode) => {
    const palette = paletteFor(mode);
    for (const surface of SURFACES) {
      for (const token of TEXT_TOKENS) {
        const ratio = contrast(palette[token], palette[surface]);
        expect(ratio, `${mode} ${token} on ${surface}: ${ratio.toFixed(2)}`).toBeGreaterThanOrEqual(4.5);
      }
      for (const token of COMPONENT_TOKENS) {
        const ratio = contrast(palette[token], palette[surface]);
        expect(ratio, `${mode} ${token} on ${surface}: ${ratio.toFixed(2)}`).toBeGreaterThanOrEqual(3.0);
      }
    }
  });
});

describe("no static quick actions in chat", () => {
  it("the chat surface renders no hardcoded suggestion buttons", () => {
    // A non-negotiable inherited from the reference's system rules: canned
    // "quick action" chips in a chat teach the user the agent only understands
    // those, and they rot the moment the pipeline changes underneath them.
    const chat = FILES.filter(
      (file) => file.path.startsWith("src/features/chat/") && file.path.endsWith(".tsx"),
    );
    for (const file of chat) {
      expect(file.text).not.toMatch(/quickAction|QUICK_ACTIONS|suggestedPrompts/i);
    }
  });
});
