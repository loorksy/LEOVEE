import { useLocale } from "@/i18n/context";

type ProviderNotConfiguredBannerProps = {
  /** Short surface title, e.g. "LLM provider not configured". */
  title: string;
  /** Env / secret names that are missing. */
  credentials: string[];
  testId?: string;
  /** Optional extra guidance under the credential list. */
  hint?: string;
};

/** Uniform explicit "not configured" state for every provider-gated surface. */
export function ProviderNotConfiguredBanner({
  title,
  credentials,
  testId,
  hint,
}: ProviderNotConfiguredBannerProps) {
  const { t } = useLocale();
  return (
    <div
      className="rounded border border-amber-800/60 bg-amber-950/40 px-4 py-3 text-sm text-amber-100"
      data-testid={testId ?? "provider-not-configured"}
      role="status"
    >
      <p className="font-medium">{title}</p>
      <p className="mt-1 text-amber-200/80">
        {t("banner.notConfigured")}{" "}
        {credentials.map((name, index) => (
          <span key={name}>
            {index > 0 ? ", " : ""}
            <code className="text-amber-100">{name}</code>
          </span>
        ))}
        .
      </p>
      <p className="mt-1 text-amber-200/80">
        {hint ?? t("banner.hint")}
      </p>
    </div>
  );
}

export function llmCredentialNames(): string[] {
  return ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY"];
}

export function isLlmConfigured(status: {
  openai?: { configured?: boolean };
  anthropic?: { configured?: boolean };
  openrouter?: { configured?: boolean };
}): boolean {
  return Boolean(
    status.openai?.configured || status.anthropic?.configured || status.openrouter?.configured,
  );
}
