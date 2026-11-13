import { describe, expect, it } from "vitest";
import { readReviewGuide, reviewGuideSteps } from "./review-guide-domain";

describe("review guide state", () => {
  it("keeps the review flow in order", () => {
    expect(reviewGuideSteps.map((step) => step.target)).toEqual([
      "review-queue-nav",
      "review-packet",
      "review-media-drafts",
      "review-decision",
    ]);
  });

  it("resumes valid state and resets invalid state", () => {
    expect(readReviewGuide(undefined)).toBeNull();
    expect(readReviewGuide('{"version":2,"step":2}')).toBe(2);
    expect(readReviewGuide('{"version":2,"step":4}')).toBeNull();
    expect(readReviewGuide('{"version":2,"step":99}')).toBe(0);
    expect(readReviewGuide("not-json")).toBe(0);
  });
});
