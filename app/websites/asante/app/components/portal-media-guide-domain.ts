import type { FeatureGuideStep } from "./GuidedTour";

export const portalMediaGuideKey = "asante.portalMediaGuide.v1";
export const portalMediaGuideSteps: readonly FeatureGuideStep[] = [
  {
    target: "portal-upload-open",
    title: "Open the recording upload.",
    text: "Choose one short audio or video recording for this draft. Uploading is separate from sending the story for human review.",
    action: "Open upload",
  },
  {
    target: "portal-upload-consent",
    title: "Confirm storage and analysis consent.",
    text: "Asante needs your explicit consent before storing and processing the original recording. The original remains preserved.",
    action: "Choose a recording",
  },
  {
    target: "portal-upload-file",
    title: "Choose one recording.",
    text: "Use a supported file within the visible size and ten-minute limits. The server verifies the actual media type, duration and checksum.",
    action: "Upload and verify",
  },
  {
    target: "portal-upload-verified",
    title: "Verify the original media.",
    text: "The chat shows the original only after Asante verifies the upload. Processing jobs are then queued from that verified asset.",
    action: "Show processing drafts",
  },
  {
    target: "portal-media-drafts",
    title: "Review processing drafts.",
    text: "Transcription, translation and video-analysis states stay explicit as queued, running, succeeded or unavailable. Draft text is never fabricated or treated as publishable.",
    action: "Finish media guide",
  },
];

export function readPortalMediaGuide(raw: string | null | undefined): number | null {
  if (raw === null || raw === undefined || raw === "") return null;
  try {
    const value: unknown = JSON.parse(raw);
    if (typeof value === "object" && value !== null && "version" in value && value.version === 1 && "step" in value && typeof value.step === "number" && Number.isInteger(value.step) && value.step >= 0 && value.step <= portalMediaGuideSteps.length) {
      return value.step === portalMediaGuideSteps.length ? null : value.step;
    }
  } catch {
    // Corrupt guide state starts a fresh guide when explicitly replayed.
  }
  return 0;
}
