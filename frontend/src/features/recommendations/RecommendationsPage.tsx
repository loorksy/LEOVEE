import { useQuery } from "@tanstack/react-query";
import { listRecommendationCards } from "@/api/recommendations";
import { RecommendationCard } from "@/features/recommendations/RecommendationCard";

export function RecommendationsPage() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["recommendations", "cards"],
    queryFn: listRecommendationCards,
  });

  return (
    <div className="flex flex-1 flex-col gap-6 p-8">
      <header>
        <h1 className="text-2xl font-semibold text-slate-100">Recommendations</h1>
        <p className="mt-1 text-slate-400">Active and historical trade recommendations.</p>
      </header>
      {isLoading && <p className="text-slate-400">Loading recommendations…</p>}
      {isError && <p className="text-amber-400">Could not load recommendations.</p>}
      {data && data.items.length === 0 && (
        <p className="text-slate-400">No recommendations yet — run an analysis to generate one.</p>
      )}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {data?.items.map((card) => <RecommendationCard key={card.id} card={card} />)}
      </div>
    </div>
  );
}
