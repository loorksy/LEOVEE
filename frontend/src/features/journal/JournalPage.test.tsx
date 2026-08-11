import { describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "@/test/renderWithProviders";
import { JournalPage } from "./JournalPage";
import * as journalApi from "@/api/journal";

describe("JournalPage", () => {
  it("lists journal entries and promotes one to a lesson", async () => {
    vi.spyOn(journalApi, "listJournalEntries").mockResolvedValue({
      items: [
        {
          id: "entry-1",
          title: "Faded the sweep too early",
          notes: "Should have waited for structure confirmation.",
          tags: ["discipline"],
          emotion: "frustrated",
          lesson: null,
          promoted_to_lesson_id: null,
          created_at: "2024-01-01T00:00:00.000Z",
        },
      ],
    });
    const promoteSpy = vi
      .spyOn(journalApi, "promoteJournalEntry")
      .mockResolvedValue({ lesson_id: "lesson-1" });

    renderWithProviders(<JournalPage />);

    expect(await screen.findByText("Faded the sweep too early")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /promote to lesson/i }));

    await waitFor(() => expect(promoteSpy).toHaveBeenCalledWith("entry-1"));
    expect(await screen.findByTestId("promoted-lesson")).toHaveTextContent("lesson-1");
  });

  it("creates a journal entry from the form", async () => {
    vi.spyOn(journalApi, "listJournalEntries").mockResolvedValue({ items: [] });
    const createSpy = vi
      .spyOn(journalApi, "createJournalEntry")
      .mockResolvedValue({ id: "entry-2" });

    renderWithProviders(<JournalPage />);

    expect(await screen.findByText(/no journal entries yet/i)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/^title$/i), { target: { value: "New reflection" } });
    fireEvent.change(screen.getByLabelText(/^notes$/i), { target: { value: "Notes here" } });
    fireEvent.click(screen.getByRole("button", { name: /add entry/i }));

    await waitFor(() =>
      expect(createSpy).toHaveBeenCalledWith({ title: "New reflection", notes: "Notes here" }),
    );
  });
});
