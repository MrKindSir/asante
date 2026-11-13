import { describe, expect, it } from "vitest";
import { portalSubmitGuideSteps, readPortalSubmitGuide } from "./portal-submit-guide-domain";

describe("portal submit guide state", () => {
  it("keeps the packet flow in order", () => {
    expect(portalSubmitGuideSteps.map((step) => step.target)).toEqual([
      "portal-submit-open",
      "portal-submit-preview",
      "portal-submit-consent",
      "portal-submit-send",
      "portal-submission-id",
    ]);
  });

  it("resumes valid state and resets invalid state", () => {
    expect(readPortalSubmitGuide(undefined)).toBeNull();
    expect(readPortalSubmitGuide('{"version":1,"step":2}')).toBe(2);
    expect(readPortalSubmitGuide('{"version":1,"step":5}')).toBeNull();
    expect(readPortalSubmitGuide('{"version":1,"step":99}')).toBe(0);
    expect(readPortalSubmitGuide("not-json")).toBe(0);
  });
});
