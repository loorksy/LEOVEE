import type { ReactNode } from "react";
import { useLocale } from "@/i18n/context";
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardInset } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import type { PerformanceSummary } from "./types";

type Props = {
  summary: PerformanceSummary | null;
  loading?: boolean;
};

export function PerformanceDashboard({ summary, loading }: Props) {
  const { t } = useLocale();

  if (loading) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-4 w-32" />
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4" data-testid="performance-loading">
            {Array.from({ length: 4 }).map((_, index) => (
              <Skeleton key={index} className="h-16 w-full" />
            ))}
          </div>
          <Skeleton className="h-24 w-full" />
        </CardContent>
      </Card>
    );
  }

  if (!summary) {
    return <p className="text-sm text-muted-foreground">{t("performance.empty")}</p>;
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("performance.title")}</CardTitle>
        <CardDescription>
          {t("performance.asOf")}: <span className="font-mono">{summary.as_of}</span>
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatTile label={t("performance.tradeIdeas")} value={summary.trade_ideas} />
          <StatTile
            label={t("performance.calibrationRate")}
            value={summary.calibration.rate.toFixed(3)}
          />
          <StatTile
            label={t("performance.predictedBins")}
            value={summary.calibration.predicted_total}
          />
          <StatTile
            label={t("performance.realizedSuccess")}
            value={summary.calibration.realized_success_total}
          />
        </dl>
        <div className="flex h-20 items-end gap-1 sm:h-24">
          {summary.calibration.bins.map((bin) => (
            <div
              key={`${bin.bin_lower}-${bin.bin_upper}`}
              className="flex-1 rounded-t bg-chart-1"
              style={{
                height: `${Math.max(8, (bin.predicted_count / Math.max(1, summary.calibration.predicted_total)) * 100)}%`,
              }}
              title={`${bin.bin_lower}-${bin.bin_upper}`}
            />
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function StatTile({ label, value }: { label: string; value: ReactNode }) {
  return (
    <CardInset>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="mt-1 truncate font-mono text-base font-semibold text-foreground sm:text-lg">
        {value}
      </dd>
    </CardInset>
  );
}
