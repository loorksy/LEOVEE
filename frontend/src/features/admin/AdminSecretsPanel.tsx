import { type FormEvent, useEffect, useState } from "react";
import type { AdminSecretItem } from "@/features/admin/types";

const LABELS: Record<string, string> = {
  OANDA_API_TOKEN: "OANDA API token (practice)",
  OANDA_ACCOUNT_ID: "OANDA account id (practice)",
  OANDA_ENVIRONMENT: "OANDA environment",
  ANTHROPIC_API_KEY: "Anthropic API key",
  OPENAI_API_KEY: "OpenAI API key",
  FINNHUB_API_KEY: "Finnhub API key",
  RESEND_API_KEY: "Resend API key",
  SECRET_KEY: "App SECRET_KEY",
  METRICS_BEARER_TOKEN: "Metrics bearer token",
  SENTRY_DSN: "Sentry DSN",
};

type Props = {
  items: AdminSecretItem[];
  oandaEnvironment: string;
  loading: boolean;
  saving: boolean;
  error: string | null;
  success: string | null;
  onSave: (secrets: Record<string, string>) => Promise<void>;
};

export function AdminSecretsPanel({
  items,
  oandaEnvironment,
  loading,
  saving,
  error,
  success,
  onSave,
}: Props) {
  const [drafts, setDrafts] = useState<Record<string, string>>({});

  useEffect(() => {
    // Reset local drafts when server status reloads (never hydrate secret values).
    setDrafts({});
  }, [items]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const payload: Record<string, string> = {};
    for (const [key, value] of Object.entries(drafts)) {
      if (value.trim().length > 0) payload[key] = value;
    }
    if (Object.keys(payload).length === 0) return;
    await onSave(payload);
    setDrafts({});
  }

  return (
    <section
      className="rounded-lg border border-slate-800 bg-leovee-panel p-4"
      data-testid="admin-secrets-panel"
    >
      <h2 className="text-lg font-medium text-slate-100">Platform secrets</h2>
      <p className="mt-1 text-sm text-slate-400">
        Set provider credentials here. Values are stored encrypted and never shown again — leave a
        field blank to keep the current value. Practice OANDA only (
        <code className="text-slate-300">{oandaEnvironment || "practice"}</code>
        ); execution stays disabled.
      </p>

      {loading && <p className="mt-3 text-sm text-slate-500">Loading secret status…</p>}
      {error && (
        <p role="alert" className="mt-3 text-sm text-amber-400">
          {error}
        </p>
      )}
      {success && (
        <p className="mt-3 text-sm text-emerald-400" data-testid="admin-secrets-saved">
          {success}
        </p>
      )}

      <form onSubmit={handleSubmit} className="mt-4 space-y-3">
        {items.map((item) => (
          <label key={item.key} className="block text-sm text-slate-300" htmlFor={`secret-${item.key}`}>
            <span className="flex items-center justify-between gap-2">
              <span>{LABELS[item.key] ?? item.key}</span>
              <span
                className={item.configured ? "text-emerald-400" : "text-slate-500"}
                data-testid={`secret-status-${item.key}`}
              >
                {item.configured ? "configured" : "not set"}
              </span>
            </span>
            <input
              id={`secret-${item.key}`}
              type={item.key === "OANDA_ENVIRONMENT" ? "text" : "password"}
              autoComplete="off"
              placeholder={item.configured ? "•••••••• (leave blank to keep)" : "Paste value"}
              value={drafts[item.key] ?? ""}
              onChange={(event) =>
                setDrafts((prev) => ({ ...prev, [item.key]: event.target.value }))
              }
              className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-slate-100"
            />
          </label>
        ))}
        <button
          type="submit"
          disabled={saving || loading}
          className="rounded bg-leovee-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500 disabled:opacity-50"
        >
          {saving ? "Saving…" : "Save secrets"}
        </button>
      </form>
    </section>
  );
}
