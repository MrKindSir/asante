import { describe, expect, it } from "vitest";
import { readReviewGuide, reviewGuideSteps } from "./review-guide-domain";

describe("review guide state", () => {
  it("keeps the review flow in order", () => {
    expect(reviewGuideSteps.map((step) => step.target)).toEqual([
      "review-sign-in",
      "review-queue-nav",
      "review-packet",
      "review-media-drafts",
      "review-decision",
    ]);
  });

  it("resumes valid state and resets invalid state", () => {
    expect(readReviewGuide(undefined)).toBeNull();
    expect(readReviewGuide('{"version":1,"step":3}')).toBe(3);
    expect(readReviewGuide('{"version":1,"step":5}')).toBeNull();
    expect(readReviewGuide('{"version":1,"step":99}')).toBe(0);
    expect(readReviewGuide("not-json")).toBe(0);
  });
});
