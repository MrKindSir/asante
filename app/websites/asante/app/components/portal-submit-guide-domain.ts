import type { FeatureGuideStep } from "./GuidedTour";

export const portalSubmitGuideKey = "asante.portalSubmitGuide.v1";
export const portalSubmitGuideSteps: readonly FeatureGuideStep[] = [
  {
    target: "portal-submit-open",
    title: "Open review and submit.",
    text: "Review the saved story packet before sending it to the Asante human review team. Submission does not publish the story.",
    action: "Load packet preview",
  },
  {
    target: "portal-submit-preview",
    title: "Check the packet preview.",
    text: "This server-built snapshot is the authoritative revision that will be sent. Confirm the narrative, claim, attribution and verified media identity.",
    action: "Confirm packet",
  },
  {
    target: "portal-submit-consent",
    title: "Confirm review consent.",
    text: "Explicitly consent to sending this story packet, its location and attribution to Asante human review.",
    action: "Prepare send",
  },
  {
    target: "portal-submit-send",
    title: "Send once for human review.",
    text: "Send the saved packet once. A reviewer will decide what happens next; nothing publishes automatically.",
    action: "Send for human review",
  },
  {
    target: "portal-submission-id",
    title: "Keep the submission reference.",
    text: "The submission id confirms the packet reached the review queue. Keep editing closed for this frozen revision.",
    action: "Finish submit guide",
  },
];

export function readPortalSubmitGuide(raw: string | null | undefined): number | null {
  if (raw === null || raw === undefined || raw === "") return null;
  try {
    const value: unknown = JSON.parse(raw);
    if (typeof value === "object" && value !== null && "version" in value && value.version === 1 && "step" in value && typeof value.step === "number" && Number.isInteger(value.step) && value.step >= 0 && value.step <= portalSubmitGuideSteps.length) {
      return value.step === portalSubmitGuideSteps.length ? null : value.step;
    }
  } catch {
    // Corrupt guide state starts a fresh guide when explicitly replayed.
  }
  return 0;
}
