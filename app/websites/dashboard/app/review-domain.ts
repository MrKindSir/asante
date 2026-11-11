export type Finding = { check: string; status: "pass" | "attention" | "blocked"; detail: string };
export type ProcessingJob = {
  jobId: string;
  jobType: string;
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  progress: number;
  safeError: string;
  result: { summary?: string };
};
export type Submission = {
  submission_id: string; title: string; contributor_name: string; language: string; media_format: string; revision_id?: string; revision_version?: number; consent_scope?: string; consent_recorded_at?: string; submission_consent_recorded_at?: string;
  latitude: number; longitude: number; status: string; trace_id: string; summary: string; claim: string;
  source_url: string; media_name: string; media_checksum: string; media_size: number; consent_given: boolean;
  contributor_id?: string; contributor_profile_url?: string; created_at: string; findings: Finding[]; decisions: { action: string; reason: string; at: string }[]; version?: number; media_url?: string | null;
  transcriptDraft?: { status: string; text: string; language?: string; segments?: { start: number; end: number; text: string }[]; backend: string; note?: string };
  captionTracks?: { language: string; label: string; cues: { start: number; end: number; text: string }[] }[];
  translations?: Record<string, { status: string; text: string; backend?: string; note?: string }>;
  videoAnalysis?: { status: string; observations: { timestamp?: number | string; observation: string }[]; frame_count: number; backend: string; note?: string };
  jobs?: ProcessingJob[];
  plan?: Record<string, unknown> | null;
  plan_document?: { title?: string; summary?: string; sections?: Array<{ id?: string; title?: string; content?: string; body?: string; bullets?: string[] }> } | null;
  research?: { sources?: Array<{ sourceId?: string; id?: string; title?: string; url?: string; excerpt?: string; snippet?: string; content?: string; retrievalState?: string; status?: string }> } | null;
  worker_runs?: Array<{ runId: string; traceId: string; workerType: string; status: string; providerModel?: string }>;
  assessment?: { status?: string; schemaVersion?: string; promptVersion?: string; provider?: string; model?: string; inputHash?: string; provenance?: { checks?: Array<{ check: string; status: string; detail: string }> }; claimEvidence?: { status?: string; claims?: Array<{ claimId: string; text: string; type: string; status: string; sourceIds: string[]; excerpts: Array<{ sourceId: string; text: string }>; rationale: string; uncertainty?: string }>; uncertainties?: string[] }; uncertainties?: string[]; safeError?: string };
  review_policy?: { version: string; may_approve: boolean; status: string };
};
export function canApprove(item: Pick<Submission, "status" | "findings" | "review_policy">): boolean {
  return !["approved", "rejected"].includes(item.status) && item.review_policy?.may_approve === true && item.findings.length > 0 && !item.findings.some((finding) => finding.status === "blocked");
}
export function filterQueue(items: Submission[], query: string, status: string): Submission[] {
  const term = query.trim().toLowerCase();
  return items.filter((item) => (!status || item.status === status) && [item.title, item.contributor_name, item.language].join(" ").toLowerCase().includes(term));
}
