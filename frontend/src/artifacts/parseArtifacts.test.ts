import { describe, expect, it } from "vitest";
import { parseArtifactSegments } from "./parseArtifacts";

describe("parseArtifactSegments", () => {
  it("returns a single text segment when there is no fence", () => {
    const segments = parseArtifactSegments("just prose, nothing fenced");
    expect(segments).toHaveLength(1);
    expect(segments[0]).toMatchObject({ kind: "text", text: "just prose, nothing fenced" });
  });

  it("interleaves text and a closed artifact in source order", () => {
    const raw =
      "before\n" +
      '```artifact\n{"type":"line-chart","family":"chart","title":"P"}\n{"data":[]}\n```\n' +
      "after";
    const segments = parseArtifactSegments(raw);
    expect(segments.map((s) => s.kind)).toEqual(["text", "artifact", "text"]);
    expect(segments[1].artifact).toMatchObject({
      type: "line-chart",
      family: "chart",
      title: "P",
      content: '{"data":[]}',
    });
    expect(segments[2].text).toContain("after");
  });

  it("marks a fence with no closing marker as still open", () => {
    const raw = '```artifact\n{"type":"table","family":"table"}\n| a | b |';
    const segments = parseArtifactSegments(raw);
    expect(segments.at(-1)?.kind).toBe("artifact-open");
  });

  it("keeps a malformed header under the markdown family rather than dropping it", () => {
    const raw = "```artifact\nnot json at all\npayload body\n```";
    const segments = parseArtifactSegments(raw);
    expect(segments[0]).toMatchObject({
      kind: "artifact",
      artifact: { type: "markdown", family: "markdown", content: "payload body" },
    });
  });

  it("parses two artifacts back to back", () => {
    const raw =
      '```artifact\n{"type":"code","family":"code","language":"py"}\nprint(1)\n```\n' +
      '```artifact\n{"type":"json","family":"json"}\n{"a":1}\n```\n';
    const artifacts = parseArtifactSegments(raw)
      .filter((s) => s.kind === "artifact")
      .map((s) => s.artifact);
    expect(artifacts.map((a) => a?.family)).toEqual(["code", "json"]);
    expect(artifacts[0]?.language).toBe("py");
  });
});
