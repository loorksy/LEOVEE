import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { LocaleProvider } from "@/i18n/LocaleProvider";
import { MessageContent } from "./MessageContent";
import type { ChatArtifact } from "./types";

function renderContent(content: string, artifacts?: ChatArtifact[]) {
  return render(
    <LocaleProvider initialLocale="en">
      <MessageContent content={content} artifacts={artifacts} />
    </LocaleProvider>,
  );
}

describe("MessageContent", () => {
  it("renders plain prose as markdown when there is no fence", () => {
    renderContent("**bold** and plain");
    expect(screen.getByText("bold")).toBeInTheDocument();
  });

  it("renders a code artifact with its language label", () => {
    const raw = "```artifact\n" + '{"type":"python-script","language":"python"}\n' + "print(1)\n```";
    const stamped: ChatArtifact[] = [
      { type: "python-script", family: "code", title: null, language: "python", content: "print(1)" },
    ];
    renderContent(raw, stamped);
    expect(screen.getByText("print(1)")).toBeInTheDocument();
    expect(screen.getByText("python")).toBeInTheDocument();
  });

  it("renders a CSV table artifact as a grid", () => {
    const raw = "```artifact\n" + '{"type":"portfolio-summary"}\n' + "level,price\nentry,2001\n```";
    const stamped: ChatArtifact[] = [
      {
        type: "portfolio-summary",
        family: "table",
        title: null,
        language: null,
        content: "level,price\nentry,2001",
      },
    ];
    renderContent(raw, stamped);
    // Header and a cell both land in the rendered grid.
    expect(screen.getByText("level")).toBeInTheDocument();
    expect(screen.getByText("2001")).toBeInTheDocument();
    expect(screen.getByRole("table")).toBeInTheDocument();
  });

  it("prefers the server-stamped family over the parsed header", () => {
    // The fence header claims markdown, but the stamped copy says json: the
    // authoritative parse wins, so the payload renders pretty-printed.
    const raw = "```artifact\n" + '{"type":"markdown"}\n' + '{"a":1}\n```';
    const stamped: ChatArtifact[] = [
      { type: "json-viewer", family: "json", title: null, language: null, content: '{"a":1}' },
    ];
    renderContent(raw, stamped);
    // JSON renderer pretty-prints, inserting a newline+indent the raw text lacks.
    expect(screen.getByText(/"a": 1/)).toBeInTheDocument();
  });

  it("interleaves prose around an artifact", () => {
    const raw =
      "here is the table\n" +
      "```artifact\n" +
      '{"type":"table"}\n' +
      "| a |\n| - |\n| 1 |\n```\n" +
      "done";
    renderContent(raw, [
      { type: "table", family: "table", title: null, language: null, content: "| a |\n| - |\n| 1 |" },
    ]);
    expect(screen.getByText("here is the table")).toBeInTheDocument();
    expect(screen.getByText("done")).toBeInTheDocument();
  });
});
