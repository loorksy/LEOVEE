import { useQuery } from "@tanstack/react-query";
import { listNews } from "@/api/news";
import { ProviderNotConfiguredBanner } from "@/components/ProviderNotConfiguredBanner";

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
        <ProviderNotConfiguredBanner
          title="News provider not configured"
          credentials={["FINNHUB_API_KEY"]}
          testId="news-provider-not-configured"
        />
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
