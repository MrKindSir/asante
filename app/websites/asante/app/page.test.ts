import { afterEach, describe, expect, it, vi } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import StoryPlayer from "./components/StoryPlayer";
import AccountAccess from "./components/AccountAccess";
import ContributorChat from "./components/ContributorChat";
import { api, filterStories, guideSteps, mediaError, readGuide, Story, tourPosition } from "./components/story-domain";
import { accuracyFeatures, discoveryReducer, initialDiscoveryState, landmarkFeatures, loadMapCatalogue, visibleStories } from "./components/map-domain";

const records: Story[] = [
  { id: "1", title: "A river memory", contributor_name: "Nomsa", language: "zu", media_format: "audio", landmark_id: "soweto", landmark: "Soweto", distance_m: 100, status: "published" },
  { id: "2", title: "A morning walk", contributor_name: "Thabo", language: "en", media_format: "video", landmark_id: "hill", landmark: "Constitution Hill", distance_m: 200, status: "published" }
];
afterEach(() => vi.unstubAllGlobals());
it("offers email/password sign-in and explicit account creation", () => {
  const html = renderToStaticMarkup(createElement(AccountAccess, { onReady: () => undefined }));
  expect(html).toContain("Sign in to Asante");
  expect(html).toContain('type="email"');
  expect(html).toContain('type="password"');
  expect(html).toContain("Create an account");
  expect(html).not.toContain('type="hidden"');
});
describe("Asante onboarding state", () => {
  it("starts new and corrupt preferences at step zero", () => {
    expect(readGuide(null)).toBe(0);
    expect(readGuide("bad JSON")).toBe(0);
    expect(readGuide('{"version":2,"step":-1}')).toBe(0);
    expect(readGuide('{"version":1,"step":3}')).toBe(0);
  });
  it("resumes valid steps and preserves completion", () => {
    expect(guideSteps).toHaveLength(5);
    expect(readGuide('{"version":2,"step":3}')).toBe(3);
    expect(readGuide('{"version":2,"step":5}')).toBeNull();
  });
  it("places the tour beside its target and flips to stay inside the viewport", () => {
    const target = { left: 20, top: 120, right: 350, bottom: 160, width: 330, height: 40 };
    const beside = tourPosition(target, { width: 1400, height: 900 }, { width: 330, height: 300 });
    expect(beside.left).toBeGreaterThan(target.right);
    const mobile = tourPosition(target, { width: 390, height: 700 }, { width: 330, height: 300 });
    expect(mobile.top).toBeGreaterThan(target.bottom);
    expect(mobile.left).toBeGreaterThanOrEqual(14);
    expect(mobile.left + 330).toBeLessThanOrEqual(376);
    const right = tourPosition({ ...target, left: 1000, right: 1300 }, { width: 1400, height: 900 }, { width: 330, height: 300 });
    expect(right.left + 330).toBeLessThanOrEqual(1386);
    expect(tourPosition(null, { width: 1000, height: 800 }, { width: 330, height: 300 })).toEqual({ left: 335, top: 250 });
  });
});
describe("Asante discovery and upload boundaries", () => {
  it("loads the global catalogue without requiring or applying a proximity filter", async () => {
    const paths: string[] = [];
    const request = async <T,>(path: string): Promise<T> => {
      paths.push(path);
      const items = path.startsWith("/v1/landmarks") ? [] : records;
      return { items } as T;
    };
    const catalogue = await loadMapCatalogue(request);
    expect(paths).toEqual(["/v1/landmarks", "/v1/stories"]);
    expect(catalogue.stories).toHaveLength(2);
    const locatedCatalogue = await loadMapCatalogue(request, { latitude: -26.2, longitude: 28.0, accuracy: 45 });
    expect(locatedCatalogue.stories).toHaveLength(2);
    expect(paths.slice(-2)).toEqual(["/v1/landmarks", "/v1/stories?latitude=-26.2&longitude=28"]);
    await expect(loadMapCatalogue(async () => { throw new Error("catalogue unavailable"); })).rejects.toThrow("catalogue unavailable");
  });
  it("keeps search, landmark selection, story selection and show-all transitions consistent", () => {
    const searched = discoveryReducer(initialDiscoveryState, { type: "query-changed", query: "river" });
    const selectedPlace = discoveryReducer(searched, { type: "landmark-selected", landmarkId: "hill", storyId: "2" });
    expect(selectedPlace).toEqual({ query: "", landmarkId: "hill", language: "", selectedStoryId: "2" });
    expect(visibleStories(records, selectedPlace).map((story) => story.id)).toEqual(["2"]);
    expect(discoveryReducer(selectedPlace, { type: "story-closed" }).selectedStoryId).toBeNull();
    expect(discoveryReducer(selectedPlace, { type: "show-all" })).toEqual(initialDiscoveryState);
  });
  it("builds landmark pins and a closed optional-location accuracy ring", () => {
    const features = landmarkFeatures([{ id: "hill", name: "Hill", region: "Gauteng", latitude: -26.2, longitude: 28, distance_m: null }]);
    expect(features.features[0].geometry.coordinates).toEqual([28, -26.2]);
    expect(features.features[0].properties).toEqual({ id: "hill", name: "Hill" });
    const accuracy = accuracyFeatures({ latitude: -26.2, longitude: 28, accuracy: 45 }).features[0].geometry.coordinates[0];
    expect(accuracy).toHaveLength(65);
    expect(accuracy[0]).toEqual(accuracy[64]);
  });
  it("does not attach a media source before an explicit play action", () => {
    const playable = { ...records[0], media_url: "/asante/api/v1/stories/story-demo/media", transcript: "An original demo narration.", is_demo: true };
    const html = renderToStaticMarkup(createElement(StoryPlayer, { story: playable, lowData: true }));
    expect(html).toContain("Play story");
    expect(html).toContain("synthetic demo");
    expect(html).not.toContain("<audio");
    expect(html).not.toContain('src="/asante/api/');
    expect(renderToStaticMarkup(createElement(StoryPlayer, { story: records[0], lowData: true }))).toContain("has not been attached");
  });
  it("places processed published media in the contributor archive flow", () => {
    const story: Story = { ...records[0], id: "story-demo", title: "A place to begin — audio demo", media_url: "/asante/api/v1/stories/story-demo/media", transcript: "An original demo narration.", is_demo: true };
    const profile = { name: "Demo contributor", email: "demo@asante.test", bio: "", language: "en" };
    const html = renderToStaticMarkup(createElement(ContributorChat, {
      account: { id: "account-demo", email: profile.email, role: "contributor", profileId: "profile-demo" },
      profile,
      profileDraft: profile,
      onProfileDraftChange: () => undefined,
      projects: [],
      project: null,
      publishedStories: [story],
      publishedId: story.id,
      media: null,
      busy: false,
      message: "",
      onDismissMessage: () => undefined,
      activeWorker: null,
      uploadProgress: null,
      isUploading: false,
      isDirty: false,
      legacyCount: 0,
      storageConsent: false,
      onStorageConsentChange: () => undefined,
      liveLocation: false,
      onLiveLocationChange: () => undefined,
      onImportBrowserData: () => undefined,
      onSelectProject: () => undefined,
      onSelectPublished: () => undefined,
      onClearSelection: () => true,
      onSaveProject: async (project) => project,
      onSavePlanDocument: async () => undefined,
      onUpdate: () => undefined,
      onRunResearch: async () => undefined,
      onUploadFile: async () => true,
      onCancelUpload: () => undefined,
      onSubmit: async () => true,
      onSaveProfile: async () => true,
      onSignOut: () => undefined,
    }));
    expect(html).toContain("Published recording · processed media");
    expect(html).toContain("Play story");
    expect(html).toContain("Choose captions after pressing Play");
  });
  it("combines search with language and searches attribution and place", () => {
    expect(filterStories(records, " NOMSA ", "zu").map((item) => item.id)).toEqual(["1"]);
    expect(filterStories(records, "hill", "en").map((item) => item.id)).toEqual(["2"]);
    expect(filterStories(records, "river", "en")).toEqual([]);
    expect(filterStories(records, "", "")).toHaveLength(2);
  });
  it("rejects empty, unsupported and oversized files before preparation", () => {
    expect(mediaError({ size: 20, type: "video/mp4" })).toBeNull();
    expect(mediaError({ size: 0, type: "audio/mpeg" })).toContain("empty");
    expect(mediaError({ size: 1024, type: "application/pdf" })).toContain("Choose");
    expect(mediaError({ size: 100 * 1024 * 1024 + 1, type: "audio/mpeg" })).toContain("100 MB");
    expect(mediaError({ size: 500 * 1024 * 1024, type: "video/mp4" })).toBeNull();
    expect(mediaError({ size: 500 * 1024 * 1024 + 1, type: "video/mp4" })).toContain("500 MB");
  });
  it("posts typed planning input to the proxy and surfaces failure", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce({ ok: true, json: async () => ({ project_id: "project_1" }) }).mockResolvedValueOnce({ ok: false, status: 422 });
    vi.stubGlobal("fetch", fetchMock);
    expect(await api("/v1/story-projects/plan", { topic: "River" })).toEqual({ project_id: "project_1" });
    expect(fetchMock.mock.calls[0][0]).toBe("/asante/api/v1/story-projects/plan");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ topic: "River" });
    await expect(api("/v1/submissions", {})).rejects.toThrow("consent");
  });
});
