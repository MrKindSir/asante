import type { FeatureGuideStep } from "./GuidedTour";

export const portalGuideKey = "asante.portalGuide.v1";
export const portalGuideSteps: readonly FeatureGuideStep[] = [
  {
    target: "portal-role-landing",
    title: "You are in the contributor portal.",
    text: "Your signed-in role opens this private story workspace. Profile settings and sign-out stay in the rail.",
    action: "Show me the chats",
  },
  {
    target: "portal-new-chat",
    title: "Start one story chat at a time.",
    text: "Use the + button to create a focused draft. Uploads and submissions are separate later stages; this first pass is for shaping the story.",
    action: "Open story shaping",
  },
  {
    target: "portal-shape",
    title: "Shape your story.",
    text: "Add a title and a claim, question, or note. You can refine the place, language, audience, source and original words before saving.",
    action: "Show the research brief",
  },
  {
    target: "portal-research-brief",
    title: "Research starts with your questions.",
    text: "The brief is where you give Asante the context and uncertainties that should guide later workers. Required questions are marked in the form.",
    action: "Show chat actions",
  },
  {
    target: "portal-save-note",
    title: "Save notes and review outputs here.",
    text: "Save note keeps your latest story edits. The research card starts empty; after research completes, the same chat area exposes the plan and candidate-source popups. Those outputs remain drafts for your interpretation.",
    action: "Finish guide",
  },
];

export function readPortalGuide(raw: string | null | undefined): number | null {
  try {
    const value: unknown = JSON.parse(raw || "null");
    if (typeof value === "object" && value !== null && "version" in value && value.version === 1 && "step" in value && typeof value.step === "number" && Number.isInteger(value.step) && value.step >= 0 && value.step <= portalGuideSteps.length) {
      return value.step === portalGuideSteps.length ? null : value.step;
    }
  } catch {
    // Corrupt guide state starts a fresh guide.
  }
  return 0;
}
