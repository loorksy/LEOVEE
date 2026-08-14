import { type FormEvent, useEffect, useState } from "react";
import type { AdminSecretItem } from "@/features/admin/types";
import { useLocale } from "@/i18n/context";
import type { TranslationKey } from "@/i18n";

// Managed key → dictionary key. An unmanaged key falls back to its raw name.
const LABEL_KEYS: Record<string, TranslationKey> = {
  OANDA_API_TOKEN: "admin.secrets.label.oandaApiToken",
  OANDA_ACCOUNT_ID: "admin.secrets.label.oandaAccountId",
  OANDA_ENVIRONMENT: "admin.secrets.label.oandaEnvironment",
  ANTHROPIC_API_KEY: "admin.secrets.label.anthropicApiKey",
  OPENAI_API_KEY: "admin.secrets.label.openaiApiKey",
  OPENROUTER_API_KEY: "admin.secrets.label.openrouterApiKey",
  FINNHUB_API_KEY: "admin.secrets.label.finnhubApiKey",
  RESEND_API_KEY: "admin.secrets.label.resendApiKey",
  SECRET_KEY: "admin.secrets.label.secretKey",
  METRICS_BEARER_TOKEN: "admin.secrets.label.metricsBearerToken",
  SENTRY_DSN: "admin.secrets.label.sentryDsn",
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
  const { t } = useLocale();
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
      <h2 className="text-lg font-medium text-slate-100">{t("admin.secrets.title")}</h2>
      <p className="mt-1 text-sm text-slate-400">
        {t("admin.secrets.intro")} (
        <code className="text-slate-300">{oandaEnvironment || "practice"}</code>
        ). {t("admin.secrets.executionDisabled")}
      </p>

      {loading && <p className="mt-3 text-sm text-slate-500">{t("common.loading")}</p>}
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
              <span>{LABEL_KEYS[item.key] ? t(LABEL_KEYS[item.key]) : item.key}</span>
              <span
                className={item.configured ? "text-emerald-400" : "text-slate-500"}
                data-testid={`secret-status-${item.key}`}
                data-configured={item.configured ? "true" : "false"}
              >
                {item.configured ? t("admin.secrets.configured") : t("admin.secrets.notSet")}
              </span>
            </span>
            <input
              id={`secret-${item.key}`}
              type={item.key === "OANDA_ENVIRONMENT" ? "text" : "password"}
              autoComplete="off"
              placeholder={
                item.configured
                  ? t("admin.secrets.placeholderKeep")
                  : t("admin.secrets.placeholderPaste")
              }
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
          {saving ? t("admin.secrets.saving") : t("admin.secrets.save")}
        </button>
      </form>
    </section>
  );
}
