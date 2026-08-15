/**
 * Light/dark theme, persisted. Mirrors `authStore`'s shape: module state +
 * a custom event, so `useTheme` can subscribe the same way `useAuth` does.
 *
 * The value written here is read synchronously by the inline script in
 * `index.html` before first paint — the two must agree on both the storage
 * key and on dark being the fallback (a trading terminal read at night).
 */

export type Theme = "dark" | "light";

const STORAGE_KEY = "leovee-theme";
export const THEME_CHANGED_EVENT = "leovee-theme-changed";

export function getTheme(): Theme {
  if (typeof window === "undefined") return "dark";
  return window.localStorage.getItem(STORAGE_KEY) === "light" ? "light" : "dark";
}

export function setTheme(theme: Theme): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(STORAGE_KEY, theme);
  document.documentElement.classList.toggle("dark", theme === "dark");
  window.dispatchEvent(new Event(THEME_CHANGED_EVENT));
}

export function toggleTheme(): void {
  setTheme(getTheme() === "dark" ? "light" : "dark");
}
