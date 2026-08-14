/**
 * Chart colours resolved from the design tokens, not hard-coded in components.
 *
 * Recharts and lightweight-charts are third-party APIs that take hex strings,
 * so the colour has to become a literal *somewhere* — but the decision stays in
 * `tokens.css`. This reads the CSS custom properties at call time, so a chart's
 * up-candle is the same `--buy` green as every other buy signal on screen,
 * never a second green claiming to be the same thing.
 *
 * Fallbacks cover the server / jsdom case where no computed style exists; they
 * mirror the dark-mode token values, which is the app's default surface.
 */

const FALLBACK: Record<string, string> = {
  buy: "#22c55e",
  sell: "#f87171",
  accent: "#6366f1",
  info: "#38bdf8",
  warning: "#f59e0b",
  success: "#22c55e",
  card: "#1a2332",
  "muted-foreground": "#a3a3a3",
};

function token(name: string): string {
  if (typeof window !== "undefined" && typeof getComputedStyle === "function") {
    const value = getComputedStyle(document.documentElement).getPropertyValue(`--${name}`).trim();
    if (value) return value;
  }
  return FALLBACK[name] ?? "#a3a3a3";
}

export interface ChartPalette {
  buy: string;
  sell: string;
  grid: string;
  axis: string;
  /** Ordered series colours for multi-line / multi-bar charts. */
  series: string[];
}

export function chartPalette(): ChartPalette {
  return {
    buy: token("buy"),
    sell: token("sell"),
    grid: token("card"),
    axis: token("muted-foreground"),
    series: [token("accent"), token("buy"), token("info"), token("warning"), token("sell")],
  };
}
