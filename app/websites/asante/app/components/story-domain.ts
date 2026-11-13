export type Landmark = { id: string; name: string; region: string; latitude: number; longitude: number; distance_m: number | null };
export type CaptionCue = { start: number; end: number; text: string };
export type CaptionTrack = { language: string; label: string; cues: CaptionCue[] };
export type Story = { contributor_id?: string | null; contributor_profile_url?: string | null; id: string; title: string; contributor_name: string; language: string; media_format: string; landmark_id: string; landmark: string; distance_m: number | null; status: string; latitude?: number; longitude?: number; region?: string; media_url?: string | null; poster_url?: string | null; transcript?: string; is_demo?: boolean };
export type Plan = {
  researchInputHash?: string;
  project_id: string;
  topic?: string;
  place_name?: string;
  trace_id: string;
  worker_steps: string[];
  human_gate: string;
  questions?: string[];
  outline?: string[];
  checklist?: string[];
  unknowns?: string[];
  aiUsed?: boolean;
};
export type ResearchSource = {
  title: string;
  url: string;
  excerpt?: string;
  collector?: string;
  status?: string;
  platform?: string;
  publisher?: string;
  retrievedAt?: string;
  contentHash?: string;
  retrievalState?: string;
};
export type ResearchPacket = {
  researchInputHash?: string;
  searchQuery?: string;
  focus?: string;
  summary?: string;
  sources?: ResearchSource[];
  notes?: string[];
  aiUsed?: boolean;
  retrievedAt?: string;
  images?: Array<{ url: string; caption: string; credit: string; sourceUrl?: string }>;
  report?: { summary?: string; findings?: Array<{ text?: string }>; openQuestions?: string[] };
};
export const languageNames: Record<string, string> = { en: "English", zu: "isiZulu", st: "Sesotho" };
export const guideSteps = [
  { title: "Every place has a story.", text: "Welcome to Asante. Explore voices and memories connected to landmarks. You can explore without sharing your location.", action: "Explore the map" },
  { title: "Get started here.", text: "Search for a place, story, or contributor. You can explore every published location, wherever you are.", action: "Next" },
  { title: "Want to know what is near you?", text: "Allow Live Location to add distances on the map. Sharing is optional and never locks other stories away. You can turn it off later in your portal profile.", action: "Allow Live Location" },
  { title: "Choose a story here.", text: "Select a story to see its place on the map. Open its details and press Play to listen, even if you are far away.", action: "Open this story" },
  { title: "Your voice belongs here.", text: "Use Login to open your contributor portal. Plan, research, and prepare a submission while keeping control of your credit.", action: "Keep exploring" }
];
export function readGuide(raw: string | null): number | null {
  try {
    const state: unknown = JSON.parse(raw || "null");
    if (typeof state === "object" && state !== null && "version" in state && state.version === 2 && "step" in state && typeof state.step === "number" && Number.isInteger(state.step) && state.step >= 0 && state.step <= 5) return state.step === 5 ? null : state.step;
  } catch { /* A damaged preference starts the guide again. */ }
  return 0;
}
export function filterStories(stories: Story[], query: string, language: string): Story[] {
  const term = query.trim().toLocaleLowerCase();
  return stories.filter((story) => (!language || story.language === language) && [story.title, story.landmark, story.region, story.contributor_name, languageNames[story.language]].join(" ").toLocaleLowerCase().includes(term));
}

export type TourRect = { left: number; top: number; right: number; bottom: number; width: number; height: number };
export function tourPosition(target: TourRect | null, viewport: { width: number; height: number }, size: { width: number; height: number }) {
  const gap = 14;
  const width = Math.min(size.width, viewport.width - gap * 2);
  const height = Math.min(size.height, viewport.height - gap * 2);
  const clamp = (value: number, max: number) => Math.max(gap, Math.min(value, max));
  if (!target) return { left: (viewport.width - width) / 2, top: (viewport.height - height) / 2 };
  const candidates = [
    { left: target.right + gap, top: target.top },
    { left: target.left, top: target.bottom + gap },
    { left: target.left - width - gap, top: target.top },
    { left: target.left, top: target.top - height - gap }
  ];
  const chosen = candidates.find((item) => item.left >= gap && item.left + width <= viewport.width - gap && item.top >= gap && item.top + height <= viewport.height - gap)
    || candidates.find((item) => item.top >= gap && item.top + height <= viewport.height - gap)
    || candidates[candidates.length - 1];
  return { left: clamp(chosen.left, viewport.width - width - gap), top: clamp(chosen.top, viewport.height - height - gap) };
}
export function mediaError(file: Pick<File, "size" | "type">): string | null {
  if (!["audio/mpeg", "audio/wav", "audio/x-wav", "audio/ogg", "video/mp4", "video/webm"].includes(file.type)) return "Choose MP3, WAV, OGG, MP4, or WebM media.";
  if (file.size <= 0) return "The media file is empty.";
  const limit = file.type.startsWith("video/") ? 500 * 1024 * 1024 : 100 * 1024 * 1024;
  if (file.size > limit) return file.type.startsWith("video/") ? "Choose a video no larger than 500 MB for this prototype." : "Choose audio smaller than 100 MB for this prototype.";
  return null;
}
export function supportingDocumentError(file: Pick<File, "size" | "type">): string | null {
  if (file.type !== "application/pdf") return "Choose a PDF supporting document.";
  if (file.size <= 0) return "The PDF is empty.";
  if (file.size > 25 * 1024 * 1024) return "Choose a PDF no larger than 25 MB.";
  return null;
}
export class AsanteApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}
export function asanteCsrfToken(): string {
  if (typeof document === "undefined") return "";
  const match = document.cookie.split(";").map((part) => part.trim()).find((part) => part.startsWith("asante_csrf="));
  return match ? decodeURIComponent(match.slice("asante_csrf=".length)) : "";
}
export function mutationHeaders(contentType = true): Record<string, string> {
  const headers: Record<string, string> = { "X-Asante-Request": "1" };
  if (contentType) headers["Content-Type"] = "application/json";
  const token = asanteCsrfToken();
  if (token) headers["X-Asante-CSRF"] = token;
  return headers;
}
export async function api<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(
    "/asante/api" + path,
    body === undefined
      ? { cache: "no-store", credentials: "include" }
      : { method: "POST", credentials: "include", headers: mutationHeaders(), body: JSON.stringify(body) },
  );
  if (!response.ok) {
    let detail: unknown;
    try { detail = (await response.json() as { detail?: unknown }).detail; } catch { /* Use the safe fallback below. */ }
    throw new AsanteApiError(response.status, typeof detail === "string" ? detail : response.status === 422 ? "Check the required fields, language, format, and consent." : "Asante could not complete this request. Please try again.");
  }
  return response.json() as Promise<T>;
}
