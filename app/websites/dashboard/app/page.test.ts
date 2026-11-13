import { describe, expect, it } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import DashboardPage from "./page";
import { canApprove, filterQueue, Submission } from "./review-domain";
import { alternateAsanteRoute, isDirectAsanteRoute } from "./route-mode";

describe("Asante human review", () => {
  it("hands authentication back to the Asante portal before displaying private submissions", () => {
    const html = renderToStaticMarkup(createElement(DashboardPage));
    expect(html).toContain('<a class="brand" href="/asante/">');
    expect(html).toContain('href="/asante/portal/"');
    expect(html).toContain("Reviewers sign in through the Asante portal");
    expect(html).not.toContain('type="email"');
    expect(html).not.toContain('type="password"');
    expect(html).not.toContain("Asante reviewer access key");
    expect(html).not.toContain("Stories waiting to be heard.");
  });
  it("blocks approval until all blocking checks are resolved", () => {
    expect(canApprove({ status: "pending_review", findings: [{ check: "Media", status: "blocked", detail: "Pending" }] })).toBe(false);
    expect(canApprove({ status: "pending_review", findings: [] })).toBe(false);
    expect(canApprove({ status: "pending_review", findings: [{ check: "Consent", status: "pass", detail: "Recorded" }], review_policy: { version: "v1", may_approve: true, status: "human_review" } })).toBe(true);
    expect(canApprove({ status: "pending_review", findings: [{ check: "Consent", status: "pass", detail: "Recorded" }], review_policy: { version: "v1", may_approve: false, status: "blocked" } })).toBe(false);
    expect(canApprove({ status: "rejected", findings: [{ check: "Consent", status: "pass", detail: "Recorded" }], review_policy: { version: "v1", may_approve: true, status: "human_review" } })).toBe(false);
  });
  it("combines queue text and workflow status filters", () => {
    const queue = [
      { title: "River memory", contributor_name: "Nomsa", language: "zu", status: "pending_review" },
      { title: "Morning walk", contributor_name: "Thabo", language: "en", status: "rejected" }
    ] as Submission[];
    expect(filterQueue(queue, "NOMSA", "pending_review")).toHaveLength(1);
    expect(filterQueue(queue, "Nomsa", "rejected")).toHaveLength(0);
    expect(filterQueue(queue, "", "")).toHaveLength(2);
  });
});

describe("Asante route mode", () => {
  it("preserves the review route and query while switching clean and direct URLs", () => {
    const clean = "http://localhost/asante/review/?queue=pending#latest";
    expect(alternateAsanteRoute(clean, "8082")).toBe("http://localhost:8082/asante/review/?queue=pending#latest");
    expect(isDirectAsanteRoute("http://localhost:8082/asante/review/", "8082")).toBe(true);
    expect(alternateAsanteRoute("http://localhost:8082/asante/review/?queue=pending#latest", "8082")).toBe(clean);
  });
});
