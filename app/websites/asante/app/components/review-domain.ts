export type Finding = { check: string; status: "pass" | "attention" | "blocked"; detail: string };
export type Submission = {
  submission_id: string;
  title: string;
  contributor_name: string;
  language: string;
  media_format: string;
  latitude: number;
  longitude: number;
  status: string;
  trace_id: string;
  summary: string;
  claim: string;
  source_url: string;
  media_name: string;
  media_checksum: string;
  media_size: number;
  consent_given: boolean;
  contributor_id?: string;
  contributor_profile_url?: string;
  created_at: string;
  findings: Finding[];
  decisions: { action: string; reason: string; at: string }[];
  version?: number;
  media_url?: string | null;
};

export function canApprove(item: Pick<Submission, "status" | "findings">): boolean {
  return !["approved", "rejected"].includes(item.status) && item.findings.length > 0 && !item.findings.some((finding) => finding.status === "blocked");
}

export function filterQueue(items: Submission[], query: string, status: string): Submission[] {
  const term = query.trim().toLowerCase();
  return items.filter((item) => (!status || item.status === status) && [item.title, item.contributor_name, item.language].join(" ").toLowerCase().includes(term));
}
