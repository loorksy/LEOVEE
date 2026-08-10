export type RecommendationCardData = {
  id: string;
  symbol?: string | null;
  direction: string;
  status: string;
  confidence: number;
  headline: string;
  thesis?: string | null;
  badges: string[];
};
