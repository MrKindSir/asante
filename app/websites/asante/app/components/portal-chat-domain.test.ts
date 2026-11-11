import { describe, expect, it } from "vitest";
import { illustrativePublishedHistory, portalChatHref, readPortalChatSelection } from "./portal-chat-domain";

describe("portal chat URL state", () => {
  it("keeps an open project chat in the refreshable URL", () => {
    const href = portalChatHref({ projectId: "project-123", publishedId: null });
    expect(href).toBe("/portal/?project=project-123");
    expect(readPortalChatSelection(new URLSearchParams(href.split("?")[1]))).toEqual({ projectId: "project-123", publishedId: null });
  });

  it("uses a published-story query without leaving a stale project selection", () => {
    const href = portalChatHref({ projectId: null, publishedId: "story id" });
    expect(href).toBe("/portal/?published=story+id");
    expect(readPortalChatSelection(new URLSearchParams(href.split("?")[1]))).toEqual({ projectId: null, publishedId: "story id" });
  });

  it("prefers project state if both query parameters are present", () => {
    expect(readPortalChatSelection(new URLSearchParams("published=story-1&project=project-2"))).toEqual({ projectId: "project-2", publishedId: null });
  });

  it("labels generated archive history as illustrative content", () => {
    expect(illustrativePublishedHistory("River story")).toContain("A human reviewer approved the story for the public map.");
  });
});
