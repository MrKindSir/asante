// @vitest-environment jsdom
import { act, createElement } from "react";
import { createRoot, Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import ContributorWorkspace from "./ContributorWorkspace";
import { Project, Workspace } from "./workspace-client";

const navigation = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn(), params: new URLSearchParams() }));
vi.mock("next/navigation", () => ({ useRouter: () => navigation, useSearchParams: () => navigation.params }));
vi.mock("./FieldReport", () => ({ default: () => <div>Existing field report editor</div> }));
let root: Root;
let container: HTMLDivElement;
let stored: Workspace;
let failSave: boolean;
let failWorker: boolean;
let saveGate: Promise<void> | null;
let workerGate: Promise<void> | null;
let history: Array<Record<string, unknown>>;
const requests: Array<{ path: string; body: Record<string, unknown> }> = [];
const profile = { name: "Nomsa", email: "fixture@example.test", bio: "", language: "en" };
const legacy: Project = { id: "old-draft", title: "Older oral history", place: "Soweto Towers", language: "en", format: "audio", audience: "Listeners", transcript: "", claim: "Who gathered?", source: "", consent: false, suggestion: "pending", version: 1 };
const answers = { knownMaterial: "Grandmother remembers", questions: "When did gatherings begin?", context: "1976, Soweto", priorities: "Compare names", uncertainties: "Exact dates" };
function button(text: string, within: ParentNode = container) {
  const found = [...within.querySelectorAll("button")].find((item) => item.textContent === text || item.getAttribute("aria-label") === text);
  if (!found) throw new Error(`Missing button: ${text}`);
  return found;
}
function input(label: string): HTMLInputElement | HTMLTextAreaElement {
  const found = [...container.querySelectorAll("label")].find((item) => item.textContent?.trimStart().startsWith(label))?.querySelector("input,textarea");
  if (!found) throw new Error(`Missing input: ${label}`);
  return found as HTMLInputElement;
}
async function click(text: string, within?: ParentNode) { await act(async () => { button(text, within).click(); }); }
async function fill(label: string, value: string) {
  await act(async () => {
    const field = input(label);
    const prototype = field.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(prototype, "value")!.set!.call(field, value);
    field.dispatchEvent(new Event("input", { bubbles: true }));
  });
}
async function openLegacy() {
  const item = [...container.querySelectorAll("button")].find((node) => node.querySelector("strong")?.textContent === legacy.title)!;
  await act(async () => item.click());
}
async function completeBrief() {
  await fill("Main story question", "When did people gather?");
  for (const [label, value] of [["What you already know", answers.knownMaterial], ["Questions the research", answers.questions], ["Relevant people", answers.context], ["Research priorities", answers.priorities], ["Uncertainties", answers.uncertainties]]) await fill(label, value);
}
beforeEach(async () => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  stored = { account: { id: "account-a", email: profile.email, profileId: "profile-a", role: "contributor" }, profile, projects: [structuredClone(legacy)], preferences: {} };
  requests.length = 0; failSave = false; failWorker = false; workerGate = null; saveGate = null; history = [];
  navigation.params = new URLSearchParams();
  vi.stubGlobal("fetch", vi.fn(async (url: string, options?: RequestInit) => {
    const path = String(url).replace("/asante/api", "");
    const body = JSON.parse(String(options?.body || "{}")) as Record<string, unknown>;
    requests.push({ path, body });
    const response = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
    if (path === "/v1/workspace/session" || path === "/v1/workspace") return response(structuredClone(stored));
    if (path === "/v1/workspace/projects") {
      if (saveGate) await saveGate;
      if (failSave) return response({ detail: "Fixture save failed" }, 409);
      const next = body as unknown as Project;
      const previous = stored.projects.find((item) => item.id === next.id);
      const saved: Project = { ...next, version: next.version + 1, status: "draft", researchFlow: next.researchBrief ? { status: "saved", inputHash: "brief-hash" } : undefined };
      if (previous && JSON.stringify(previous.researchBrief) === JSON.stringify(next.researchBrief)) saved.researchFlow = previous.researchFlow;
      stored.projects = [saved, ...stored.projects.filter((item) => item.id !== saved.id)];
      return response(saved);
    }
    if (path === "/v1/workspace/profile") { stored.profile = body as unknown as typeof profile; return response(stored.profile); }
    if (path.endsWith("/workers") && !options?.body) return response({ items: structuredClone(history) });
    if (path.endsWith("/workers")) {
      const run: Record<string, unknown> = { runId: `run-${history.length}`, traceId: "trace-fixture", projectId: path.split("/")[4], workerType: body.workerType, status: "running", createdAt: new Date().toISOString(), activity: [{ id: `event-${history.length}`, at: new Date().toISOString(), actor: "Asante coordinator", kind: "delegation", message: `Asante coordinator → ${body.workerType}: work assigned from saved revision ${body.expectedVersion}.`, details: [] }] };
      history.push(run);
      if (workerGate) await workerGate;
      const id = path.split("/")[4];
      const project = stored.projects.find((item) => item.id === id)!;
      if (body.expectedVersion !== project.version) return response({ detail: "Stale version" }, 409);
      if (failWorker) { run.status = "failed"; project.researchFlow = { status: "failed", inputHash: "brief-hash", safeError: "Fixture worker failed" }; return response({ detail: "Fixture worker failed" }, 502); }
      project.version += 1;
      if (body.workerType === "planner") {
        project.plan = { project_id: id, trace_id: "trace-fixture", worker_steps: [], human_gate: "Human review", researchInputHash: "brief-hash" } as Project["plan"];
        project.researchFlow = { status: "planned", inputHash: "brief-hash" };
      } else {
        project.research = { sources: [{ title: "Candidate archive", url: "https://example.com/archive" }] };
        project.planDocument = { title: project.title, subtitle: "Fixture report", landmark: project.place, summary: "Candidates", sections: [], charts: [], tables: [], images: [], sources: [], humanGate: "Human review" };
        project.researchFlow = { status: "completed", inputHash: "brief-hash" };
      }
      run.status = "succeeded"; run.result = { aiUsed: false, questions: ["Who attended?"], unknowns: ["Dates need review"] };
      return response({ ...project, status: "succeeded", projectVersion: project.version });
    }
    if (path.endsWith("plan-share")) return response({ share: null, collaborators: [] });
    throw new Error(`Unexpected request ${path}`);
  }));
  container = document.createElement("div"); document.body.append(container); root = createRoot(container);
  await act(async () => root.render(createElement(ContributorWorkspace)));
});
afterEach(async () => { vi.useRealTimers(); await act(async () => root.unmount()); container.remove(); vi.unstubAllGlobals(); });

