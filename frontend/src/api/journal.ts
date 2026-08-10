import { apiFetch } from "@/api/httpClient";
import type { JournalEntryData } from "@/features/journal/types";

export async function listJournalEntries(): Promise<{ items: JournalEntryData[] }> {
  return apiFetch<{ items: JournalEntryData[] }>("/api/v1/journal");
}

export type CreateJournalEntryInput = {
  title: string;
  notes?: string;
  tags?: string[];
  emotion?: string | null;
  lesson?: string | null;
};

export async function createJournalEntry(
  input: CreateJournalEntryInput,
): Promise<{ id: string }> {
  return apiFetch<{ id: string }>("/api/v1/journal", {
    method: "POST",
    body: input,
  });
}

/** Promotes a journal entry into a durable `lessons` memory row (phase 31). */
export async function promoteJournalEntry(id: string): Promise<{ lesson_id: string }> {
  return apiFetch<{ lesson_id: string }>(`/api/v1/journal/${id}/promote`, {
    method: "POST",
  });
}
