/**
 * One overlay at a time, app-wide — mirrors authStore/themeStore's shape:
 * module state + a custom event.
 *
 * The chart sheet is summoned from the chat composer, the nav drawer from the
 * top bar — two owners that cannot see each other's state. Left alone they
 * stack, and the user gets two backdrops and no way to tell which one a tap
 * dismisses. A single slot fixes that by construction: each surface is open
 * only while it *is* the active sheet, so opening one closes whatever was
 * there. Switching reads as a swap, never as a stack.
 */

export type SheetId = "navDrawer" | "chart";

const CHANGED_EVENT = "leovee-sheet-changed";

let activeSheet: SheetId | null = null;

export function getActiveSheet(): SheetId | null {
  return activeSheet;
}

export function openSheet(id: SheetId): void {
  if (activeSheet === id) return;
  activeSheet = id;
  window.dispatchEvent(new Event(CHANGED_EVENT));
}

/** Guarded: a late close from a surface that already lost the slot must not
 *  dismiss whichever one took it over. */
export function closeSheet(id: SheetId): void {
  if (activeSheet !== id) return;
  activeSheet = null;
  window.dispatchEvent(new Event(CHANGED_EVENT));
}

export function subscribeSheet(listener: () => void): () => void {
  window.addEventListener(CHANGED_EVENT, listener);
  return () => window.removeEventListener(CHANGED_EVENT, listener);
}

/** Test-only: this module holds pure in-memory state (no localStorage to
 *  clear), so a leftover open sheet from one test would otherwise leak into
 *  the next one in the same file. */
export function resetSheetForTests(): void {
  activeSheet = null;
}
