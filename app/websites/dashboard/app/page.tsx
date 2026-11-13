"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { canApprove, filterQueue, ProcessingJob, Submission } from "./review-domain";
import { alternateAsanteRoute, isDirectAsanteRoute } from "./route-mode";
import ReviewVideoPlayer from "./ReviewVideoPlayer";
import ReviewGuide from "./ReviewGuide";
import { readReviewGuide, reviewGuideKey, reviewGuideSteps } from "./review-guide-domain";

const languages: Record<string, string> = { en: "English", zu: "isiZulu", st: "Sesotho" };
const directPort = process.env.NEXT_PUBLIC_ASANTE_DIRECT_PORT || "8082";
function mutationHeaders(contentType = false): Record<string, string> {
  const headers: Record<string, string> = { "X-Asante-Request": "1" };
  if (contentType) headers["Content-Type"] = "application/json";
  if (typeof document !== "undefined") {
    const cookie = document.cookie.split(";").map((part) => part.trim()).find((part) => part.startsWith("asante_csrf="));
    if (cookie) headers["X-Asante-CSRF"] = decodeURIComponent(cookie.slice("asante_csrf=".length));
  }
  return headers;
}
const workerLabels: Record<string, string> = { assessment: "Evidence comparison worker", hls: "HLS 1080p worker", transcribe: "Transcription worker", translate: "Translation worker", analyze: "Scene analysis worker" };
const workerInputSummaries: Record<string, string> = {
  assessment: "Story title, description and claim, location, English transcript or translation draft, optional submitted PDF text, and scene observations when available. Contributor research is excluded.",
  hls: "Verified original video. Converts a HubTweak-style 1080p HLS package into private media storage without overwriting the original.",
  transcribe: "Verified original recording or prepared speech track. Speech recognition is bounded to the first 180 seconds.",
  translate: "Timed transcript segments from the transcription worker, with their timestamps and source language.",
  analyze: "Verified video and up to four extracted keyframes. The worker is asked to describe visible scene cues only.",
};
type PublishedVideo = { id: string; title: string; contributor_name: string; language: string; media_format: string; landmark: string; status: string };
export default function DashboardPage() {
  const loadGeneration = useRef(0);
  const [reviewerEmail, setReviewerEmail] = useState("");
  const [connected, setConnected] = useState(false);
  const [items, setItems] = useState<Submission[]>([]);
  const [publishedVideos, setPublishedVideos] = useState<PublishedVideo[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [queueCollapsed, setQueueCollapsed] = useState(false);
  const [statusModalOpen, setStatusModalOpen] = useState(false);
  const [workerTrailJobId, setWorkerTrailJobId] = useState("");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [reason, setReason] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [playingId, setPlayingId] = useState("");
  const [section, setSection] = useState("Dashboard");
  const [directRoute, setDirectRoute] = useState(false);
  const [reviewGuideStep, setReviewGuideStep] = useState<number | null>(null);
  const selected = items.find((item) => item.submission_id === selectedId);
  const workerTrailJob = selected?.jobs?.find((job) => job.jobId === workerTrailJobId);
  const assessmentJobsPending = Boolean(selected?.jobs?.some((job) => ["assessment", "hls", "transcribe", "translate", "analyze"].includes(job.jobType) && ["queued", "running"].includes(job.status)));
  function moveReviewGuide(next: number) {
    const step = next >= reviewGuideSteps.length ? null : Math.max(0, next);
    setReviewGuideStep(step);
    window.localStorage.setItem(reviewGuideKey, JSON.stringify({ version: 1, step: step ?? reviewGuideSteps.length }));
  }
  function replayReviewGuide() {
    setReviewGuideStep(0);
    window.localStorage.setItem(reviewGuideKey, JSON.stringify({ version: 1, step: 0 }));
  }
  async function load(event?: FormEvent) {
    event?.preventDefault(); const generation = ++loadGeneration.current; setBusy(true); setMessage("");
    try {
      const access = await fetch("/asante/api/v1/review/session", { method: "POST", credentials: "include", headers: mutationHeaders() });
      if (generation !== loadGeneration.current) return;
      if (!access.ok) {
        setConnected(false); setItems([]); setSelectedId(""); setPlayingId("");
        if (access.status === 403) {
          const identity = await fetch("/asante/api/v1/auth/me", { cache: "no-store", credentials: "include" });
          if (identity.ok) {
            const account = await identity.json() as { role?: string };
            if (account.role === "contributor") {
              window.location.replace("/asante/portal/");
              return;
            }
          }
        }
        if (access.status === 401 || access.status === 403) {
          window.location.replace("/asante/portal/");
          return;
        }
        throw new Error("The Asante review desk is unavailable. Return to the portal and try again.");
      }
      setReviewerEmail((await access.json() as { email: string }).email);
      const repaired = await fetch("/asante/api/v1/review/queue/ensure-jobs", { method: "POST", credentials: "include", headers: mutationHeaders() });
      if (!repaired.ok) throw new Error("Could not prepare pending review jobs. Refresh the queue to retry.");
      const response = await fetch("/asante/api/v1/review/queue", { cache: "no-store", credentials: "include" });
      if (!response.ok) throw new Error(response.status === 403 ? "An Asante reviewer account is required." : "The Asante review queue is unavailable.");
      const body = await response.json() as { items: Submission[] };
      if (generation !== loadGeneration.current) return;
      setItems(body.items); setConnected(true);
      const requestedId = new URL(window.location.href).searchParams.get("submission");
      const preferred = body.items.find((item) => item.submission_id === requestedId)
        || body.items.find((item) => item.submission_id === selectedId)
        || body.items[0];
      setSelectedId(preferred?.submission_id || "");
      if (requestedId && preferred?.submission_id === requestedId) setSection("Review queue");
      const nextUrl = new URL(window.location.href);
      if (preferred && (requestedId || section === "Review queue")) nextUrl.searchParams.set("submission", preferred.submission_id);
      else if (!requestedId) nextUrl.searchParams.delete("submission");
      window.history.replaceState(null, "", nextUrl);
      try {
        const catalogueResponse = await fetch("/asante/api/v1/stories", { cache: "no-store" });
        if (catalogueResponse.ok) {
          const catalogue = await catalogueResponse.json() as { items?: PublishedVideo[] };
          if (generation === loadGeneration.current) setPublishedVideos((catalogue.items || []).filter((story) => story.status === "published" && story.media_format === "video"));
        } else if (generation === loadGeneration.current) setPublishedVideos([]);
      } catch {
        if (generation === loadGeneration.current) setPublishedVideos([]);
      }
    } catch (cause) { if (generation === loadGeneration.current) setMessage((cause as Error).message); } finally { if (generation === loadGeneration.current) setBusy(false); }
  }
  useEffect(() => {
    setDirectRoute(isDirectAsanteRoute(window.location.href, directPort));
    setReviewGuideStep(readReviewGuide(window.localStorage.getItem(reviewGuideKey)));
    void load();
    const refresh = () => { void load(); };
    window.addEventListener("focus", refresh);
    return () => window.removeEventListener("focus", refresh);
  }, []);
  useEffect(() => {
    if (!assessmentJobsPending) return;
    let cancelled = false;
    const timer = window.setInterval(async () => {
      try {
        const response = await fetch("/asante/api/v1/review/queue", { cache: "no-store" });
        if (!response.ok || cancelled) return;
        const body = await response.json() as { items: Submission[] };
        if (!cancelled) setItems(body.items);
      } catch {
        // The reviewer can still use Refresh queue if the background poll fails.
      }
    }, 3000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [selectedId, assessmentJobsPending]);
  useEffect(() => {
    if (!statusModalOpen && !workerTrailJobId) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setStatusModalOpen(false);
      if (event.key === "Escape") setWorkerTrailJobId("");
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [statusModalOpen, workerTrailJobId]);
  useEffect(() => {
    if (!connected) return;
    const targets: Array<[string, string]> = [
      [".review-details > .surface", "review-packet"],
      [".review-details .video-drafts", "review-media-drafts"],
      [".review-details .decision-panel", "review-decision"],
    ];
    targets.forEach(([selector, name]) => document.querySelector<HTMLElement>(selector)?.setAttribute("data-guide", name));
  }, [connected, selectedId, section, items]);
  async function logout() {
    ++loadGeneration.current;
    setBusy(true);
    try {
      const response = await fetch("/asante/api/v1/auth/logout", { method: "POST", credentials: "include", headers: mutationHeaders() });
      if (!response.ok) throw new Error("Could not sign out. Retry.");
      setConnected(false); setItems([]); setPublishedVideos([]); setSelectedId(""); setPlayingId(""); setReason(""); setMessage("");
    } catch (cause) { setMessage((cause as Error).message); }
    finally { setBusy(false); }
  }
  function switchRoute() {
    window.location.assign(alternateAsanteRoute(window.location.href, directPort));
  }
  function selectSubmission(submissionId: string) {
    setSelectedId(submissionId);
    setWorkerTrailJobId("");
    setSection("Review queue");
    setReason("");
    const nextUrl = new URL(window.location.href);
    nextUrl.searchParams.set("submission", submissionId);
    window.history.replaceState(null, "", nextUrl);
  }
  const reviewGuide = reviewGuideStep !== null ? <ReviewGuide
    steps={reviewGuideSteps}
    step={reviewGuideStep}
    onMove={moveReviewGuide}
    canAdvance={reviewGuideStep === 0 ? connected : reviewGuideStep === 2 ? Boolean(selected) : reviewGuideStep === 3 ? Boolean(selected && (selected.transcriptDraft || Object.keys(selected.translations || {}).length > 0)) : Boolean(selected)}
    onAction={(current) => { if (current === 1) setSection("Review queue"); }}
  /> : null;
  const routeControl = <>{<button type="button" className="quiet" onClick={switchRoute}>{directRoute ? "Use clean presentation URL" : "Use direct port URL"}</button>}{reviewGuide}</>;
  const showWorkerTrail = (jobType: string) => {
    const job = selected?.jobs?.find((item) => item.jobType === jobType);
    if (job) setWorkerTrailJobId(job.jobId);
  };
  const workerTrailButton = (jobType: string) => {
    const available = Boolean(selected?.jobs?.some((job) => job.jobType === jobType));
    return <button type="button" className="button secondary worker-trail-trigger" disabled={!available} onClick={() => showWorkerTrail(jobType)}>{available ? "View worker trail" : "Worker not queued"}</button>;
  };
  const workerName = (job: ProcessingJob) => workerLabels[job.jobType] || `${job.jobType} worker`;
  const workerInputs = (job: ProcessingJob) => workerInputSummaries[job.jobType] || "No input summary is available.";
  async function decide(action: string) {
    if (!selected || reason.trim().length < 10) return;
    setBusy(true); setMessage("");
    try {
      const response = await fetch("/asante/api/v1/review/" + selected.submission_id + "/decision", { method: "POST", credentials: "include", headers: mutationHeaders(true), body: JSON.stringify({ action, reason, expected_version: selected.version }) });
      if (!response.ok) throw new Error(response.status === 409 ? "This decision is blocked. Refresh the queue and check the guideline findings." : "Could not save the reviewer decision.");
      const next = await response.json() as Submission;
      setItems(items.map((item) => item.submission_id === next.submission_id ? next : item)); setReason(""); setMessage(action === "approve" ? `Approved and published “${next.title}” to the public map.` : "Reviewer decision recorded: " + next.status.replaceAll("_", " ") + ".");
    } catch (cause) { setMessage((cause as Error).message); } finally { setBusy(false); }
  }
  if (!connected) return <main className="account-page"><a className="brand" href="/asante/"><span className="brand-mark">a</span>asante review</a><div className="account-grid"><section><p className="eyebrow">Human decisions matter</p><h1>Listen closely.<br />Review with care.</h1><p>Reviewers sign in through the Asante portal, then return here to make human decisions.</p><a className="button primary" href="/asante/portal/">Open Asante portal →</a><p className="feedback" role="status">{message}</p></section></div></main>;

  return <main className="workspace"><aside className="workspace-sidebar"><div className="review-sidebar-brand"><a className="brand" href="/asante/"><span className="brand-mark">a</span>asante</a><span className="reviewer-email" title={reviewerEmail}>{reviewerEmail}</span></div><p className="sidebar-caption">Human review workspace</p>{routeControl}<button type="button" className="quiet" data-guide="review-guide-replay" onClick={replayReviewGuide}>Replay review guide</button><nav>{["Dashboard", "Review queue", "Decision history"].map((name) => <button key={name} data-guide={name === "Review queue" ? "review-queue-nav" : undefined} className={section === name ? "active" : ""} onClick={() => { setSection(name); const nextUrl = new URL(window.location.href); if (name === "Review queue" && selectedId) nextUrl.searchParams.set("submission", selectedId); else nextUrl.searchParams.delete("submission"); window.history.replaceState(null, "", nextUrl); }}>{name}</button>)}</nav><div className="sidebar-bottom"><button className="quiet" disabled={busy} onClick={() => void logout()}>Sign out</button></div></aside><section className="workspace-main"><header className="workspace-header"><div><p className="eyebrow">Evidence informs. People decide.</p><h1>{section === "Review queue" ? "Stories waiting to be heard." : section}</h1></div><button disabled={busy} className="button secondary" onClick={() => void load()}>{busy ? "Refreshing…" : "↻ Refresh dashboard"}</button></header><p className="prototype-note">Submitted packets are frozen to a saved revision. Assessments support human review; no worker decides authenticity or publishes stories.</p><p role="status" className="feedback">{message}</p><div className="metric-row"><div><strong>{items.filter((item) => item.status === "pending_review").length}</strong><span>Awaiting review</span></div><div><strong>{publishedVideos.length}</strong><span>Published videos</span></div><div><strong>{items.reduce((count, item) => count + item.decisions.length, 0)}</strong><span>Human decisions</span></div></div>
    {section === "Dashboard" && <div className="review-dashboard-grid"><section className="surface"><p className="eyebrow">Review workload</p><h2>Current queue</h2><p>{items.filter((item) => item.status === "pending_review").length} submission(s) are waiting for a decision.</p><button className="button primary" onClick={() => setSection("Review queue")}>Open review queue</button></section><section className="surface"><p className="eyebrow">Published catalogue</p><h2>{publishedVideos.length} public videos</h2>{publishedVideos.slice(0, 5).map((video) => <div className="audit-entry" key={video.id}><strong>{video.title}</strong><small>{video.landmark} · {video.contributor_name}</small></div>)}{publishedVideos.length > 5 && <button className="quiet" onClick={() => setSection("Decision history")}>See all published videos</button>}</section><section className="surface"><p className="eyebrow">Recent submissions</p><h2>Latest activity</h2>{items.slice(0, 5).map((item) => <button type="button" className="dashboard-submission" key={item.submission_id} onClick={() => { selectSubmission(item.submission_id); setSection("Review queue"); }}><span className="badge">{item.status.replaceAll("_", " ")}</span><strong>{item.title}</strong><small>{item.contributor_name} · {item.media_format}</small></button>)}{!items.length && <p>No submissions yet.</p>}</section></div>}
    {section === "Review queue" && <div className={"review-grid" + (queueCollapsed ? " queue-collapsed" : "")}><section className="queue-list" aria-label="Review submissions"><div className="queue-list-heading"><h2>{queueCollapsed ? "Queue" : "Submissions"}</h2><button type="button" className="icon-button" aria-label={queueCollapsed ? "Expand submission sidebar" : "Collapse submission sidebar"} aria-expanded={!queueCollapsed} onClick={() => setQueueCollapsed((value) => !value)}>{queueCollapsed ? "›" : "‹"}</button></div>{!queueCollapsed && <><label>Find a submission<input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Title, contributor, language…" /></label><button type="button" className="button secondary status-filter" onClick={() => setStatusModalOpen(true)}>Status: {status ? status.replaceAll("_", " ") : "All statuses"}⌄</button></>}{filterQueue(items, query, status).map((item) => <button className={"queue-item " + (selectedId === item.submission_id ? "active" : "")} key={item.submission_id} title={item.title} onClick={() => selectSubmission(item.submission_id)}><span className="badge">{item.status.replaceAll("_", " ")}</span><strong>{item.title}</strong><small>{item.contributor_name} · {languages[item.language]} · {item.media_format}</small></button>)}{!filterQueue(items, query, status).length && !queueCollapsed && <div className="surface"><h3>No submissions to show.</h3><p>Send a story packet from the contributor portal, then refresh this queue.</p></div>}{statusModalOpen && <div className="status-modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setStatusModalOpen(false); }}><div className="status-modal" role="dialog" aria-modal="true" aria-labelledby="status-modal-title"><button type="button" className="quiet status-modal-close" aria-label="Close status filter" onClick={() => setStatusModalOpen(false)}>×</button><p className="eyebrow">Queue filter</p><h2 id="status-modal-title">Choose submission status</h2>{["", "pending_review", "changes_requested", "escalated", "rejected", "approved"].map((value) => <button type="button" className={"status-option" + (status === value ? " active" : "")} key={value || "all"} onClick={() => { setStatus(value); setStatusModalOpen(false); }}>{value ? value.replaceAll("_", " ") : "All statuses"}{status === value && <span aria-hidden="true">✓</span>}</button>)}</div></div>}</section>
    {selected && <article className="review-details"><section className="surface"><p className="eyebrow">{selected.submission_id} · frozen revision {selected.revision_version || "unknown"}</p><h2>{selected.title}</h2><div className="tag-row"><span>{selected.contributor_profile_url ? <a href={selected.contributor_profile_url}>{selected.contributor_name}</a> : selected.contributor_name}</span><span>{languages[selected.language]} · original</span><span>{selected.media_format}</span></div><h3>Contributor's original narrative</h3><blockquote>{selected.summary || "The contributor has not supplied a narrative."}</blockquote><details><summary>Media & location</summary><p>{selected.media_name || "No original media attached"} · {selected.media_size} bytes</p><p>Original media stored and verified by Asante.</p>{selected.media_url && (playingId !== selected.submission_id ? <button className="button secondary" onClick={() => setPlayingId(selected.submission_id)}>Play original recording</button> : selected.media_format === "video" ? <ReviewVideoPlayer key={selected.submission_id} source={selected.media_url} tracks={selected.captionTracks || []} /> : <ReviewVideoPlayer key={selected.submission_id} source={selected.media_url} tracks={selected.captionTracks || []} format="audio" />)}<p>Location: {selected.place || `${selected.latitude}, ${selected.longitude}`}</p><code>{selected.media_checksum || "Checksum not supplied"}</code>{selected.supporting_document_url && <p><a className="button secondary" href={selected.supporting_document_url} target="_blank" rel="noopener noreferrer">Open supporting PDF ↗</a></p>}</details><details open><summary>Submitted claim</summary><p>{selected.claim || "No claim supplied. Review the contributor narrative and attached evidence."}</p>{selected.source_url && <p><a style={{ color: "var(--blue)" }} href={selected.source_url} target="_blank" rel="noopener noreferrer">Open contributor source ↗</a></p>}</details><details><summary>Authorship & consent</summary><p>Requested credit: <strong>{selected.contributor_name}</strong></p><p>Contributor consent: {selected.consent_given ? `recorded for ${selected.consent_scope || "submission review"}` : "missing"}</p><p>Original language preserved: {languages[selected.language]}</p><p>Submitted: {new Date(selected.created_at).toLocaleString()}</p></details></section>
    <details className="surface"><summary>Evidence comparison · {selected.assessment?.status || selected.jobs?.find((job) => job.jobType === "assessment")?.status || "waiting"}</summary><div className="worker-trail-actions">{workerTrailButton("assessment")}</div><p className="eyebrow">Asante assessment · {selected.assessment?.schemaVersion || "submission evidence v2"}</p><p className="muted">Decision support only; this is not independent fact-checking or an authenticity verdict. Review workers use story details, available English transcript, submitted PDF text and scene observations. Contributor research stays private.</p>{selected.assessment?.status ? <><p><span className="badge">{selected.assessment.status}</span> {selected.assessment.provider || "Provider unavailable"} · {selected.assessment.model || "model unavailable"} · prompt {selected.assessment.promptVersion || "version unavailable"}</p>{selected.assessment.safeError && <p role="status">{selected.assessment.safeError} Review the submitted story evidence and use your judgment.</p>}{selected.assessment.claimEvidence?.summary && <p>{selected.assessment.claimEvidence.summary}</p>}{(selected.assessment.claimEvidence?.evidence || []).map((evidence) => <span className="badge" key={evidence.evidenceId}>{evidence.label}</span>)}{(selected.assessment.claimEvidence?.claims || []).map((claim) => <div className="finding" key={claim.claimId}><strong>{claim.type.replaceAll("_", " ")} · {claim.status.replaceAll("_", " ")}</strong><blockquote>{claim.text}</blockquote><p>{claim.rationale}</p>{claim.uncertainty && <p className="muted">Uncertainty: {claim.uncertainty}</p>}{(claim.evidenceReferences || []).map((reference, index) => { const evidence = selected.assessment?.claimEvidence?.evidence?.find((item) => item.evidenceId === reference.evidenceId); return <blockquote key={`${reference.evidenceId}-${index}`}>“{reference.excerpt}” <small>{evidence?.label || "Submitted evidence"}</small></blockquote>; })}</div>)}<details><summary>Provenance and readiness</summary>{(selected.assessment.provenance?.checks || []).map((check) => <div className="finding" key={check.check}><strong>{check.check.replaceAll("_", " ")}</strong><span className="badge">{check.status}</span><p>{check.detail}</p></div>)}<p>Input SHA-256: <code>{selected.assessment.inputHash || "not recorded"}</code></p></details></> : <p role="status">Assessment {selected.jobs?.find((job) => job.jobType === "assessment")?.status || "not queued"}{selected.jobs?.find((job) => job.jobType === "assessment")?.progress ? ` · ${selected.jobs.find((job) => job.jobType === "assessment")?.progress}%` : ""}. The worker will wait for transcription, translation and scene analysis to finish.</p>}</details>
    {(selected.media_format === "video" || selected.media_format === "audio") && <details className="surface video-drafts"><summary>{selected.media_format === "video" ? "Video processing" : "Audio processing"}<span> · media drafts</span></summary><div className="worker-trail-actions">{workerTrailButton("hls")}{workerTrailButton("transcribe")}{workerTrailButton("translate")}{workerTrailButton("analyze")}</div><p className="eyebrow">Background media jobs · human review drafts</p><p className="muted">The original media is preserved. Transcription and scene observations are unreviewed drafts; scene observations are not heritage proof.</p><div className="video-job-list">{(selected.jobs || []).filter((job) => ["assessment", "hls", "transcribe", "translate", "analyze"].includes(job.jobType)).map((job) => <p key={job.jobId}><strong>{{assessment: "Evidence assessment", hls: "HLS 1080p", transcribe: "Transcription", translate: "Translation", analyze: "Video analysis"}[job.jobType] || job.jobType}</strong><span>{job.status.replaceAll("_", " ")}{job.status === "running" ? ` · ${job.progress}%` : ""}</span>{job.safeError && <small>{job.safeError}</small>}</p>)}</div>
      <section className="video-draft-block"><div className="worker-trail-subheading"><h3>Transcript draft · requires human review</h3>{workerTrailButton("transcribe")}</div>{selected.transcriptDraft ? <><span className="badge">{selected.transcriptDraft.status} · {selected.transcriptDraft.backend}</span>{selected.transcriptDraft.text ? <blockquote>{selected.transcriptDraft.text}</blockquote> : <p className="muted">{selected.transcriptDraft.note || "No transcript text is available."}</p>}{!!selected.transcriptDraft.segments?.length && <ol className="transcript-segments">{selected.transcriptDraft.segments.map((segment, index) => <li key={`${segment.start}-${index}`}><time>{segment.start.toFixed(1)}s–{segment.end.toFixed(1)}s</time> {segment.text}</li>)}</ol>}{selected.transcriptDraft.note && <small>{selected.transcriptDraft.note}</small>}</> : selected.jobs?.some((job) => job.jobType === "transcribe" && job.status === "failed") ? <p className="muted">Transcription is unavailable after job retries. The original story words remain unchanged.</p> : <p className="muted">Waiting for local Whisper transcription…</p>}</section>
      <section className="video-draft-block"><div className="worker-trail-subheading"><h3>Timed translation drafts</h3>{workerTrailButton("translate")}</div>{Object.entries(selected.translations || {}).map(([language, draft]) => <div key={language}><strong>{languages[language] || language} · {draft.status} · {draft.backend || "provider unavailable"}</strong>{draft.text ? <p>{draft.text}</p> : <p className="muted">{draft.note || "Translation unavailable"}</p>}</div>)}{!Object.keys(selected.translations || {}).length && <p className="muted">Waiting for timed transcript and translation processing.</p>}</section>
      {selected.media_format === "video" && <section className="video-draft-block"><div className="worker-trail-subheading"><h3>Scene observations · requires human review</h3>{workerTrailButton("analyze")}</div>{selected.videoAnalysis ? <><span className="badge">{selected.videoAnalysis.status} · {selected.videoAnalysis.backend} · {selected.videoAnalysis.frame_count} keyframes</span>{selected.videoAnalysis.observations.length ? <ul>{selected.videoAnalysis.observations.map((item, index) => <li key={`${item.timestamp}-${index}`}>{item.timestamp !== undefined ? <time>{typeof item.timestamp === "number" ? `${item.timestamp.toFixed(1)}s` : item.timestamp} · </time> : null}{item.observation}</li>)}</ul> : <p className="muted">{selected.videoAnalysis.note || "No scene observations are available."}</p>}{selected.videoAnalysis.note && <small>{selected.videoAnalysis.note}</small>}</> : selected.jobs?.some((job) => job.jobType === "analyze" && job.status === "failed") ? <p className="muted">Video analysis is unavailable after job retries. No scene result was fabricated.</p> : <p className="muted">Waiting for video analysis…</p>}</section>}
    </details>}
    <details className="surface"><summary>Guideline findings · {selected.findings.length}</summary><p className="eyebrow">Asante submission guideline · v1</p>{selected.findings.map((finding) => <div className={"finding " + finding.status} key={finding.check}><strong>{finding.check}</strong><span className="badge">{finding.status}</span><p>{finding.detail}</p></div>)}</details>
    <details className="surface decision-panel"><summary>Decision and reason</summary><p className="eyebrow">Human review gate · {selected.review_policy?.version || "policy pending"}</p><label>Decision reason<textarea minLength={10} maxLength={2000} value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Explain what is ready or what the contributor needs to change." /></label><p className="muted">Approval follows the server policy and remains a human decision. Assessment concerns require judgment; pending or unavailable required assessments can be escalated.</p><div className="action-row"><button disabled={busy || reason.trim().length < 10 || !canApprove(selected)} className="button primary" onClick={() => void decide("approve")}>Approve</button>{["request_changes", "escalate", "reject"].map((action) => <button disabled={busy || reason.trim().length < 10 || ["approved", "rejected"].includes(selected.status)} className="button secondary" key={action} onClick={() => void decide(action)}>{action.replaceAll("_", " ")}</button>)}</div></details>
    <details className="surface"><summary>Map publishing · {selected.published_story_id ? "published" : selected.status}</summary><h3>{selected.title}</h3><p>By {selected.contributor_name} · {languages[selected.language]} · {selected.media_format}</p>{selected.published_story_id ? <><span className="badge">Published on the public map</span>{selected.published_at && <p className="muted">Published {new Date(selected.published_at).toLocaleString()}</p>}</> : <span className="badge">{selected.status === "approved" ? "Approved · publication not recorded" : "Not published · awaiting human approval"}</span>}</details></article>}</div>}
    {selected && workerTrailJob && <div className="worker-trail-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setWorkerTrailJobId(""); }}><section className="worker-trail-modal" role="dialog" aria-modal="true" aria-labelledby="worker-trail-title"><button type="button" className="quiet status-modal-close" aria-label="Close worker trail" onClick={() => setWorkerTrailJobId("")}>×</button><p className="eyebrow">Asante worker record</p><h2 id="worker-trail-title">{workerName(workerTrailJob)}</h2><p><span className="badge">{workerTrailJob.status.replaceAll("_", " ")}{workerTrailJob.status === "running" ? ` · ${workerTrailJob.progress}%` : ""}</span> · attempt {workerTrailJob.attempt || 1}{workerTrailJob.jobType === "assessment" ? ` · ${selected.assessment?.provider || "provider unavailable"} · ${selected.assessment?.model || "model unavailable"}` : workerTrailJob.jobType === "translate" ? ` · ${Object.values(selected.translations || {}).map((draft) => draft.backend).filter(Boolean).join(", ") || "provider not recorded"}` : workerTrailJob.jobType === "analyze" ? ` · ${selected.videoAnalysis?.backend || "provider not recorded"}` : ` · ${selected.transcriptDraft?.backend || "local worker"}`}</p><p className="muted">This trail shows recorded worker actions and outputs, not private internal reasoning. Contributor research, source URLs, raw PDF contents, and provider prompts are not shown.</p><section className="worker-trail-block"><h3>Task and allowed inputs</h3><p>{workerInputs(workerTrailJob)}</p></section><section className="worker-trail-block"><h3>Recorded activity</h3>{workerTrailJob.workerTrail?.length ? <ol className="worker-trail-events">{workerTrailJob.workerTrail.map((event, index) => <li key={`${event.at}-${index}`}><time>{new Date(event.at).toLocaleString()}</time><strong>{event.label}</strong><span className="badge">{event.state.replaceAll("_", " ")}</span><p>{event.detail}</p></li>)}</ol> : <><p className="muted">This run predates detailed activity capture. These are the lifecycle timestamps that were saved:</p><ol className="worker-trail-events">{workerTrailJob.createdAt && <li><time>{new Date(workerTrailJob.createdAt).toLocaleString()}</time><strong>Job queued</strong><span className="badge">queued</span><p>The review job was added to Asante’s durable worker queue.</p></li>}{workerTrailJob.startedAt && <li><time>{new Date(workerTrailJob.startedAt).toLocaleString()}</time><strong>Worker started</strong><span className="badge">attempt {workerTrailJob.attempt || 1}</span><p>{workerName(workerTrailJob)} began processing.</p></li>}{workerTrailJob.finishedAt && <li><time>{new Date(workerTrailJob.finishedAt).toLocaleString()}</time><strong>Job finished</strong><span className="badge">{workerTrailJob.status}</span><p>{workerTrailJob.safeError || workerTrailJob.result.summary || "The recorded job reached a terminal state."}</p></li>}</ol></>}</section><section className="worker-trail-block"><h3>Saved output</h3>{workerTrailJob.safeError && <p role="status">{workerTrailJob.safeError}</p>}{workerTrailJob.result.summary && <p>{workerTrailJob.result.summary}</p>}{workerTrailJob.jobType === "assessment" && <>{selected.assessment?.claimEvidence?.summary && <p>{selected.assessment.claimEvidence.summary}</p>}{(selected.assessment?.claimEvidence?.claims || []).map((claim) => <div className="worker-trail-output" key={claim.claimId}><strong>{claim.type.replaceAll("_", " ")} · {claim.status.replaceAll("_", " ")}</strong><p>{claim.rationale}</p>{claim.uncertainty && <small>Uncertainty: {claim.uncertainty}</small>}</div>)}</>}{workerTrailJob.jobType === "transcribe" && <p>{selected.transcriptDraft?.text ? `${selected.transcriptDraft.text.slice(0, 1600)}${selected.transcriptDraft.text.length > 1600 ? "…" : ""}` : selected.transcriptDraft?.note || "No transcript output was saved."}</p>}{workerTrailJob.jobType === "translate" && Object.entries(selected.translations || {}).map(([language, draft]) => <div className="worker-trail-output" key={language}><strong>{languages[language] || language} · {draft.status} · {draft.backend || "provider unavailable"}</strong><p>{draft.text ? `${draft.text.slice(0, 900)}${draft.text.length > 900 ? "…" : ""}` : draft.note || "No translation output was saved."}</p></div>)}{workerTrailJob.jobType === "analyze" && (selected.videoAnalysis?.observations || []).map((observation, index) => <p className="worker-trail-output" key={`${observation.timestamp}-${index}`}>{observation.timestamp !== undefined ? `${observation.timestamp} · ` : ""}{observation.observation}</p>)}<p className="muted">Worker output is draft decision support. A human reviewer remains responsible for interpretation and publication.</p></section></section></div>}
    {section === "Decision history" && <><details className="surface" open><summary>Published videos · {publishedVideos.length}</summary>{publishedVideos.map((story) => {
      const submission = items.find((item) => item.published_story_id === story.id || item.published_slug === story.id);
      const approval = submission?.decisions.find((decision) => decision.action === "approve");
      return <div className="audit-entry" key={story.id}><strong>{story.title} · published</strong><p>{story.contributor_name} · {languages[story.language] || story.language} · {story.landmark}</p>{approval ? <><small>Reviewer approved {new Date(approval.at).toLocaleString()}</small><p>{approval.reason}</p></> : <small>Published catalogue video; no linked reviewer decision record is available.</small>}</div>;
    })}{!publishedVideos.length && <p>No published videos are currently in the catalogue.</p>}</details><details className="surface"><summary>Recorded reviewer decisions</summary>{items.flatMap((item) => item.decisions.map((decision, index) => <div className="audit-entry" key={item.submission_id + index}><strong>{item.title} · {decision.action.replaceAll("_", " ")}</strong><p>{decision.reason}</p><small>{new Date(decision.at).toLocaleString()}</small></div>))}{!items.some((item) => item.decisions.length) && <p>No reviewer decisions recorded yet.</p>}</details></>}
    </section></main>;
}
