import { useState } from "react";
import { DEFAULT_SYMBOL } from "@/config/symbols";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createAlert, listAlerts, triggerAlert } from "@/api/alerts";
import { useWorkspaceId } from "@/hooks/useWorkspaceId";
import { useNotificationsStream } from "@/features/alerts/useNotificationsStream";
import type { NotificationData } from "@/features/alerts/types";

export function AlertsPage() {
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
      setTriggerError(err instanceof Error ? err.message : "Alert condition not met");
    },
  });

  const alerts = alertsQuery.data?.items ?? [];

  return (
    <div className="flex flex-1 flex-col gap-6 p-8">
      <header>
        <h1 className="text-2xl font-semibold text-slate-100">Alerts</h1>
        <p className="mt-1 text-slate-400">
          Create price alerts. Live evaluation runs from market ticks on the worker — not from the
          UI test control below.
        </p>
      </header>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          createMutation.mutate();
        }}
        className="flex flex-wrap items-end gap-2"
      >
        <div className="flex flex-col">
          <label htmlFor="alert-symbol" className="text-xs text-slate-500">
            Symbol
          </label>
          <input
            id="alert-symbol"
            value={symbol}
            onChange={(event) => setSymbol(event.target.value.toUpperCase())}
            className="w-28 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-sm text-slate-100"
          />
        </div>
        <div className="flex flex-col">
          <label htmlFor="alert-op" className="text-xs text-slate-500">
            Condition
          </label>
          <select
            id="alert-op"
            value={op}
            onChange={(event) => setOp(event.target.value as "gte" | "lte" | "eq")}
            className="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-sm text-slate-100"
          >
            <option value="gte">Price ≥</option>
            <option value="lte">Price ≤</option>
            <option value="eq">Price =</option>
          </select>
        </div>
        <div className="flex flex-col">
          <label htmlFor="alert-threshold" className="text-xs text-slate-500">
            Threshold
          </label>
          <input
            id="alert-threshold"
            value={threshold}
            onChange={(event) => setThreshold(event.target.value)}
            className="w-24 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-sm text-slate-100"
          />
        </div>
        <button
          type="submit"
          disabled={createMutation.isPending}
          className="rounded bg-leovee-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500 disabled:opacity-50"
        >
          Create alert
        </button>
      </form>

      {alertsQuery.isLoading && <p className="text-slate-400">Loading alerts…</p>}
      {alertsQuery.isError && <p className="text-amber-400">Could not load alerts.</p>}
      {triggerError && <p className="text-amber-400">{triggerError}</p>}
      {!alertsQuery.isLoading && alerts.length === 0 && (
        <p className="text-slate-400">No alerts yet — create one above.</p>
      )}

      <ul className="space-y-2">
        {alerts.map((alert) => (
          <li
            key={alert.id}
            data-testid={`alert-${alert.id}`}
            className="flex flex-wrap items-center justify-between gap-3 rounded border border-slate-800 bg-leovee-panel p-3 text-sm"
          >
            <div>
              <p className="font-medium text-slate-100">
                {alert.type} · {JSON.stringify(alert.condition)}
              </p>
              <p className="text-xs text-slate-500">
                {alert.active ? "Active" : "Inactive"}
                {alert.last_triggered_at ? ` · last triggered ${alert.last_triggered_at}` : ""}
              </p>
            </div>
            <div
              className="flex flex-col items-end gap-1 rounded border border-dashed border-amber-800/70 bg-amber-950/20 p-2"
              data-testid={`alert-ui-test-${alert.id}`}
            >
              <p className="max-w-[14rem] text-right text-[10px] font-semibold uppercase tracking-wide text-amber-300">
                UI test control — not live evaluation
              </p>
              <div className="flex items-center gap-2">
                <label htmlFor={`trigger-price-${alert.id}`} className="sr-only">
                  UI test price (not a live market quote) for {alert.type} alert
                </label>
                <input
                  id={`trigger-price-${alert.id}`}
                  value={triggerPrices[alert.id] ?? ""}
                  onChange={(event) =>
                    setTriggerPrices((prev) => ({ ...prev, [alert.id]: event.target.value }))
                  }
                  placeholder="test price"
                  className="w-24 rounded border border-amber-900/60 bg-slate-900 px-2 py-1 text-slate-100"
                />
                <button
                  type="button"
                  onClick={() =>
                    triggerMutation.mutate({
                      id: alert.id,
                      price: Number(triggerPrices[alert.id] ?? "0"),
                    })
                  }
                  className="rounded border border-amber-700/70 px-3 py-1 text-xs font-medium text-amber-100 hover:bg-amber-950/50"
                >
                  Fire UI test (not live)
                </button>
              </div>
            </div>
          </li>
        ))}
      </ul>

      <section>
        <h2 className="text-lg font-semibold text-slate-100">Notifications</h2>
        {notifications.length === 0 && (
          <p className="mt-2 text-sm text-slate-400">
            No notifications yet. Live alerts arrive from market evaluation; the UI test control
            only exercises the notification fan-out path.
          </p>
        )}
        <ul className="mt-2 space-y-2" data-testid="notification-list">
          {notifications.map((note) => (
            <li
              key={note.id}
              className="rounded border border-sky-800 bg-sky-950/40 p-3 text-sm text-sky-200"
            >
              <p className="font-semibold">{note.title}</p>
              <p className="text-xs">{note.message}</p>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
