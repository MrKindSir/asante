import { api, mutationHeaders, Plan, ResearchPacket, Story } from "./story-domain";
import { FieldReportDocument } from "./plan-document";

export type Profile = { name: string; email: string; bio: string; language: string };
export type Media = { id: string; name: string; size: number; type: string; checksum: string; url: string };
export type WorkerActivity = { id: string; at: string; actor: string; kind: string; message: string; details: string[] };
export type WorkerRun = {
  runId: string; traceId: string; projectId: string; workerType: "planner" | "researcher";
  status: "running" | "succeeded" | "failed" | "cancelled"; providerModel?: string;
  createdAt: string; finishedAt?: string | null; safeError?: string | null; activity: WorkerActivity[];
  input?: { title?: string; place?: string; claim?: string; source?: string; researchBrief?: ResearchBrief; planQuestions?: string[]; projectVersion?: number; researchInputHash?: string };
  result?: { questions?: string[]; outline?: string[]; unknowns?: string[]; searchQuery?: string; focus?: string; notes?: string[]; sources?: ResearchPacket["sources"]; aiUsed?: boolean };
};
export type SaveProjectOptions = { background?: boolean };
export type ResearchBrief = { knownMaterial: string; questions: string; context: string; priorities: string; uncertainties: string };
export type ResearchFlow = { status: "incomplete" | "saved" | "running" | "planned" | "completed" | "failed"; workerType?: "planner" | "researcher"; inputHash: string; runId?: string; safeError?: string };
export type MediaJob = {
  jobId: string; projectId?: string; jobType: "hls" | "transcribe" | "translate" | "analyze" | string;
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled" | string;
  progress: number; safeError?: string; createdAt?: string | null; finishedAt?: string | null;
};
export type TranscriptDraft = {
  status?: string; text?: string; language?: string; backend?: string; note?: string;
  coveredSeconds?: number; segments?: { start: number; end: number; text: string }[];
};
export type TranslationDraft = { status?: string; text?: string; backend?: string; note?: string; providerModel?: string };
export type Project = {
  id: string; title: string; place: string; language: string; format: string; audience: string; transcript: string; claim: string; source: string; consent: boolean;
  researchBrief?: ResearchBrief | null; researchFlow?: ResearchFlow; plan?: Plan; planDocument?: FieldReportDocument | null; research?: ResearchPacket;
  suggestion: "pending" | "accepted" | "rejected"; submissionId?: string; uploadId?: string; supportingDocumentUploadId?: string; version: number;
  media?: Media | null; supportingDocument?: Media | null; status?: string;
  mediaJobs?: MediaJob[]; transcriptDraft?: TranscriptDraft | null; translations?: Record<string, TranslationDraft> | null;
  videoAnalysis?: { status?: string; observations?: { timestamp?: number; observation: string }[]; note?: string; backend?: string } | null;
};
export type Account = { id: string; email: string; role: "contributor" | "reviewer"; profileId: string };
export type Workspace = { account?: Account | null; profile: Profile | null; projects: Project[]; preferences: Record<string, string>; publishedStories?: Story[] };

function canonical(value: unknown): string {
  if (Array.isArray(value)) return "[" + value.map(canonical).join(",") + "]";
  if (value !== null && typeof value === "object") return "{" + Object.entries(value).sort(([a], [b]) => a.localeCompare(b)).map(([key, item]) => JSON.stringify(key) + ":" + canonical(item)).join(",") + "}";
  return JSON.stringify(value);
}

export function captureAsanteStorage(local: Storage, session: Storage): Record<string, string> {
  const snapshot: Record<string, string> = {};
  for (const [prefix, storage] of [["local", local], ["session", session]] as const) {
    for (let index = 0; index < storage.length; index++) {
      const key = storage.key(index);
      if (key?.startsWith("asante.")) snapshot[prefix + ":" + key] = storage.getItem(key) || "";
    }
  }
  return snapshot;
}

export async function migrateBrowserStorage(local: Storage, session: Storage): Promise<Workspace> {
  const snapshot = captureAsanteStorage(local, session);
  const entries = Object.entries(snapshot);
  if (!entries.length) return api<Workspace>("/v1/workspace");
  const profile: unknown = JSON.parse(snapshot["local:asante.profile.v1"] || "null");
  const projects: unknown = JSON.parse(snapshot["local:asante.projects.v1"] || "[]");
  if (!Array.isArray(projects)) throw new Error("Browser drafts could not be read. They have been retained.");
  const preferences = Object.fromEntries(entries.filter(([key]) => !key.endsWith("asante.profile.v1") && !key.endsWith("asante.projects.v1")).map(([key, value]) => [key.slice(key.indexOf(":") + 1), value]));
  const imported = await api<Workspace & { importChecksum: string }>("/v1/workspace/import", { profile, projects, preferences, browser_data: snapshot, consent: true });
  const stored = await api<Workspace>("/v1/workspace");
  if (canonical(stored.profile) !== canonical(imported.profile) || canonical(stored.projects) !== canonical(imported.projects)) throw new Error("The server copy changed. Browser data has been retained.");
  const receipt = await api<{ verified: boolean; checksum: string }>("/v1/workspace/import-receipt/" + imported.importChecksum);
  if (!receipt.verified || receipt.checksum !== imported.importChecksum) throw new Error("The browser backup could not be verified. Browser data has been retained.");
  // Delete only exact captured Asante values, after DB and MinIO verification.
  for (const [key, value] of entries) {
    const separator = key.indexOf(":");
    const storage = key.startsWith("local:") ? local : session;
    const name = key.slice(separator + 1);
    if (storage.getItem(name) !== value) throw new Error("Browser data changed during import. New changes have been retained.");
  }
  for (const [key] of entries) {
    const storage = key.startsWith("local:") ? local : session;
    storage.removeItem(key.slice(key.indexOf(":") + 1));
  }
  return stored;
}

let opening: Promise<Workspace> | null = null;
export function openWorkspace(): Promise<Workspace> {
  if (!opening) {
    opening = api<Workspace>("/v1/workspace/session", {}).finally(() => { opening = null; });
  }
  return opening;
}

export function savePreference(key: string, value: string | null): Promise<unknown> {
  return api("/v1/workspace/preferences", { key, value });
}

export function uploadFile(url: string, file: File, onProgress: (percent: number) => void, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    const abort = () => request.abort();
    signal.addEventListener("abort", abort, { once: true });
    request.open("PUT", url);
    for (const [name, value] of Object.entries(mutationHeaders(false))) request.setRequestHeader(name, value);
    request.setRequestHeader("Content-Type", file.type);
    request.upload.onprogress = (event) => { if (event.lengthComputable) onProgress(Math.round(event.loaded / event.total * 100)); };
    request.onload = () => { signal.removeEventListener("abort", abort); if (request.status >= 200 && request.status < 300) resolve(); else reject(new Error("Upload could not be verified. Check the file type, size, ten-minute limit and connection, then retry.")); };
    request.onerror = () => { signal.removeEventListener("abort", abort); reject(new Error("Upload connection failed. Retry when connected.")); };
    request.onabort = () => { signal.removeEventListener("abort", abort); reject(new Error("Upload cancelled. No media was marked ready.")); };
    if (signal.aborted) reject(new Error("Upload cancelled.")); else request.send(file);
  });
}
