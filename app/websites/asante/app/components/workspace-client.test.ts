import { afterEach, expect, it, vi } from "vitest";
import { migrateBrowserStorage } from "./workspace-client";

function memoryStorage(initial: Record<string, string>): Storage {
  const items = new Map(Object.entries(initial));
  return { get length() { return items.size; }, key: (index) => Array.from(items.keys())[index] ?? null, getItem: (key) => items.get(key) ?? null, setItem: (key, value) => { items.set(key, value); }, removeItem: (key) => { items.delete(key); }, clear: () => items.clear() };
}
afterEach(() => vi.unstubAllGlobals());
const profile = { name: "Contributor", email: "test@example.test", bio: "", language: "en" };
const saved = { profile, projects: [], preferences: {} };

it("clears only captured Asante values after database readback and verified MinIO backup", async () => {
  const local = memoryStorage({ "asante.profile.v1": JSON.stringify(profile), "other-app": "keep me" });
  const session = memoryStorage({ "asante.guide.v2": "done", "unrelated": "keep too" });
  const responses = [{ ...saved, importChecksum: "abc" }, { ...saved, profile: { language: "en", bio: "", email: profile.email, name: profile.name } }, { verified: true, checksum: "abc" }];
  vi.stubGlobal("fetch", vi.fn(async () => {
    expect(local.getItem("asante.profile.v1")).not.toBeNull();
    return { ok: true, json: async () => responses.shift() };
  }));
  await migrateBrowserStorage(local, session);
  expect(local.getItem("asante.profile.v1")).toBeNull();
  expect(session.getItem("asante.guide.v2")).toBeNull();
  expect(local.getItem("other-app")).toBe("keep me");
  expect(session.getItem("unrelated")).toBe("keep too");
});

it("retains browser drafts when a save or MinIO verification fails", async () => {
  for (const failAt of [0, 2]) {
    const local = memoryStorage({ "asante.profile.v1": JSON.stringify(profile) });
    let calls = 0;
    vi.stubGlobal("fetch", vi.fn(async () => {
      const index = calls++;
      return { ok: index !== failAt, status: 503, json: async () => index === 0 ? { ...saved, importChecksum: "abc" } : saved };
    }));
    await expect(migrateBrowserStorage(local, memoryStorage({}))).rejects.toThrow();
    expect(local.getItem("asante.profile.v1")).toBe(JSON.stringify(profile));
  }
});

it("retains new browser changes made during import", async () => {
  const local = memoryStorage({ "asante.profile.v1": JSON.stringify(profile) });
  const responses = [{ ...saved, importChecksum: "abc" }, saved, { verified: true, checksum: "abc" }];
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, json: async () => { const response = responses.shift(); if (!responses.length) local.setItem("asante.profile.v1", "new edits"); return response; } })));
  await expect(migrateBrowserStorage(local, memoryStorage({}))).rejects.toThrow("changed during import");
  expect(local.getItem("asante.profile.v1")).toBe("new edits");
});
