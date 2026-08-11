import { useQuery } from "@tanstack/react-query";
import { listNews } from "@/api/news";

export function ResearchPage() {
  const newsQuery = useQuery({
    queryKey: ["news"],
    queryFn: () => listNews("USD"),
  });

  return (
    <div className="flex flex-1 flex-col gap-6 p-8">
      <header>
        <h1 className="text-2xl font-semibold text-slate-100">Research</h1>
        <p className="text-sm text-slate-400">
          Recent headlines from `/api/v1/news` (Finnhub when `FINNHUB_API_KEY` is set).
        </p>
      </header>
      {newsQuery.isLoading && <p className="text-slate-400">Loading research…</p>}
      {newsQuery.isError && (
        <p className="text-amber-400">{(newsQuery.error as Error).message}</p>
      )}
      <ul className="space-y-3">
        {(newsQuery.data?.items ?? []).map((item) => (
          <li
            key={item.id}
            className="rounded border border-slate-800 bg-leovee-panel px-4 py-3"
            data-testid={`news-${item.id}`}
          >
            <p className="text-sm font-medium text-slate-100">{item.headline}</p>
            <p className="mt-1 text-xs text-slate-500">
              {item.source ?? "unknown"} · {item.published_at}
            </p>
            {item.url ? (
              <a
                href={item.url}
                target="_blank"
                rel="noreferrer"
                className="mt-1 inline-block text-xs text-leovee-accent hover:underline"
              >
                Open source
              </a>
            ) : null}
          </li>
        ))}
      </ul>
      {!newsQuery.isLoading && (newsQuery.data?.items.length ?? 0) === 0 && (
        <p className="text-slate-400">
          No news rows yet. Ingestion requires a Finnhub key (see `docs/BLOCKED_ON_OWNER.md`).
        </p>
      )}
    </div>
  );
}
