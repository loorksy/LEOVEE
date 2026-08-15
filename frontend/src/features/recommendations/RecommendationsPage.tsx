import { useQuery } from "@tanstack/react-query";
import { listRecommendationCards } from "@/api/recommendations";
import { RecommendationCard } from "@/features/recommendations/RecommendationCard";
import { useLocale } from "@/i18n/context";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";

export function RecommendationsPage() {
  const { t } = useLocale();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["recommendations", "cards"],
    queryFn: listRecommendationCards,
  });
  // A rejected tradability assessment is never rendered as a card at all
  // (DESIGN.md §2) — filtered here, once, rather than by every consumer of
  // this list.
  const visibleCards = data?.items.filter((card) => card.tradability !== "rejected") ?? [];

  return (
    <div className="flex flex-1 flex-col gap-6 p-4 sm:p-6 lg:p-8">
      <PageHeader
        testId="recommendations-title"
        title={t("recommendations.title")}
        description={t("recommendations.intro")}
      />
      {isLoading && (
        <div
          className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3"
          data-testid="recommendations-loading"
        >
          {Array.from({ length: 3 }).map((_, index) => (
            <Card key={index} className="flex flex-col gap-3 p-3">
              <Skeleton className="h-4 w-2/3" />
              <Skeleton className="h-3 w-full" />
              <Skeleton className="h-3 w-4/5" />
            </Card>
          ))}
        </div>
      )}
      {isError && (
        <p className="text-sm text-destructive" data-testid="recommendations-error">
          {t("common.error.load")}
        </p>
      )}
      {data && visibleCards.length === 0 && (
        <p className="text-sm text-muted-foreground" data-testid="recommendations-empty">
          {t("recommendations.empty")}
        </p>
      )}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {visibleCards.map((card) => (
          <RecommendationCard key={card.id} card={card} />
        ))}
      </div>
    </div>
  );
}
