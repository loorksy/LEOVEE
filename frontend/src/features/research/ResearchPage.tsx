import { useQuery } from "@tanstack/react-query";
import { listNews } from "@/api/news";

export function ResearchPage() {
  const newsQuery = useQuery({
    queryKey: ["news"],
    queryFn: () => listNews("USD"),
  });

  const notConfigured =
    newsQuery.isSuccess && newsQuery.data.provider_configured === false;

  return (
    <div className="flex flex-1 flex-col gap-6 p-8">
      <header>
        <h1 className="text-2xl font-semibold text-slate-100">Research</h1>
        <p className="text-sm text-slate-400">
          Recent headlines from `/api/v1/news` (Finnhub when configured).
        </p>
      </header>
      {newsQuery.isLoading && <p className="text-slate-400">Loading research…</p>}
      {newsQuery.isError && (
        <p className="text-amber-400">{(newsQuery.error as Error).message}</p>
      )}
      {notConfigured && (
        <div
          className="rounded border border-amber-800/60 bg-amber-950/40 px-4 py-3 text-sm text-amber-100"
          data-testid="news-provider-not-configured"
        >
          <p className="font-medium">News provider not configured</p>
          <p className="mt-1 text-amber-200/80">
            Set the <code className="text-amber-100">FINNHUB_API_KEY</code> GitHub Actions secret
            and re-run <strong>Deploy staging</strong>. This page stays empty until that key is
            present on the server.
          </p>
        </div>
      )}
      {!notConfigured && (
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
      )}
      {!newsQuery.isLoading &&
        newsQuery.isSuccess &&
        newsQuery.data.provider_configured &&
        newsQuery.data.items.length === 0 && (
          <p className="text-slate-400">No news rows yet — ingestion runs on the worker cron.</p>
        )}
    </div>
  );
}
