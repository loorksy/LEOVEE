import { Badge } from "@/components/ui/Badge";
import { Card, CardContent, CardHeader } from "@/components/ui/Card";
import { useLocale } from "@/i18n/context";
import type { TranslationKey } from "@/i18n";
import type { RecommendationCardData, Tradability } from "./types";

type Props = {
  card: RecommendationCardData;
};

type RenderableTradability = Exclude<Tradability, "rejected">;

/** now -> buy tones, soon -> warning, watch_only -> muted (DESIGN.md §2). */
function tradabilityBadgeVariant(tradability: RenderableTradability): "buy" | "warning" | "neutral" {
  if (tradability === "now") return "buy";
  if (tradability === "soon") return "warning";
  return "neutral";
}

const TRADABILITY_LABEL_KEY: Record<RenderableTradability, TranslationKey> = {
  now: "tradability.now",
  soon: "tradability.soon",
  watch_only: "tradability.watchOnly",
};

/** Trade direction only, never decorative — buy/sell tokens exclusively. */
function directionBadgeVariant(direction: string): "buy" | "sell" | "neutral" {
  if (direction === "BUY") return "buy";
  if (direction === "SELL") return "sell";
  return "neutral";
}

/** Lifecycle status, not direction: pending states read as warning, tracked
 * states as info, an invalidated thesis as destructive, everything else
 * (e.g. expired) stays neutral. */
function statusBadgeVariant(status: string): "warning" | "info" | "destructive" | "neutral" {
  switch (status) {
    case "DETECTED":
    case "ANALYZING":
    case "FORMING":
    case "WAITING_CONFIRMATION":
      return "warning";
    case "READY":
    case "ACTIVE":
    case "STRENGTHENING":
    case "WEAKENING":
    case "TARGET_REACHED":
      return "info";
    case "INVALIDATED":
      return "destructive";
    default:
      return "neutral";
  }
}

export function RecommendationCard({ card }: Props) {
  const { t } = useLocale();
  // "rejected" is filtered out one level up (never a card at all); anything
  // else renderable-or-absent is handled here.
  const tradability =
    card.tradability && card.tradability !== "rejected" ? card.tradability : null;

  return (
    <Card data-testid={`recommendation-card-${card.id}`} className="flex h-full flex-col">
      <CardHeader className="flex-row items-center justify-between gap-2">
        <div className="min-w-0">
          <h3 className="truncate text-sm font-semibold text-foreground">{card.headline}</h3>
          {card.symbol && (
            <p className="mt-0.5 truncate font-mono text-xs text-muted-foreground">
              {card.symbol}
            </p>
          )}
        </div>
        <Badge variant={directionBadgeVariant(card.direction)} className="shrink-0 font-mono">
          {card.direction}
        </Badge>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-3">
        {card.thesis ? <p className="text-sm text-muted-foreground">{card.thesis}</p> : null}
        {tradability && (
          <div className="flex items-center gap-2">
            <Badge
              variant={tradabilityBadgeVariant(tradability)}
              data-testid={`recommendation-card-${card.id}-tradability`}
            >
              {t(TRADABILITY_LABEL_KEY[tradability])}
            </Badge>
            {card.tradability_reason && (
              <span className="truncate text-xs text-muted-foreground">
                {card.tradability_reason}
              </span>
            )}
          </div>
        )}
        <div className="mt-auto flex flex-wrap items-center gap-2">
          <Badge variant={statusBadgeVariant(card.status)}>{card.status}</Badge>
          {card.badges
            .filter((badge) => badge !== card.status)
            .map((badge) => (
              <Badge key={badge} variant="neutral" className="font-mono">
                {badge}
              </Badge>
            ))}
        </div>
      </CardContent>
    </Card>
  );
}
