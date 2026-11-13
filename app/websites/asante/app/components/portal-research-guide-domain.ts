import type { FeatureGuideStep } from "./GuidedTour";

export const portalResearchGuideKey = "asante.portalResearchGuide.v1";
export const portalResearchGuideSteps: readonly FeatureGuideStep[] = [
  {
    target: "portal-run-planner",
    title: "Run the story planner.",
    text: "Start from the saved research brief. The planner prepares questions and an outline without changing your original story words.",
    action: "Watch the planner",
  },
  {
    target: "portal-watch-activity",
    title: "Watch recorded worker activity.",
    text: "Open the activity record to follow factual handoffs and progress. It is a saved worker trail, not hidden model reasoning.",
    action: "Open activity",
  },
  {
    target: "portal-plan-decision",
    title: "Accept or reject the plan.",
    text: "Review the planning suggestion and choose whether it should guide the researcher. This remains your decision.",
    action: "Open accept / reject",
  },
  {
    target: "portal-run-researcher",
    title: "Run the researcher.",
    text: "The researcher uses the saved brief and accepted or rejected planning handoff to collect bounded candidate evidence.",
    action: "Run researcher",
  },
  {
    target: "portal-field-report",
    title: "Review the field report and sources.",
    text: "When the run finishes, open the field report and candidate sources. They remain drafts for your interpretation, not verified proof.",
    action: "Open field report",
  },
];

export function readPortalResearchGuide(raw: string | null | undefined): number | null {
  if (raw === null || raw === undefined || raw === "") return null;
  try {
    const value: unknown = JSON.parse(raw || "null");
    if (typeof value === "object" && value !== null && "version" in value && value.version === 1 && "step" in value && typeof value.step === "number" && Number.isInteger(value.step) && value.step >= 0 && value.step <= portalResearchGuideSteps.length) {
      return value.step === portalResearchGuideSteps.length ? null : value.step;
    }
  } catch {
    // Corrupt guide state starts a fresh guide.
  }
  return 0;
}
