import { describe, expect, it } from "vitest";
import { portalGuideSteps, readPortalGuide } from "./portal-guide-domain";

describe("portal guide state", () => {
  it("defines stable stage A targets in order", () => {
    expect(portalGuideSteps.map((step) => step.target)).toEqual([
      "portal-role-landing",
      "portal-new-chat",
      "portal-shape",
      "portal-research-brief",
      "portal-save-note",
    ]);
  });

  it("resumes version one and restarts corrupt or old state", () => {
    expect(readPortalGuide('{"version":1,"step":2}')).toBe(2);
    expect(readPortalGuide('{"version":1,"step":5}')).toBeNull();
    expect(readPortalGuide('{"version":0,"step":2}')).toBe(0);
    expect(readPortalGuide("not json")).toBe(0);
  });
});
