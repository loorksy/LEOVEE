import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createJournalEntry, listJournalEntries, promoteJournalEntry } from "@/api/journal";
import { useLocale } from "@/i18n/context";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Skeleton } from "@/components/ui/Skeleton";

export function JournalPage() {
  const { t } = useLocale();
  const queryClient = useQueryClient();
  const [title, setTitle] = useState("");
  const [notes, setNotes] = useState("");
  const [promoteError, setPromoteError] = useState<string | null>(null);
  const [lastPromotedLessonId, setLastPromotedLessonId] = useState<string | null>(null);

  const entriesQuery = useQuery({ queryKey: ["journal"], queryFn: listJournalEntries });

  const createMutation = useMutation({
    mutationFn: () => createJournalEntry({ title, notes }),
    onSuccess: async () => {
      setTitle("");
      setNotes("");
      await queryClient.invalidateQueries({ queryKey: ["journal"] });
    },
  });

  const promoteMutation = useMutation({
    mutationFn: (id: string) => promoteJournalEntry(id),
    onSuccess: async (result) => {
      setPromoteError(null);
      setLastPromotedLessonId(result.lesson_id);
      await queryClient.invalidateQueries({ queryKey: ["journal"] });
    },
    onError: (err) => {
      setPromoteError(err instanceof Error ? err.message : t("journal.error.promote"));
    },
  });

  const entries = entriesQuery.data?.items ?? [];

  return (
    <div className="flex flex-1 flex-col gap-6 p-4 sm:p-6 lg:p-8">
      <PageHeader testId="journal-title" title={t("journal.title")} description={t("journal.intro")} />

      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (title.trim()) createMutation.mutate();
        }}
        className="flex flex-col gap-3"
      >
        <label
          htmlFor="journal-title"
          className="flex flex-col gap-1 text-xs text-muted-foreground"
        >
          {t("journal.form.title")}
          <Input
            id="journal-title"
            data-testid="journal-title-input"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            className="sm:max-w-md"
          />
        </label>
        <label
          htmlFor="journal-notes"
          className="flex flex-col gap-1 text-xs text-muted-foreground"
        >
          {t("journal.form.notes")}
          <textarea
            id="journal-notes"
            data-testid="journal-notes-input"
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
            rows={3}
            className="rounded-md border border-border bg-input px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background sm:max-w-md"
          />
        </label>
        <Button
          type="submit"
          data-testid="journal-add"
          disabled={createMutation.isPending}
          className="self-start"
        >
          {t("journal.add")}
        </Button>
      </form>

      {promoteError && <p className="text-sm text-destructive">{promoteError}</p>}
      {lastPromotedLessonId && (
        <p className="text-xs text-muted-foreground" data-testid="promoted-lesson">
          {t("journal.promoted")}: <span className="font-mono">{lastPromotedLessonId}</span>
        </p>
      )}

      {entriesQuery.isLoading && (
        <div className="flex flex-col gap-2" data-testid="journal-loading">
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
        </div>
      )}
      {entriesQuery.isError && <p className="text-sm text-destructive">{t("common.error.load")}</p>}
      {!entriesQuery.isLoading && entries.length === 0 && (
        <p className="text-sm text-muted-foreground" data-testid="journal-empty">
          {t("journal.empty")}
        </p>
      )}

      <ul className="flex flex-col gap-3">
        {entries.map((entry) => (
          <li key={entry.id} data-testid={`journal-entry-${entry.id}`}>
            <Card className="flex flex-col gap-3 p-3 sm:flex-row sm:items-start sm:justify-between">
              <div className="min-w-0">
                <p className="text-sm font-medium text-foreground">{entry.title}</p>
                <p className="mt-1 text-sm text-muted-foreground">{entry.notes}</p>
              </div>
              {entry.promoted_to_lesson_id ? (
                <Badge variant="info" className="shrink-0 self-start">
                  {t("journal.lessonLearned")}
                </Badge>
              ) : (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  data-testid={`journal-promote-${entry.id}`}
                  onClick={() => promoteMutation.mutate(entry.id)}
                  disabled={promoteMutation.isPending}
                  className="shrink-0 self-start"
                >
                  {t("journal.promote")}
                </Button>
              )}
            </Card>
          </li>
        ))}
      </ul>
    </div>
  );
}
