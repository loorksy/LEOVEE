/**
 * The boundary that made swapping the chart library cheap.
 *
 * Replacing KLineChart with TradingView (ADR 0004) touched two files, because
 * every consumer binds to `ChartEngine` and `AnnotationSurface` rather than to a
 * library. That property is worth exactly as much as it is enforced: the first
 * component to import the widget directly, or the first semantic type named
 * after a drawing tool, quietly turns the next swap back into a rewrite.
 */

import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, resolve } from "node:path";

import { describe, expect, it } from "vitest";

// Resolved from the vitest root rather than from `import.meta.url`, which the
// transform rewrites to a bare module path — `scandir '/src'`. That failure
// collected zero tests while the *suite* run still reported "94 passed", which
// is the one thing a guard must never do: pass by not running.
const SRC = resolve(process.cwd(), "src");

function sourceFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      out.push(...sourceFiles(full));
    } else if (/\.(ts|tsx)$/.test(entry)) {
      out.push(full);
    }
  }
  return out;
}

const FILES = sourceFiles(SRC).map((path) => ({
  path: path.replace(`${SRC}/`, "src/"),
  text: readFileSync(path, "utf8"),
}));

describe("renderer boundary", () => {
  it("is actually reading the source tree", () => {
    // The guard above scanned an empty file list once and reported success.
    // This is the assertion that makes that impossible.
    expect(FILES.length).toBeGreaterThan(20);
    expect(FILES.map((file) => file.path)).toContain("src/chart/ChartTypes.ts");
  });

  it("no longer depends on the previous charting library", () => {
    const offenders = FILES.filter(
      (file) => !file.path.endsWith("rendererBoundary.test.ts") && /klinecharts/i.test(file.text),
    ).map((file) => file.path);
    expect(offenders).toEqual([]);
  });

  it("keeps knowledge of the charting library inside the chart adapter", () => {
    // Everything else talks to `ChartEngine`. A page importing the widget
    // directly would work perfectly and quietly cost the abstraction.
    const allowed = [
      "src/chart/TradingViewAdapter.ts",
      "src/chart/tradingview/loadLibrary.ts",
      "src/chart/tradingview/TradingViewChart.tsx",
      "src/chart/tradingview/datafeed.ts",
      "src/chart/index.ts",
      "src/chart/rendererBoundary.test.ts",
    ];
    const offenders = FILES.filter(
      (file) =>
        !allowed.includes(file.path) &&
        !file.path.endsWith(".test.ts") &&
        !file.path.endsWith(".test.tsx") &&
        /charting_library|window\.TradingView/.test(file.text),
    ).map((file) => file.path);
    expect(offenders).toEqual([]);
  });

  it("serves the library from this origin, never a CDN", () => {
    // The licence forbids public redistribution, and a CDN URL is exactly that.
    const loader = FILES.find((file) => file.path === "src/chart/tradingview/loadLibrary.ts");
    expect(loader).toBeDefined();
    expect(loader?.text).toContain('"/charting_library/charting_library.standalone.js"');
    expect(loader?.text).not.toMatch(/https?:\/\/[^"']*charting_library/);
  });
});
