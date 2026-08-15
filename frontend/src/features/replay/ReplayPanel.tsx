import { useLocale } from "@/i18n/context";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";

export type ReplayPreview = {
  symbol: string;
  timeframe: string;
  as_of: string;
  candle_count: number;
  excluded_future_candles: number;
  candles: { ts: string; close: number }[];
  recall: {
    counts: { memories: number; lessons: number; episodes: number };
  };
};

type Props = {
  preview: ReplayPreview | null;
  loading?: boolean;
};

export function ReplayPanel({ preview, loading }: Props) {
  const { t } = useLocale();
  if (loading) {
    return (
      <Card className="p-3" data-testid="replay-panel-loading">
        <div className="flex flex-col gap-2">
          <Skeleton className="h-4 w-40" />
          <Skeleton className="h-3 w-56" />
          <Skeleton className="mt-2 h-16 w-full" />
        </div>
      </Card>
    );
  }
  if (!preview) {
    return <p className="text-sm text-muted-foreground">{t("replay.empty")}</p>;
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("replay.historical")}</CardTitle>
        <p className="font-mono text-xs text-muted-foreground">
          {preview.symbol} {preview.timeframe} ·{" "}
          {t("replay.asof.value", { timestamp: preview.as_of })}
        </p>
      </CardHeader>
      <CardContent>
        <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
          <div>
            <dt className="text-muted-foreground">{t("replay.candles.visible")}</dt>
            <dd className="font-mono text-foreground">{preview.candle_count}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">{t("replay.candles.hidden")}</dt>
            <dd className="font-mono text-foreground">{preview.excluded_future_candles}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">{t("replay.memories")}</dt>
            <dd className="font-mono text-foreground">{preview.recall.counts.memories}</dd>
          </div>
        </dl>
      </CardContent>
    </Card>
  );
}
