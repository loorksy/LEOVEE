import { SUPPORTED_TIMEFRAMES, type SupportedTimeframe } from "./ChartTypes";

export function isSupportedTimeframe(value: string): value is SupportedTimeframe {
  return (SUPPORTED_TIMEFRAMES as readonly string[]).includes(value.toUpperCase());
}

export function resolveTimeframe(
  current: string,
  next: string,
): { timeframe: SupportedTimeframe; changed: boolean } {
  const normalized = next.toUpperCase();
  if (!isSupportedTimeframe(normalized)) {
    return { timeframe: isSupportedTimeframe(current) ? current.toUpperCase() as SupportedTimeframe : "1H", changed: false };
  }
  return {
    timeframe: normalized,
    changed: normalized !== current.toUpperCase(),
  };
}
