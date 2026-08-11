import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createJournalEntry, listJournalEntries, promoteJournalEntry } from "@/api/journal";

export function JournalPage() {
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
      setPromoteError(err instanceof Error ? err.message : "Could not promote entry");
    },
  });

  const entries = entriesQuery.data?.items ?? [];

  return (
    <div className="flex flex-1 flex-col gap-6 p-8">
      <header>
        <h1 className="text-2xl font-semibold text-slate-100">Journal</h1>
        <p className="mt-1 text-slate-400">
          Log trade reflections and promote lessons into durable memory (§31).
        </p>
      </header>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (title.trim()) createMutation.mutate();
        }}
        className="flex flex-col gap-2"
      >
        <label htmlFor="journal-title" className="text-xs text-slate-500">
          Title
        </label>
        <input
          id="journal-title"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          className="rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100"
        />
        <label htmlFor="journal-notes" className="text-xs text-slate-500">
          Notes
        </label>
        <textarea
          id="journal-notes"
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
          rows={3}
          className="rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100"
        />
        <button
          type="submit"
          disabled={createMutation.isPending}
          className="self-start rounded bg-leovee-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500 disabled:opacity-50"
        >
          Add entry
        </button>
      </form>

      {promoteError && <p className="text-amber-400">{promoteError}</p>}
      {lastPromotedLessonId && (
        <p className="text-xs text-slate-500" data-testid="promoted-lesson">
          Promoted to lesson {lastPromotedLessonId}
        </p>
      )}

      {entriesQuery.isLoading && <p className="text-slate-400">Loading journal…</p>}
      {entriesQuery.isError && <p className="text-amber-400">Could not load journal entries.</p>}
      {!entriesQuery.isLoading && entries.length === 0 && (
        <p className="text-slate-400">No journal entries yet — add one above.</p>
      )}

      <ul className="space-y-3">
        {entries.map((entry) => (
          <li
            key={entry.id}
            data-testid={`journal-entry-${entry.id}`}
            className="rounded-lg border border-slate-800 bg-leovee-panel p-4"
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="font-medium text-slate-100">{entry.title}</p>
                <p className="mt-1 text-sm text-slate-400">{entry.notes}</p>
              </div>
              {entry.promoted_to_lesson_id ? (
                <span className="whitespace-nowrap rounded bg-emerald-900/40 px-2 py-1 text-xs text-emerald-300">
                  Lesson learned
                </span>
              ) : (
                <button
                  type="button"
                  onClick={() => promoteMutation.mutate(entry.id)}
                  disabled={promoteMutation.isPending}
                  className="whitespace-nowrap rounded border border-slate-700 px-3 py-1 text-xs text-slate-200 hover:bg-slate-800 disabled:opacity-50"
                >
                  Promote to lesson
                </button>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
