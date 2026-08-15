/** A convincing plan can still be untradeable (entry is far, session is
 *  closed) — reported as its own axis from the backend, separate from
 *  direction/confidence. `rejected` is never rendered as a card at all. */
export type Tradability = "now" | "soon" | "watch_only" | "rejected";

export type RecommendationCardData = {
  id: string;
  symbol?: string | null;
  direction: string;
  status: string;
  confidence: number;
  headline: string;
  thesis?: string | null;
  badges: string[];
  tradability?: Tradability | null;
  tradability_reason?: string | null;
};
