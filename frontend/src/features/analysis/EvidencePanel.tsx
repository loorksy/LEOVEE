import type { EvidenceCheck, EvidenceReport } from "@/api/analysis";
import { useLocale } from "@/i18n/context";
import type { LocaleContextValue } from "@/i18n/context";

type Translator = LocaleContextValue["t"];

/** The readings the agent must take before a direction is published — shown as
 *  a checklist so the operator can see what backed the call, or which reading
 *  blocked it. The order matches the pipeline: context first, live price last.
 *  Keys are literal so the strictly-typed translator accepts them. */
const CHECK_LABELS = {
  market_structure: "evidence.check.market_structure",
  liquidity_map: "evidence.check.liquidity_map",
  supply_demand: "evidence.check.supply_demand",
  institutional_behavior: "evidence.check.institutional_behavior",
  multi_timeframe_bias: "evidence.check.multi_timeframe_bias",
  volatility_regime: "evidence.check.volatility_regime",
  trading_session: "evidence.check.trading_session",
  market_intelligence: "evidence.check.market_intelligence",
  event_blackout: "evidence.check.event_blackout",
  live_price: "evidence.check.live_price",
} as const;

type TranslationKey = Parameters<Translator>[0];

const CHECK_ORDER = Object.keys(CHECK_LABELS);

function checkLabel(name: string, t: Translator): string {
  const key = (CHECK_LABELS as Record<string, TranslationKey | undefined>)[name];
  // A check the UI has not localized yet still reads as its humanized name
  // rather than a dotted key.
  return key ? t(key) : name.replace(/_/g, " ");
}

function statusClass(status: EvidenceCheck["status"]): string {
  switch (status) {
    case "ok":
      return "text-success";
    case "warning":
      return "text-warning";
    default:
      return "text-destructive";
  }
}

function statusGlyph(status: EvidenceCheck["status"]): string {
  return status === "ok" ? "✓" : status === "warning" ? "!" : "✗";
}

export function EvidencePanel({ report }: { report: EvidenceReport }) {
  const { t } = useLocale();
  const byName = new Map(report.checks.map((check) => [check.name, check]));
  const ordered = [
    ...CHECK_ORDER.filter((name) => byName.has(name)).map((name) => byName.get(name) as EvidenceCheck),
    ...report.checks.filter((check) => !CHECK_ORDER.includes(check.name)),
  ];

  return (
    <section
      className="mt-4 rounded border border-slate-800 bg-slate-900/60 p-4"
      data-testid="evidence-panel"
    >
      <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
        {t("evidence.title")}
      </h3>
      {report.blocked && report.block_reason && (
        <p className="mt-1 text-xs text-destructive" data-testid="evidence-blocked-by">
          {t("evidence.blockedBy", { reason: report.block_reason })}
        </p>
      )}
      <ul className="mt-2 space-y-1">
        {ordered.map((check) => (
          <li
            key={check.name}
            className="flex items-baseline gap-2 text-sm"
            data-testid={`evidence-check-${check.name}`}
          >
            <span className={`w-4 shrink-0 font-bold ${statusClass(check.status)}`} aria-hidden>
              {statusGlyph(check.status)}
            </span>
            <span className="text-slate-200">{checkLabel(check.name, t)}</span>
            {check.blocking && check.status !== "ok" && (
              <span className="text-xs text-destructive">({t("evidence.blocking")})</span>
            )}
            {check.detail && <span className="text-xs text-slate-500">— {check.detail}</span>}
          </li>
        ))}
      </ul>
    </section>
  );
}
