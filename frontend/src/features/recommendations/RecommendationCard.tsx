import type { RecommendationCardData } from "./types";

type Props = {
  card: RecommendationCardData;
};

export function RecommendationCard({ card }: Props) {
  return (
    <article className="rounded-lg border border-slate-700 bg-slate-900 p-4 shadow">
      <header className="mb-2 flex items-center justify-between gap-2">
        <h3 className="text-lg font-semibold text-slate-100">{card.headline}</h3>
        <span className="text-sm text-slate-400">{card.status}</span>
      </header>
      {card.thesis ? <p className="mb-3 text-sm text-slate-300">{card.thesis}</p> : null}
      <div className="flex flex-wrap gap-2">
        {card.badges.map((badge) => (
          <span
            key={badge}
            className="rounded bg-slate-800 px-2 py-0.5 text-xs text-slate-200"
          >
            {badge}
          </span>
        ))}
      </div>
    </article>
  );
}