it("retains Step 1 after failure, saves once on double click, then shows one Step 2 before results", async () => {
  await click("New story chat"); await fill("Story title", "River memories");
  failSave = true; await click("Save and open chat");
  expect(input("Story title").value).toBe("River memories");
  expect(container.querySelector('[data-testid="research-step"]')).toBeNull();
  failSave = false;
  await act(async () => { button("Save and open chat").click(); button("Save and open chat").click(); });
  expect(stored.projects.filter((item) => item.title === "River memories")).toHaveLength(1);
  expect(container.querySelectorAll('[data-testid="research-step"]')).toHaveLength(1);
  expect(container.querySelector('[role="dialog"]')).toBeNull();
  expect(requests.filter((item) => item.path.endsWith("/workers") && item.body.workerType)).toHaveLength(0);
  await click("Complete research brief");
  expect(input("Questions the research")).toBeTruthy();
  expect(requests.filter((item) => item.path.endsWith("/workers") && item.body.workerType)).toHaveLength(0);
});

it("preserves questionnaire on save failure; save-only survives remount and chat switching without workers", async () => {
  await openLegacy(); await click("Complete research brief"); await completeBrief();
  failSave = true; await click("Save and start research");
  expect(input("Questions the research").value).toBe(answers.questions);
  expect(requests.filter((item) => item.path.endsWith("/workers") && item.body.workerType)).toHaveLength(0);
  failSave = false; await click("Save brief");
  expect(stored.projects[0].researchBrief).toEqual(answers);
  expect(container.textContent).toContain("Brief saved. Research has not completed");
  await click("New story chat"); await openLegacy(); await click("Edit research brief");
  expect(input("Relevant people").value).toBe(answers.context);
  await act(async () => root.unmount()); root = createRoot(container);
  await act(async () => root.render(createElement(ContributorWorkspace)));
  await openLegacy(); await click("Edit research brief");
  expect(input("What you already know").value).toBe(answers.knownMaterial);
  expect(requests.filter((item) => item.path.endsWith("/workers") && item.body.workerType)).toHaveLength(0);
});

