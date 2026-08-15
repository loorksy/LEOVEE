import { type FormEvent, useEffect, useState } from "react";
import { AlertCircle, CheckCircle2, Circle } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Skeleton } from "@/components/ui/Skeleton";
import { cn } from "@/lib/cn";
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
    <Card data-testid="admin-secrets-panel">
      <CardHeader>
        <CardTitle>{t("admin.secrets.title")}</CardTitle>
        <p className="text-sm text-muted-foreground">
          {t("admin.secrets.intro")} (
          <code className="rounded bg-muted px-1 py-0.5 font-mono text-xs text-foreground">
            {oandaEnvironment || "practice"}
          </code>
          ). {t("admin.secrets.executionDisabled")}
        </p>
      </CardHeader>

      <form onSubmit={handleSubmit}>
        <CardContent className="flex flex-col gap-4">
          {loading && (
            <div className="flex flex-col gap-3" data-testid="admin-secrets-loading">
              <Skeleton className="h-14 w-full" />
              <Skeleton className="h-14 w-full" />
              <Skeleton className="h-14 w-full" />
            </div>
          )}

          {error && (
            <div
              role="alert"
              data-testid="admin-secrets-error"
              className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive"
            >
              <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
              <p>{error}</p>
            </div>
          )}
          {success && (
            <div
              role="status"
              data-testid="admin-secrets-saved"
              className="flex items-start gap-2 rounded-lg border border-success/30 bg-success/10 p-3 text-sm text-success"
            >
              <CheckCircle2 className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
              <p>{success}</p>
            </div>
          )}

          {!loading &&
            items.map((item) => (
              <div key={item.key} className="flex flex-col gap-1.5">
                <label
                  htmlFor={`secret-${item.key}`}
                  className="flex flex-wrap items-center justify-between gap-2 text-sm text-foreground"
                >
                  <span>{LABEL_KEYS[item.key] ? t(LABEL_KEYS[item.key]) : item.key}</span>
                  <span
                    className={cn(
                      "inline-flex items-center gap-1 text-xs font-medium",
                      item.configured ? "text-success" : "text-muted-foreground",
                    )}
                    data-testid={`secret-status-${item.key}`}
                    data-configured={item.configured ? "true" : "false"}
                  >
                    {item.configured ? (
                      <CheckCircle2 className="size-3.5" aria-hidden="true" />
                    ) : (
                      <Circle className="size-3.5" aria-hidden="true" />
                    )}
                    {item.configured ? t("admin.secrets.configured") : t("admin.secrets.notSet")}
                  </span>
                </label>
                <Input
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
                />
              </div>
            ))}
        </CardContent>

        <CardFooter>
          <Button type="submit" disabled={saving || loading} data-testid="admin-secrets-save">
            {saving ? t("admin.secrets.saving") : t("admin.secrets.save")}
          </Button>
        </CardFooter>
      </form>
    </Card>
  );
}
