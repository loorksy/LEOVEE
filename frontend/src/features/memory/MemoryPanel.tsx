import { useLocale } from "@/i18n/context";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import type { CalibrationBin, MemoryListItem } from "./types";

type Props = {
  memories: MemoryListItem[];
  bins: CalibrationBin[];
  onDelete: (id: string) => void;
};

export function MemoryPanel({ memories, bins, onDelete }: Props) {
  const { t } = useLocale();
  return (
    <section className="grid grid-cols-1 gap-4 md:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>{t("memory.workspace")}</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="flex flex-col gap-2">
            {memories.map((memory) => (
              <li
                key={memory.id}
                className="flex items-start justify-between gap-3 rounded-lg border border-border p-3"
              >
                <div className="min-w-0">
                  <p className="truncate font-mono text-sm font-medium text-foreground">
                    {memory.key}
                  </p>
                  <p className="text-xs text-muted-foreground">{memory.type}</p>
                </div>
                <Button
                  type="button"
                  variant="destructive"
                  size="sm"
                  data-testid={`memory-delete-${memory.id}`}
                  onClick={() => onDelete(memory.id)}
                  className="shrink-0"
                >
                  {t("common.delete")}
                </Button>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
      <CalibrationChart bins={bins} />
    </section>
  );
}

function CalibrationChart({ bins }: { bins: CalibrationBin[] }) {
  const { t } = useLocale();
  const max = Math.max(1, ...bins.map((b) => b.predicted_count));
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("memory.calibration")}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex h-40 items-end gap-1">
          {bins.map((bin) => (
            <div
              key={`${bin.bin_lower}-${bin.bin_upper}`}
              className="flex-1 rounded-t bg-chart-1"
              style={{ height: `${(bin.predicted_count / max) * 100}%` }}
              title={`${bin.bin_lower}-${bin.bin_upper}`}
            />
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