it("saves before workers, carries sequential server versions, and opens the report and sources", async () => {
  await openLegacy(); await click("Complete research brief"); await completeBrief(); await click("Save and start research");
  const workerRequests = requests.filter((item) => item.path.endsWith("/workers") && item.body.workerType);
  expect(workerRequests.map((item) => [item.body.workerType, item.body.expectedVersion])).toEqual([["planner", 2], ["researcher", 3]]);
  expect(stored.projects[0].researchBrief).toEqual(answers);
  await click("Open field report"); expect(container.textContent).toContain("Existing field report editor");
  await click("Close Asante field report"); await click("Open sources");
  expect(container.querySelector('[role="dialog"]')?.textContent).toContain("Candidate archive");
});

it("shows pending and failed states and explicit retry without losing the saved brief", async () => {
  await openLegacy(); await click("Complete research brief"); await completeBrief();
  let release!: () => void; workerGate = new Promise<void>((resolve) => { release = resolve; });
  await click("Save and start research");
  expect(container.textContent).toContain("Preparing the story plan");
  expect(container.querySelector('[role="dialog"]')).toBeNull();
  failWorker = true; await act(async () => release());
  expect(container.textContent).toContain("Research failed. Your saved brief is preserved");
  expect(stored.projects[0].researchBrief).toEqual(answers);
  workerGate = null; failWorker = false; await click("Retry research");
  expect(container.textContent).toContain("Research completed for this saved brief");
});

it("keeps late worker results out of another selected chat", async () => {
  await openLegacy(); await click("Complete research brief"); await completeBrief();
  let release!: () => void; workerGate = new Promise<void>((resolve) => { release = resolve; });
  await click("Save and start research");
  // Creating a new chat changes selection while the first worker is pending.
  await click("New story chat");
  await act(async () => release());
  expect(container.textContent).not.toContain("Research completed for this saved brief");
  expect(container.querySelector('[data-testid="research-step"]')).toBeNull();
});

it("restores an existing draft from its URL and keeps submitted projects read-only", async () => {
  await act(async () => root.unmount());
  stored.projects[0].submissionId = "submission-fixture";
  navigation.params = new URLSearchParams("project=old-draft"); root = createRoot(container);
  await act(async () => root.render(createElement(ContributorWorkspace)));
  expect(container.textContent).toContain("Submitted story chat");
  expect(container.querySelector('[data-testid="research-step"]')).toBeNull();
  expect(button("Edit story details").disabled).toBe(true);
  expect(requests.filter((item) => item.path.endsWith("/workers") && item.body.workerType)).toHaveLength(0);
});

it("ignores late results after the account changes", async () => {
  await openLegacy(); await click("Complete research brief"); await completeBrief();
  let release!: () => void; workerGate = new Promise<void>((resolve) => { release = resolve; });
  await click("Save and start research");
  stored = { account: { id: "account-b", profileId: "profile-b", email: "other@example.test", role: "contributor" }, profile: { ...profile, name: "Other contributor" }, projects: [], preferences: {} };
  await act(async () => { window.dispatchEvent(new Event("focus")); });
  await act(async () => release());
  expect(container.textContent).toContain("Other contributor");
  expect(container.textContent).not.toContain(legacy.title);
  expect(container.querySelector('[data-testid="research-step"]')).toBeNull();
  expect(requests.filter((item) => item.path.endsWith("/workers") && item.body.workerType)).toHaveLength(1);
});

it("blocks repeated starts and restores completed results without rerunning on reload", async () => {
  await openLegacy(); await click("Complete research brief"); await completeBrief(); await click("Save brief");
  await act(async () => { button("Start research").click(); button("Start research").click(); });
  expect(requests.filter((item) => item.path.endsWith("/workers") && item.body.workerType)).toHaveLength(2);
  await act(async () => root.unmount()); root = createRoot(container);
  await act(async () => root.render(createElement(ContributorWorkspace)));
  await openLegacy();
  expect(container.textContent).toContain("Research completed for this saved brief");
  expect(requests.filter((item) => item.path.endsWith("/workers") && item.body.workerType)).toHaveLength(2);
});


