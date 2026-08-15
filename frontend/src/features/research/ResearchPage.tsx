import { useQuery } from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";
import { listNews } from "@/api/news";
import { ProviderNotConfiguredBanner } from "@/components/ProviderNotConfiguredBanner";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { useLocale } from "@/i18n/context";

export function ResearchPage() {
  const { t } = useLocale();
  const newsQuery = useQuery({
    queryKey: ["news"],
    queryFn: () => listNews("USD"),
  });

  const notConfigured =
    newsQuery.isSuccess && newsQuery.data.provider_configured === false;

  return (
    <div className="flex flex-1 flex-col gap-6 p-4 sm:p-6 lg:p-8">
      <PageHeader
        testId="research-title"
        title={t("research.title")}
        description={t("research.intro")}
      />

      {newsQuery.isLoading && (
        <div className="flex flex-col gap-3" data-testid="research-loading">
          {Array.from({ length: 3 }).map((_, index) => (
            <Card key={index} className="flex flex-col gap-2 p-3">
              <Skeleton className="h-4 w-2/3" />
              <Skeleton className="h-3 w-1/3" />
            </Card>
          ))}
        </div>
      )}
      {newsQuery.isError && (
        <p className="text-sm text-destructive">{(newsQuery.error as Error).message}</p>
      )}
      {notConfigured && (
        <ProviderNotConfiguredBanner
          title={t("research.providerNotConfigured")}
          credentials={["FINNHUB_API_KEY"]}
          testId="news-provider-not-configured"
        />
      )}
      {!notConfigured && (
        <ul className="flex flex-col gap-3">
          {(newsQuery.data?.items ?? []).map((item) => (
            <li key={item.id}>
              <Card className="p-3 sm:p-4" data-testid={`news-${item.id}`}>
                <p className="text-sm font-medium text-foreground">{item.headline}</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {item.source ?? t("research.sourceUnknown")} · {item.published_at}
                </p>
                {item.url ? (
                  <a
                    href={item.url}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-2 inline-flex items-center gap-1 text-xs text-primary hover:underline"
                  >
                    {t("research.openSource")}
                    <ExternalLink className="size-3" aria-hidden="true" />
                  </a>
                ) : null}
              </Card>
            </li>
          ))}
        </ul>
      )}
      {!newsQuery.isLoading &&
        newsQuery.isSuccess &&
        newsQuery.data.provider_configured &&
        newsQuery.data.items.length === 0 && (
          <p className="text-sm text-muted-foreground">{t("research.empty")}</p>
        )}
    </div>
  );
}
