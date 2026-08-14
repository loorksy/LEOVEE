import { useLocale } from "@/i18n/context";
import type { CalibrationBin, MemoryListItem } from "./types";

type Props = {
  memories: MemoryListItem[];
  bins: CalibrationBin[];
  onDelete: (id: string) => void;
};

export function MemoryPanel({ memories, bins, onDelete }: Props) {
  const { t } = useLocale();
  return (
    <section className="grid gap-6 md:grid-cols-2">
      <div>
        <h2 className="mb-3 text-lg font-semibold text-slate-100">{t("memory.workspace")}</h2>
        <ul className="space-y-2">
          {memories.map((memory) => (
            <li
              key={memory.id}
              className="flex items-start justify-between gap-3 rounded border border-slate-700 p-3"
            >
              <div>
                <p className="font-medium text-slate-100">{memory.key}</p>
                <p className="text-xs text-slate-400">{memory.type}</p>
              </div>
              <button
                type="button"
                data-testid={`memory-delete-${memory.id}`}
                className="text-sm text-red-400 hover:text-red-300"
                onClick={() => onDelete(memory.id)}
              >
                {t("common.delete")}
              </button>
            </li>
          ))}
        </ul>
      </div>
      <CalibrationChart bins={bins} />
    </section>
  );
}

function CalibrationChart({ bins }: { bins: CalibrationBin[] }) {
  const { t } = useLocale();
  const max = Math.max(1, ...bins.map((b) => b.predicted_count));
  return (
    <div>
      <h2 className="mb-3 text-lg font-semibold text-slate-100">{t("memory.calibration")}</h2>
      <div className="flex h-40 items-end gap-1">
        {bins.map((bin) => (
          <div
            key={`${bin.bin_lower}-${bin.bin_upper}`}
            className="flex-1 bg-sky-600"
            style={{ height: `${(bin.predicted_count / max) * 100}%` }}
            title={`${bin.bin_lower}-${bin.bin_upper}`}
          />
        ))}
      </div>
    </div>
  );
}