it("autosaves an incomplete brief without starting research and restores it on reopen", async () => {
  vi.useFakeTimers();
  await openLegacy(); await click("Complete research brief");
  await fill("What you already know", "An unfinished oral history note");
  await act(async () => { await vi.advanceTimersByTimeAsync(950); });
  expect(stored.projects[0].researchBrief?.knownMaterial).toBe("An unfinished oral history note");
  expect(stored.projects[0].researchBrief?.questions).toBe("");
  expect(requests.filter((item) => item.body.workerType)).toHaveLength(0);
  await click("Close 02 / Prepare your research brief");
  await click("Complete research brief");
  expect(input("What you already know").value).toBe("An unfinished oral history note");
});

it("autosaves new story details without closing the form or creating duplicate projects", async () => {
  vi.useFakeTimers(); await click("New story chat"); await fill("Story title", "Auto saved story");
  await act(async () => { await vi.advanceTimersByTimeAsync(950); });
  expect(stored.projects.filter((item) => item.title === "Auto saved story")).toHaveLength(1);
  expect(container.querySelector('[role="dialog"]')).toBeTruthy();
  await fill("Audience", "Neighbourhood listeners");
  await act(async () => { await vi.advanceTimersByTimeAsync(950); });
  expect(stored.projects.find((item) => item.title === "Auto saved story")?.audience).toBe("Neighbourhood listeners");
  await click("Save and open chat");
  expect(stored.projects.filter((item) => item.title === "Auto saved story")).toHaveLength(1);
});

it("queues edits made during autosave and preserves them after a failed save", async () => {
  vi.useFakeTimers(); await openLegacy(); await click("Complete research brief");
  let release!: () => void; saveGate = new Promise<void>((resolve) => { release = resolve; });
  await fill("Questions the research", "First draft question");
  await act(async () => { await vi.advanceTimersByTimeAsync(950); });
  await fill("Questions the research", "Newest question typed during the save");
  await act(async () => release()); saveGate = null;
  failSave = true;
  await act(async () => { await vi.advanceTimersByTimeAsync(950); });
  expect(input("Questions the research").value).toBe("Newest question typed during the save");
  expect(container.textContent).toContain("Save failed. Your edits remain here");
  failSave = false; await click("Retry autosave");
  expect(stored.projects[0].researchBrief?.questions).toBe("Newest question typed during the save");
  expect(requests.filter((item) => item.body.workerType)).toHaveLength(0);
});

it("shows recorded activity and opens the full activity popup without starting workers", async () => {
  history.push({ runId: "recorded-run", traceId: "recorded-trace", projectId: legacy.id, workerType: "researcher", status: "succeeded", createdAt: "2026-11-10T10:00:00Z", input: { projectVersion: 3, claim: "Who gathered?", planQuestions: ["Which families attended?"] }, result: { aiUsed: false, searchQuery: "Soweto community records", sources: [{ title: "Candidate archive", url: "https://example.com/archive" }] }, activity: [{ id: "handoff-record", at: "2026-11-10T10:00:00Z", actor: "Asante researcher", kind: "handoff", message: "Planner → Researcher: use these planning questions.", details: ["Which families attended?"] }] });
  await openLegacy();
  expect(container.textContent).toContain("Planner → Researcher");
  await click("View full research activity");
  expect(container.querySelector('[role="dialog"]')?.textContent).toContain("Soweto community records");
  expect(container.querySelector('[role="dialog"]')?.textContent).toContain("recorded-trace");
  await click("Close research activity");
  expect(requests.filter((item) => item.body.workerType)).toHaveLength(0);
});

it("autosaves story notes and only saves profile edits after storage consent", async () => {
  vi.useFakeTimers(); await openLegacy();
  await fill("Story question or notes", "Updated note for research");
  await act(async () => { await vi.advanceTimersByTimeAsync(950); });
  expect(stored.projects[0].claim).toBe("Updated note for research");
  const profileButton = container.querySelector<HTMLButtonElement>(".portal-profile-control")!;
  await act(async () => profileButton.click());
  await fill("Bio", "Contributor biography");
  await act(async () => { await vi.advanceTimersByTimeAsync(950); });
  expect(requests.filter((item) => item.path === "/v1/workspace/profile")).toHaveLength(0);
  const checkbox = input("Store these profile changes");
  await act(async () => checkbox.click());
  await act(async () => { await vi.advanceTimersByTimeAsync(950); });
  expect(stored.profile?.bio).toBe("Contributor biography");
});
