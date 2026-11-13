import { describe, expect, it } from "vitest";
import { buildFieldReportDocument } from "./plan-document";

describe("field report document builder", () => {
  it("reuses planner sections and attributed HTTPS research references", () => {
    const document = buildFieldReportDocument({
      title: "River memories",
      place: "Soweto Towers",
      claim: "Which date needs confirmation?",
      plan: {
        project_id: "project-1",
        trace_id: "trace-1",
        worker_steps: ["Compare oral histories"],
        human_gate: "A human must review this report.",
        outline: ["Introduce the river"],
        questions: ["Who remembers the gathering?"],
      },
      research: {
        sources: [
          { title: "Local archive", url: "https://example.org/archive", excerpt: "Candidate reference" },
          { title: "Unsafe", url: "javascript:alert(1)" },
        ],
        images: [
          { url: "https://upload.wikimedia.org/commons/image.jpg", caption: "Archive photograph", credit: "Wikimedia contributor" },
          { url: "http://unsafe.example/image.jpg", caption: "Unsafe", credit: "Untrusted" },
        ],
      },
    });
    expect(document.sections.map((section) => section.title)).toContain("Story outline");
    expect(document.sources.map((source) => source.title)).toEqual(["Local archive"]);
    expect(document.images).toHaveLength(1);
    expect(document.images[0].credit).toBe("Wikimedia contributor");
    expect(document.charts).toEqual([]);
    expect(document.tables).toEqual([]);
  });
});
