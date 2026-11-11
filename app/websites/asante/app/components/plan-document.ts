import { Plan, ResearchPacket, ResearchSource } from "./story-domain";

export type FieldReportSection = { id: string; title: string; body: string; bullets: string[]; icon?: string };
export type FieldReportChart = { id: string; title: string; unit?: string; series: Array<{ label: string; value: number }> };
export type FieldReportTable = { id: string; title: string; columns: string[]; rows: string[][] };
export type FieldReportImage = { url: string; caption: string; credit: string; sourceUrl?: string };
export type FieldReportSource = Pick<ResearchSource, "title" | "url" | "excerpt" | "publisher" | "retrievedAt" | "status">;
export type FieldReportDocument = {
  title: string;
  subtitle: string;
  landmark: string;
  summary: string;
  sections: FieldReportSection[];
  charts: FieldReportChart[];
  tables: FieldReportTable[];
  images: FieldReportImage[];
  sources: FieldReportSource[];
  humanGate: string;
};

export function safeReportUrl(value: string | undefined): string {
  if (!value) return "";
  try {
    const url = new URL(value);
    return url.protocol === "https:" ? url.toString() : "";
  } catch { return ""; }
}

export function buildFieldReportDocument(project: {
  title: string;
  place: string;
  claim: string;
  plan?: Plan | null;
  research?: ResearchPacket | null;
}): FieldReportDocument {
  const plan = project.plan;
  const research = project.research as (ResearchPacket & {
    images?: FieldReportImage[];
    report?: { summary?: string; findings?: Array<{ text?: string }>; openQuestions?: string[] };
  }) | null | undefined;
  const sections: FieldReportSection[] = [];
  const add = (id: string, title: string, values: string[] | undefined, icon: string) => {
    if (values?.length) sections.push({ id, title, body: "", bullets: values, icon });
  };
  add("outline", "Story outline", plan?.outline, "◈");
  add("questions", "Questions to explore", plan?.questions, "? ");
  add("steps", "Suggested next steps", plan?.worker_steps, "↗");
  add("checklist", "Recording and review checklist", plan?.checklist, "✓");
  add("unknowns", "What remains uncertain", plan?.unknowns, "◇");
  const findings = research?.report?.findings?.map((finding) => finding.text || "").filter(Boolean) || [];
  add("research", "Research notes", findings.length ? findings : research?.notes, "⌕");
  add("human-questions", "Questions for human review", research?.report?.openQuestions, "◎");
  const images = (research?.images || []).filter((image) => safeReportUrl(image.url)).map((image) => ({ ...image, sourceUrl: safeReportUrl(image.sourceUrl) || undefined }));
  const sources = (research?.sources || []).filter((source) => safeReportUrl(source.url)).map((source) => ({ ...source, url: safeReportUrl(source.url) }));
  return {
    title: project.title || "Untitled story",
    subtitle: plan?.topic || "Asante field report",
    landmark: project.place || plan?.place_name || "",
    summary: research?.report?.summary || research?.summary || project.claim || "A working plan for a contributor-led story.",
    sections,
    charts: [],
    tables: [],
    images,
    sources,
    humanGate: plan?.human_gate || "A human reviewer must approve publication.",
  };
}
