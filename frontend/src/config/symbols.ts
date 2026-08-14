/**
 * The tradable universe, mirroring the backend allowlist.
 *
 * Leovee analyses gold and nothing else (ADR 0007). The backend enforces this —
 * `app/core/symbols.py` rejects anything else at the data layer — so this exists
 * to keep the UI from *offering* instruments the API will refuse, not as a
 * second line of defence.
 *
 * The shape stays a list so a symbol picker remains meaningful if the universe
 * ever grows; today it has one entry and most surfaces simply read
 * DEFAULT_SYMBOL.
 */
export const TRADABLE_SYMBOLS = ["XAUUSD"] as const;

export type TradableSymbol = (typeof TRADABLE_SYMBOLS)[number];

export const DEFAULT_SYMBOL: TradableSymbol = "XAUUSD";

export function isTradableSymbol(value: string): value is TradableSymbol {
  return (TRADABLE_SYMBOLS as readonly string[]).includes(value.toUpperCase());
}
