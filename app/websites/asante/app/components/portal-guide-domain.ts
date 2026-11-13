import type { FeatureGuideStep } from "./GuidedTour";

export const portalGuideKey = "asante.portalGuide.v1";
// A safe, clearly labelled TestData example keeps the first-time guide
// runnable without asking a tester to invent or submit personal content.
// It mirrors the "Cities, Scripts, and Long Memory" research pack.
export const portalGuideStoryPreset = {
  title: "Cities, Scripts, and Long Memory",
  place: "Cairo",
  language: "en",
  format: "video",
  audience: "Students confronting simplified school histories of Africa",
  claim: "How should this test clip be framed responsibly?",
  source: "https://www.pbs.org/",
  transcript: "TEST ONLY educational excerpt inspired by Africa's Great Civilizations framing. Not original Asante fieldwork.",
  researchBrief: {
    knownMaterial: "Henry Louis Gates Jr.'s Africa's Great Civilizations surveys deep African history across regions. This 45-second cut is used only for Asante transcription and research-flow testing.",
    questions: "What early African polities, scripts, cities, or knowledge systems are highlighted, and which reputable sources can support the story without treating documentary narration as primary evidence?",
    context: "Henry Louis Gates Jr.; PBS documentary series; Cairo as the Asante place tag for continental deep-history framing in this test packet.",
    priorities: "Prefer PBS, museum essays, and peer-reviewed overviews. Keep TEST ONLY explicit.",
    uncertainties: "The exact topics in this excerpt and how much of the narration is synthesis versus primary evidence.",
  },
} as const;
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
    text: "A TestData example is loaded so you can see the complete flow. Review the title, place, claim and source, then save it to continue.",
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
