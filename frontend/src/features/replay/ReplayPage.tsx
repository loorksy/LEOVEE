import { useMutation } from "@tanstack/react-query";
import { DEFAULT_SYMBOL } from "@/config/symbols";
import { useState } from "react";
import { previewReplay } from "@/api/replay";
import { ReplayPanel, type ReplayPreview } from "@/features/replay/ReplayPanel";
import { useLocale } from "@/i18n/context";
import { PageHeader } from "@/components/ui/PageHeader";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";

export function ReplayPage() {
  const { t } = useLocale();
  const [symbol, setSymbol] = useState<string>(DEFAULT_SYMBOL);
  const [timeframe, setTimeframe] = useState("H1");
  const [asOf, setAsOf] = useState(() => new Date().toISOString().slice(0, 16));
  const [preview, setPreview] = useState<ReplayPreview | null>(null);

  const mutation = useMutation({
    mutationFn: () =>
      previewReplay({
        symbol,
        timeframe,
        as_of: new Date(asOf).toISOString(),
      }),
    onSuccess: (data) => setPreview(data),
  });

  return (
    <div className="flex flex-1 flex-col gap-6 p-4 sm:p-6 lg:p-8">
      <PageHeader testId="replay-title" title={t("replay.title")} description={t("replay.intro")} />
      <form
        className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end"
        onSubmit={(e) => {
          e.preventDefault();
          mutation.mutate();
        }}
      >
        <label className="flex flex-col gap-1 text-xs text-muted-foreground" htmlFor="replay-symbol">
          {t("common.symbol")}
          <Input
            id="replay-symbol"
            className="sm:w-40"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
          />
        </label>
        <label className="flex flex-col gap-1 text-xs text-muted-foreground" htmlFor="replay-timeframe">
          {t("common.timeframe")}
          <select
            id="replay-timeframe"
            data-testid="replay-timeframe-select"
            className="h-11 rounded-md border border-border bg-input px-3 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-not-allowed disabled:opacity-50 sm:h-9 sm:w-28"
            value={timeframe}
            onChange={(e) => setTimeframe(e.target.value)}
          >
            {["M15", "H1", "H4", "D1"].map((tf) => (
              <option key={tf} value={tf}>
                {tf}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs text-muted-foreground" htmlFor="replay-asof">
          {t("replay.asof")}
          <Input
            id="replay-asof"
            type="datetime-local"
            className="sm:w-56"
            value={asOf}
            onChange={(e) => setAsOf(e.target.value)}
          />
        </label>
        <Button type="submit" data-testid="replay-preview-button" disabled={mutation.isPending}>
          {mutation.isPending ? t("common.loading") : t("replay.preview")}
        </Button>
      </form>
      {mutation.isError ? (
        <p className="text-sm text-destructive">{(mutation.error as Error).message}</p>
      ) : null}
      <ReplayPanel preview={preview} loading={mutation.isPending} />
    </div>
  );
}
