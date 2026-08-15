import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

// jsdom has no layout engine, so it never implements matchMedia — any
// breakpoint-aware hook (the chat workspace's chart-sheet-vs-pane switch)
// throws without this. `matches: false` is the right default: it puts every
// test in the narrower, mobile-first branch unless a test opts into the
// wider one itself.
if (typeof window !== "undefined" && !window.matchMedia) {
  window.matchMedia = (query: string): MediaQueryList =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }) as MediaQueryList;
}

afterEach(() => {
  cleanup();
});
