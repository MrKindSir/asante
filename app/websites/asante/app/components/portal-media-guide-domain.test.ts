import { describe, expect, it } from "vitest";
import { portalMediaGuideSteps, readPortalMediaGuide } from "./portal-media-guide-domain";

describe("portal media guide state", () => {
  it("defines stable upload and draft targets", () => {
    expect(portalMediaGuideSteps.map((step) => step.target)).toEqual([
      "portal-upload-open",
      "portal-upload-consent",
      "portal-upload-file",
      "portal-upload-verified",
      "portal-media-drafts",
    ]);
  });

  it("resumes version one and keeps absent state opt-in", () => {
    expect(readPortalMediaGuide(undefined)).toBeNull();
    expect(readPortalMediaGuide('{"version":1,"step":2}')).toBe(2);
    expect(readPortalMediaGuide('{"version":1,"step":5}')).toBeNull();
    expect(readPortalMediaGuide('{"version":0,"step":2}')).toBe(0);
    expect(readPortalMediaGuide("not json")).toBe(0);
  });
});
