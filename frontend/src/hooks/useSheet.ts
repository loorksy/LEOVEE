import { useCallback, useSyncExternalStore } from "react";
import { type SheetId, closeSheet, getActiveSheet, openSheet, subscribeSheet } from "@/api/sheetStore";

/** Whether `id` currently holds the app's single overlay slot, plus a setter
 *  that claims or releases it — opening a different id elsewhere closes this
 *  one automatically (the whole point of the shared slot). */
export function useSheetSlot(id: SheetId): [boolean, (open: boolean) => void] {
  const active = useSyncExternalStore(subscribeSheet, getActiveSheet, () => null);
  const setOpen = useCallback(
    (open: boolean) => (open ? openSheet(id) : closeSheet(id)),
    [id],
  );
  return [active === id, setOpen];
}
