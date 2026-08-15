import { useState } from "react";
import { DEFAULT_SYMBOL } from "@/config/symbols";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createAlert, listAlerts, triggerAlert } from "@/api/alerts";
import { useWorkspaceId } from "@/hooks/useWorkspaceId";
import { useNotificationsStream } from "@/features/alerts/useNotificationsStream";
import type { NotificationData } from "@/features/alerts/types";
import { useLocale } from "@/i18n/context";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card, CardInset } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Skeleton } from "@/components/ui/Skeleton";

export function AlertsPage() {
  const { t } = useLocale();
  const queryClient = useQueryClient();
  const workspaceQuery = useWorkspaceId();

  const [symbol, setSymbol] = useState<string>(DEFAULT_SYMBOL);
  const [op, setOp] = useState<"gte" | "lte" | "eq">("gte");
  const [threshold, setThreshold] = useState("1.10");
  const [triggerPrices, setTriggerPrices] = useState<Record<string, string>>({});
  const [notifications, setNotifications] = useState<NotificationData[]>([]);
  const [triggerError, setTriggerError] = useState<string | null>(null);

  const alertsQuery = useQuery({ queryKey: ["alerts"], queryFn: listAlerts });

  useNotificationsStream({
    workspaceId: workspaceQuery.data,
    onNotification: (notification) => {
      setNotifications((prev) => [notification, ...prev].slice(0, 20));
    },
  });

  const createMutation = useMutation({
    mutationFn: () =>
      createAlert({
        type: "PRICE",
        symbol,
        condition: { op, price: Number(threshold) },
        channels: { in_app: true },
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["alerts"] });
    },
  });

  const triggerMutation = useMutation({
    mutationFn: ({ id, price }: { id: string; price: number }) => triggerAlert(id, price),
    onSuccess: async () => {
      setTriggerError(null);
      await queryClient.invalidateQueries({ queryKey: ["alerts"] });
    },
    onError: (err) => {
      setTriggerError(err instanceof Error ? err.message : t("alerts.error.notMet"));
    },
  });

  const alerts = alertsQuery.data?.items ?? [];

  return (
    <div className="flex flex-1 flex-col gap-6 p-4 sm:p-6 lg:p-8">
      <PageHeader testId="alerts-title" title={t("alerts.title")} description={t("alerts.intro")} />

      <form
        onSubmit={(event) => {
          event.preventDefault();
          createMutation.mutate();
        }}
        className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end"
      >
        <label className="flex flex-col gap-1 text-xs text-muted-foreground" htmlFor="alert-symbol">
          {t("common.symbol")}
          <Input
            id="alert-symbol"
            value={symbol}
            onChange={(event) => setSymbol(event.target.value.toUpperCase())}
            className="sm:w-28"
          />
        </label>
        <label className="flex flex-col gap-1 text-xs text-muted-foreground" htmlFor="alert-op">
          {t("alerts.condition")}
          <select
            id="alert-op"
            value={op}
            onChange={(event) => setOp(event.target.value as "gte" | "lte" | "eq")}
            className="h-11 rounded-md border border-border bg-input px-3 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background sm:h-9 sm:w-44"
          >
            <option value="gte">{t("alerts.op.gte")}</option>
            <option value="lte">{t("alerts.op.lte")}</option>
            <option value="eq">{t("alerts.op.eq")}</option>
          </select>
        </label>
        <label
          className="flex flex-col gap-1 text-xs text-muted-foreground"
          htmlFor="alert-threshold"
        >
          {t("alerts.threshold")}
          <Input
            id="alert-threshold"
            value={threshold}
            onChange={(event) => setThreshold(event.target.value)}
            className="sm:w-24"
          />
        </label>
        <Button type="submit" data-testid="create-alert" disabled={createMutation.isPending}>
          {t("alerts.create")}
        </Button>
      </form>

      {alertsQuery.isLoading && (
        <div className="flex flex-col gap-2" data-testid="alerts-loading">
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-20 w-full" />
        </div>
      )}
      {alertsQuery.isError && <p className="text-sm text-destructive">{t("common.error.load")}</p>}
      {triggerError && <p className="text-sm text-destructive">{triggerError}</p>}
      {!alertsQuery.isLoading && alerts.length === 0 && (
        <p className="text-sm text-muted-foreground" data-testid="alerts-empty">
          {t("alerts.empty")}
        </p>
      )}

      <ul className="flex flex-col gap-3">
        {alerts.map((alert) => (
          <li key={alert.id} data-testid={`alert-${alert.id}`}>
            <Card className="flex flex-col gap-3 p-3">
              <div className="min-w-0">
                <p className="text-sm font-medium text-foreground">
                  {alert.type} · <span className="font-mono">{JSON.stringify(alert.condition)}</span>
                </p>
                <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                  <Badge variant={alert.active ? "info" : "neutral"}>
                    {alert.active ? t("alerts.active") : t("alerts.inactive")}
                  </Badge>
                  {alert.last_triggered_at && (
                    <span>{t("alerts.lastTriggered", { time: alert.last_triggered_at })}</span>
                  )}
                </div>
              </div>

              <CardInset
                className="flex flex-col gap-2 border border-dashed border-warning/40 bg-warning/5"
                data-testid={`alert-ui-test-${alert.id}`}
              >
                <p className="max-w-[16rem] text-end text-[10px] font-semibold uppercase tracking-wide text-warning">
                  {t("alerts.uiTest.label")}
                </p>
                <div className="flex flex-wrap items-center gap-2">
                  <label htmlFor={`trigger-price-${alert.id}`} className="sr-only">
                    {t("alerts.uiTest.priceLabel")}
                  </label>
                  <Input
                    id={`trigger-price-${alert.id}`}
                    data-testid={`trigger-price-${alert.id}`}
                    value={triggerPrices[alert.id] ?? ""}
                    onChange={(event) =>
                      setTriggerPrices((prev) => ({ ...prev, [alert.id]: event.target.value }))
                    }
                    placeholder={t("common.price")}
                    className="h-9 w-24"
                  />
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    data-testid={`fire-ui-test-${alert.id}`}
                    onClick={() =>
                      triggerMutation.mutate({
                        id: alert.id,
                        price: Number(triggerPrices[alert.id] ?? "0"),
                      })
                    }
                    className="border-warning/50 text-warning hover:bg-warning/10"
                  >
                    {t("alerts.uiTest.fire")}
                  </Button>
                </div>
              </CardInset>
            </Card>
          </li>
        ))}
      </ul>

      <section className="flex flex-col gap-2">
        <h2 className="text-sm font-semibold text-foreground">{t("alerts.notifications")}</h2>
        {notifications.length === 0 && (
          <p className="text-sm text-muted-foreground">{t("alerts.notifications.empty")}</p>
        )}
        <ul className="flex flex-col gap-2" data-testid="notification-list">
          {notifications.map((note) => (
            <li key={note.id}>
              <Card className="border-info/30 bg-info/5 p-3">
                <p className="text-sm font-semibold text-foreground">{note.title}</p>
                <p className="text-xs text-muted-foreground">{note.message}</p>
              </Card>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
