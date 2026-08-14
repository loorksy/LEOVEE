/**
 * Loading the vendored charting library at runtime.
 *
 * A script tag rather than an import, because the library ships as a global
 * bundle that lazily fetches ~1,900 chunks from a fixed base path. Importing it
 * would pull all of that into the application bundle, and the base path would
 * no longer match where the chunks actually live.
 *
 * Served from this origin (`/charting_library/`), never from a CDN: the licence
 * forbids public redistribution, and a CDN URL is public redistribution.
 */

const SCRIPT_ID = "tradingview-charting-library";
const SCRIPT_SRC = "/charting_library/charting_library.standalone.js";

type WidgetConstructor = new (options: Record<string, unknown>) => TradingViewWidget;

export type TradingViewWidget = {
  onChartReady: (callback: () => void) => void;
  activeChart: () => {
    createMultipointShape: (
      points: Array<{ time: number; price: number }>,
      options: Record<string, unknown>,
    ) => string | null;
    removeEntity: (id: string) => void;
    setSymbol: (symbol: string, callback?: () => void) => void;
  };
  remove: () => void;
};

declare global {
  interface Window {
    TradingView?: { widget?: WidgetConstructor };
  }
}

let pending: Promise<WidgetConstructor> | null = null;

/**
 * Resolve the widget constructor, loading the script once.
 *
 * Memoised on the promise, not on a boolean: two components mounting in the
 * same tick would both see "not loaded yet" and inject the script twice, and
 * the second load would reset the first widget's global state.
 */
export function loadChartingLibrary(): Promise<WidgetConstructor> {
  if (window.TradingView?.widget) {
    return Promise.resolve(window.TradingView.widget);
  }
  if (pending) {
    return pending;
  }

  pending = new Promise<WidgetConstructor>((resolve, reject) => {
    const existing = document.getElementById(SCRIPT_ID) as HTMLScriptElement | null;
    const script = existing ?? document.createElement("script");
    const onLoad = () => {
      const widget = window.TradingView?.widget;
      if (widget) {
        resolve(widget);
      } else {
        // The script loaded and the global is missing: the vendored asset is
        // present but wrong. Saying so beats a chart that silently never appears.
        reject(new Error("charting library loaded but window.TradingView.widget is absent"));
      }
    };
    script.addEventListener("load", onLoad, { once: true });
    script.addEventListener(
      "error",
      () => reject(new Error(`failed to load ${SCRIPT_SRC}`)),
      { once: true },
    );
    if (!existing) {
      script.id = SCRIPT_ID;
      script.src = SCRIPT_SRC;
      script.async = true;
      document.head.appendChild(script);
    }
  }).catch((error: unknown) => {
    // Clear the memo so a transient failure can be retried; keeping a rejected
    // promise cached would make the chart permanently broken for the session.
    pending = null;
    throw error;
  });

  return pending;
}

/** Test seam: forget any in-flight or completed load. */
export function resetChartingLibraryLoader(): void {
  pending = null;
}
