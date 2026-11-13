import { describe, expect, it } from "vitest";
import { portalResearchGuideSteps, readPortalResearchGuide } from "./portal-research-guide-domain";

describe("portal research guide state", () => {
  it("defines stable worker-stage targets", () => {
    expect(portalResearchGuideSteps.map((step) => step.target)).toEqual([
      "portal-run-planner",
      "portal-watch-activity",
      "portal-plan-decision",
      "portal-run-researcher",
      "portal-field-report",
    ]);
    expect(portalResearchGuideSteps[2].action).toBe("Open accept / reject");
    expect(portalResearchGuideSteps[3].action).toBe("Run researcher");
    expect(portalResearchGuideSteps[4].action).toBe("Open field report");
  });

  it("resumes version one and restarts completed or corrupt state", () => {
    expect(readPortalResearchGuide('{"version":1,"step":2}')).toBe(2);
    expect(readPortalResearchGuide('{"version":1,"step":5}')).toBeNull();
    expect(readPortalResearchGuide('{"version":0,"step":2}')).toBe(0);
    expect(readPortalResearchGuide("not json")).toBe(0);
  });
});
