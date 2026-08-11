export type JournalEntryData = {
  id: string;
  title: string;
  notes: string;
  tags: string[];
  emotion: string | null;
  lesson: string | null;
  promoted_to_lesson_id: string | null;
  created_at: string;
};
