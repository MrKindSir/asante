export type ReviewGuideStep = { title: string; text: string; action: string; target?: string | null };

export const reviewGuideKey = "asante.reviewGuide.v1";
export const reviewGuideSteps: readonly ReviewGuideStep[] = [
  {
    target: "review-sign-in",
    title: "Open the reviewer workspace.",
    text: "Sign in with the Asante reviewer account. Contributor accounts stay in the private portal.",
    action: "Continue",
  },
  {
    target: "review-queue-nav",
    title: "Open the review queue.",
    text: "The queue contains submitted packets waiting for a human decision. Filter and select a packet without changing its status.",
    action: "Open review queue",
  },
  {
    target: "review-packet",
    title: "Inspect the frozen packet.",
    text: "Read the submitted narrative, claim, location, attribution and original-media identity from the saved revision.",
    action: "Inspect media drafts",
  },
  {
    target: "review-media-drafts",
    title: "Review transcript and translation drafts.",
    text: "Worker outputs are unreviewed decision support. Check their status, text and timed cues; they are not heritage proof or publishable captions.",
    action: "Open decision panel",
  },
  {
    target: "review-decision",
    title: "Prepare a human decision.",
    text: "Add a reason and choose approve, request changes, escalate or reject. This guide never makes that decision for you.",
    action: "Finish review guide",
  },
];

export function readReviewGuide(raw: string | null | undefined): number | null {
  if (raw === null || raw === undefined || raw === "") return null;
  try {
    const value: unknown = JSON.parse(raw);
    if (typeof value === "object" && value !== null && "version" in value && value.version === 1 && "step" in value && typeof value.step === "number" && Number.isInteger(value.step) && value.step >= 0 && value.step <= reviewGuideSteps.length) {
      return value.step === reviewGuideSteps.length ? null : value.step;
    }
  } catch {
    // Corrupt guide state starts a fresh guide when explicitly replayed.
  }
  return 0;
}
