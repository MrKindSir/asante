"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { canApprove, filterQueue, Submission } from "./review-domain";
import { alternateAsanteRoute, isDirectAsanteRoute } from "./route-mode";
import ReviewVideoPlayer from "./ReviewVideoPlayer";

const languages: Record<string, string> = { en: "English", zu: "isiZulu", st: "Sesotho" };
const directPort = process.env.NEXT_PUBLIC_ASANTE_DIRECT_PORT || "8082";
export default function DashboardPage() {
  const loadGeneration = useRef(0);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [reviewerEmail, setReviewerEmail] = useState("");
  const [connected, setConnected] = useState(false);
  const [items, setItems] = useState<Submission[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [reason, setReason] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [playingId, setPlayingId] = useState("");
  const [section, setSection] = useState("Review queue");
  const [directRoute, setDirectRoute] = useState(false);
  const [workerRuns, setWorkerRuns] = useState<Array<{
    runId: string;
    traceId: string;
    projectId: string;
    workerType: string;
    status: string;
    providerModel?: string | null;
    createdAt: string;
    safeError?: string | null;
    result?: { summary?: string; searchQuery?: string; aiUsed?: boolean };
  }>>([]);
  const selected = items.find((item) => item.submission_id === selectedId);
  const assessmentJobsPending = Boolean(selected?.jobs?.some((job) => ["assessment", "transcribe", "analyze"].includes(job.jobType) && ["queued", "running"].includes(job.status)));
  async function load(event?: FormEvent) {
    event?.preventDefault(); const generation = ++loadGeneration.current; setBusy(true); setMessage("");
    try {
      const access = await fetch("/asante/api/v1/review/session", { method: "POST", headers: { "X-Asante-Request": "1" } });
      if (generation !== loadGeneration.current) return;
      if (!access.ok) {
        setConnected(false); setItems([]); setSelectedId(""); setPlayingId("");
        if (access.status === 403) {
          const identity = await fetch("/asante/api/v1/auth/me", { cache: "no-store" });
          if (identity.ok) {
            const account = await identity.json() as { role?: string };
            if (account.role === "contributor") {
              window.location.replace("/asante/portal/");
              return;
            }
          }
        }
        throw new Error(access.status === 403 ? "Sign in with an Asante reviewer account." : "Sign in to open the review dashboard.");
      }
      setReviewerEmail((await access.json() as { email: string }).email);
      const response = await fetch("/asante/api/v1/review/queue", { cache: "no-store" });
      if (!response.ok) throw new Error(response.status === 403 ? "An Asante reviewer account is required." : "The Asante review queue is unavailable.");
      const body = await response.json() as { items: Submission[] };
      if (generation !== loadGeneration.current) return;
      setItems(body.items); setConnected(true);
      setSelectedId((current) => body.items.some((item) => item.submission_id === current) ? current : body.items[0]?.submission_id || "");
      const runs = await fetch("/asante/api/v1/review/worker-runs", { cache: "no-store" });
      if (runs.ok) {
        const runBody = await runs.json() as { items: typeof workerRuns };
        if (generation === loadGeneration.current) setWorkerRuns(runBody.items);
      } else if (generation === loadGeneration.current) setWorkerRuns([]);
    } catch (cause) { if (generation === loadGeneration.current) setMessage((cause as Error).message); } finally { if (generation === loadGeneration.current) setBusy(false); }
  }
  useEffect(() => {
    setDirectRoute(isDirectAsanteRoute(window.location.href, directPort));
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
  async function login(event: FormEvent) {
    event.preventDefault(); setBusy(true); setMessage("");
    try {
      const response = await fetch("/asante/api/v1/auth/login", { method: "POST", headers: { "Content-Type": "application/json", "X-Asante-Request": "1" }, body: JSON.stringify({ email, password }) });
      if (!response.ok) { const body = await response.json() as { detail?: string }; throw new Error(typeof body.detail === "string" ? body.detail : "Could not sign in. Check your email and password."); }
      const account = await response.json() as { role?: string };
      setPassword("");
      if (account.role === "contributor") {
        setMessage("Opening your contributor portal…");
        window.location.assign("/asante/portal/");
        return;
      }
      if (account.role !== "reviewer") throw new Error("This Asante account does not have a supported workspace role.");
      await load();
    } catch (cause) { setMessage((cause as Error).message); }
    finally { setBusy(false); }
  }
  async function logout() {
    ++loadGeneration.current;
    setBusy(true);
    try {
      const response = await fetch("/asante/api/v1/auth/logout", { method: "POST", headers: { "X-Asante-Request": "1" } });
      if (!response.ok) throw new Error("Could not sign out. Retry.");
      setConnected(false); setPassword(""); setItems([]); setSelectedId(""); setPlayingId(""); setReason(""); setMessage("");
    } catch (cause) { setMessage((cause as Error).message); }
    finally { setBusy(false); }
  }
  function switchRoute() {
    window.location.assign(alternateAsanteRoute(window.location.href, directPort));
  }
  const routeControl = <button type="button" className="quiet" onClick={switchRoute}>{directRoute ? "Use clean presentation URL" : "Use direct port URL"}</button>;
  async function decide(action: string) {
    if (!selected || reason.trim().length < 10) return;
    setBusy(true); setMessage("");
    try {
      const response = await fetch("/asante/api/v1/review/" + selected.submission_id + "/decision", { method: "POST", headers: { "Content-Type": "application/json", "X-Asante-Request": "1" }, body: JSON.stringify({ action, reason, expected_version: selected.version }) });
      if (!response.ok) throw new Error(response.status === 409 ? "This decision is blocked. Refresh the queue and check the guideline findings." : "Could not save the reviewer decision.");
      const next = await response.json() as Submission;
      setItems(items.map((item) => item.submission_id === next.submission_id ? next : item)); setReason(""); setMessage("Reviewer decision recorded: " + next.status.replaceAll("_", " ") + ".");
    } catch (cause) { setMessage((cause as Error).message); } finally { setBusy(false); }
  }
  if (!connected) return <main className="account-page"><a className="brand" href="/asante/review/"><span className="brand-mark">a</span>asante review</a><div className="account-grid"><section><p className="eyebrow">Human decisions matter</p><h1>Listen closely.<br />Review with care.</h1><p>Compare the contributor's words with the evidence. Keep uncertainty visible and authorship intact.</p>{routeControl}</section><form className="surface" onSubmit={(event) => void login(event)}><p className="eyebrow">Asante account access</p><h2>Open your workspace</h2><label>Email<input type="email" required autoComplete="username" value={email} onChange={(event) => setEmail(event.target.value)} /></label><label>Password<input type="password" required minLength={12} maxLength={128} autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} /></label><p className="muted">Your account role opens the review dashboard or contributor portal.</p><button disabled={busy} className="button primary">{busy ? "Opening…" : "Continue →"}</button><p className="feedback" role="status">{message}</p></form></div></main>;

  return <main className="workspace"><aside className="workspace-sidebar"><a className="brand" href="/asante/review/"><span className="brand-mark">a</span>asante</a><p className="sidebar-caption">Human review workspace</p>{routeControl}<nav>{["Review queue", "Worker traces", "Decision history"].map((name) => <button key={name} className={section === name ? "active" : ""} onClick={() => setSection(name)}>{name}</button>)}</nav><div className="sidebar-bottom"><span className="avatar">HR</span><strong>{reviewerEmail}</strong><button className="quiet" disabled={busy} onClick={() => void logout()}>Sign out</button></div></aside><section className="workspace-main"><header className="workspace-header"><div><p className="eyebrow">Evidence informs. People decide.</p><h1>{section === "Review queue" ? "Stories waiting to be heard." : section}</h1></div><button disabled={busy} className="button secondary" onClick={() => void load()}>↻ Refresh queue</button></header><p className="prototype-note">Submitted packets are frozen to a saved revision. Assessments support human review; no worker decides authenticity or publishes stories.</p><p role="status" className="feedback">{message}</p><div className="metric-row"><div><strong>{items.filter((item) => item.status === "pending_review").length}</strong><span>Awaiting review</span></div><div><strong>{items.reduce((count, item) => count + item.findings.filter((finding) => finding.status === "blocked").length, 0)}</strong><span>Blocking findings</span></div><div><strong>{items.reduce((count, item) => count + item.decisions.length, 0)}</strong><span>Human decisions</span></div></div>
    {section === "Review queue" && <div className="review-grid"><section className="queue-list" aria-label="Review submissions"><label>Find a submission<input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Title, contributor, language…" /></label><select aria-label="Review status filter" value={status} onChange={(event) => setStatus(event.target.value)}><option value="">All statuses</option>{["pending_review", "changes_requested", "escalated", "rejected", "approved"].map((value) => <option key={value} value={value}>{value.replaceAll("_", " ")}</option>)}</select>{filterQueue(items, query, status).map((item) => <button className={"queue-item " + (selectedId === item.submission_id ? "active" : "")} key={item.submission_id} onClick={() => { setSelectedId(item.submission_id); setReason(""); }}><span className="badge">{item.status.replaceAll("_", " ")}</span><strong>{item.title}</strong><small>{item.contributor_name} · {languages[item.language]} · {item.media_format}</small></button>)}{!filterQueue(items, query, status).length && <div className="surface"><h3>No submissions to show.</h3><p>Send a story packet from the contributor portal, then refresh this queue.</p></div>}</section>
    {selected && <article className="review-details"><section className="surface"><p className="eyebrow">{selected.submission_id} · frozen revision {selected.revision_version || "unknown"}</p><h2>{selected.title}</h2><div className="tag-row"><span>{selected.contributor_profile_url ? <a href={selected.contributor_profile_url}>{selected.contributor_name}</a> : selected.contributor_name}</span><span>{languages[selected.language]} · original</span><span>{selected.media_format}</span></div><h3>Contributor's original narrative</h3><blockquote>{selected.summary || "The contributor has not supplied a narrative."}</blockquote>{selected.plan_document && <details open><summary>Frozen field report</summary><h3>{selected.plan_document.title || selected.title}</h3>{(selected.plan_document.sections || []).map((section, index) => <section key={`${section.title}-${index}`}><h4>{section.title}</h4>{section.body && <p>{section.body}</p>}{section.content && <p>{section.content}</p>}{section.bullets && <ul>{section.bullets.map((bullet, bulletIndex) => <li key={bulletIndex}>{bullet}</li>)}</ul>}</section>)}</details>}<details><summary>Media & location</summary><p>{selected.media_name || "No original media attached"} · {selected.media_size} bytes</p><p>Original media stored and verified by Asante.</p>{selected.media_url && (playingId !== selected.submission_id ? <button className="button secondary" onClick={() => setPlayingId(selected.submission_id)}>Play original recording</button> : selected.media_format === "video" ? <ReviewVideoPlayer key={selected.submission_id} source={selected.media_url} tracks={selected.captionTracks || []} /> : <ReviewVideoPlayer key={selected.submission_id} source={selected.media_url} tracks={selected.captionTracks || []} format="audio" />)}<p>Location: {selected.latitude}, {selected.longitude}</p><code>{selected.media_checksum || "Checksum not supplied"}</code></details><details open><summary>Claims & submitted sources</summary><p>{selected.claim || "No claim list supplied. Review assertions in the contributor narrative and report."}</p>{selected.source_url && <p><a style={{ color: "var(--blue)" }} href={selected.source_url} target="_blank" rel="noopener noreferrer">Open contributor source ↗</a></p>}{(selected.research?.sources || []).map((source, index) => <div className="finding" key={source.sourceId || source.url || index}><strong>{source.title || source.url || `Source ${index + 1}`}</strong><span className="badge">{source.retrievalState || source.status || "metadata_only"}</span><p>{source.excerpt || source.snippet || source.content || "No submitted excerpt; metadata only."}</p>{source.url && <a style={{ color: "var(--blue)" }} href={source.url} target="_blank" rel="noopener noreferrer">Open submitted source ↗</a>}</div>)}</details><details><summary>Authorship & consent</summary><p>Requested credit: <strong>{selected.contributor_name}</strong></p><p>Contributor consent: {selected.consent_given ? `recorded for ${selected.consent_scope || "submission review"}` : "missing"}</p><p>Original language preserved: {languages[selected.language]}</p><p>Submitted: {new Date(selected.created_at).toLocaleString()}</p></details></section>
    <section className="surface"><p className="eyebrow">Asante assessment · {selected.assessment?.schemaVersion || "waiting"}</p><h2>Evidence comparison</h2><p className="muted">Model interpretations are decision support. No authenticity verdict is produced.</p>{selected.assessment ? <><p><span className="badge">{selected.assessment.status || "unknown"}</span> {selected.assessment.provider} · {selected.assessment.model} · prompt {selected.assessment.promptVersion}</p>{selected.assessment.safeError && <p role="status">{selected.assessment.safeError} Escalate for human review.</p>}{(selected.assessment.claimEvidence?.claims || []).map((claim) => <div className="finding" key={claim.claimId}><strong>{claim.type.replaceAll("_", " ")} · {claim.status.replaceAll("_", " ")}</strong><blockquote>{claim.text}</blockquote><p>{claim.rationale}</p>{claim.uncertainty && <p className="muted">Uncertainty: {claim.uncertainty}</p>}{claim.excerpts.map((excerpt, index) => <blockquote key={`${excerpt.sourceId}-${index}`}>“{excerpt.text}” <small>Source {excerpt.sourceId}</small></blockquote>)}</div>)}<details><summary>Provenance and readiness</summary>{(selected.assessment.provenance?.checks || []).map((check) => <div className="finding" key={check.check}><strong>{check.check.replaceAll("_", " ")}</strong><span className="badge">{check.status}</span><p>{check.detail}</p></div>)}<p>Input SHA-256: <code>{selected.assessment.inputHash || "not recorded"}</code></p></details></> : <p role="status">{selected.jobs?.find((job) => job.jobType === "assessment")?.status || "Assessment not queued"}. Refresh while it runs; unavailable results require human escalation.</p>}</section>
    {(selected.media_format === "video" || selected.media_format === "audio") && <section className="surface video-drafts"><p className="eyebrow">Background media jobs · human review drafts</p><h2>{selected.media_format === "video" ? "Video processing" : "Audio processing"}</h2><p className="muted">The original media is preserved. Transcription and scene observations are unreviewed drafts; scene observations are not heritage proof.</p><div className="video-job-list">{(selected.jobs || []).filter((job) => ["assessment", "transcribe", "translate", "analyze"].includes(job.jobType)).map((job) => <p key={job.jobId}><strong>{{assessment: "Evidence assessment", transcribe: "Transcription", analyze: "Video analysis"}[job.jobType] || job.jobType}</strong><span>{job.status.replaceAll("_", " ")}{job.status === "running" ? ` · ${job.progress}%` : ""}</span>{job.safeError && <small>{job.safeError}</small>}</p>)}</div>
      <section className="video-draft-block"><h3>Transcript draft · requires human review</h3>{selected.transcriptDraft ? <><span className="badge">{selected.transcriptDraft.status} · {selected.transcriptDraft.backend}</span>{selected.transcriptDraft.text ? <blockquote>{selected.transcriptDraft.text}</blockquote> : <p className="muted">{selected.transcriptDraft.note || "No transcript text is available."}</p>}{!!selected.transcriptDraft.segments?.length && <ol className="transcript-segments">{selected.transcriptDraft.segments.map((segment, index) => <li key={`${segment.start}-${index}`}><time>{segment.start.toFixed(1)}s–{segment.end.toFixed(1)}s</time> {segment.text}</li>)}</ol>}{selected.transcriptDraft.note && <small>{selected.transcriptDraft.note}</small>}</> : selected.jobs?.some((job) => job.jobType === "transcribe" && job.status === "failed") ? <p className="muted">Transcription is unavailable after job retries. The original story words remain unchanged.</p> : <p className="muted">Waiting for local Whisper transcription…</p>}</section>
      <section className="video-draft-block"><h3>Timed translation drafts</h3>{Object.entries(selected.translations || {}).map(([language, draft]) => <div key={language}><strong>{languages[language] || language} · {draft.status} · {draft.backend || "provider unavailable"}</strong>{draft.text ? <p>{draft.text}</p> : <p className="muted">{draft.note || "Translation unavailable"}</p>}</div>)}{!Object.keys(selected.translations || {}).length && <p className="muted">Waiting for timed transcript and translation processing.</p>}</section>
      {selected.media_format === "video" && <section className="video-draft-block"><h3>Scene observations · requires human review</h3>{selected.videoAnalysis ? <><span className="badge">{selected.videoAnalysis.status} · {selected.videoAnalysis.backend} · {selected.videoAnalysis.frame_count} keyframes</span>{selected.videoAnalysis.observations.length ? <ul>{selected.videoAnalysis.observations.map((item, index) => <li key={`${item.timestamp}-${index}`}>{item.timestamp !== undefined ? <time>{typeof item.timestamp === "number" ? `${item.timestamp.toFixed(1)}s` : item.timestamp} · </time> : null}{item.observation}</li>)}</ul> : <p className="muted">{selected.videoAnalysis.note || "No scene observations are available."}</p>}{selected.videoAnalysis.note && <small>{selected.videoAnalysis.note}</small>}</> : selected.jobs?.some((job) => job.jobType === "analyze" && job.status === "failed") ? <p className="muted">Video analysis is unavailable after job retries. No scene result was fabricated.</p> : <p className="muted">Waiting for video analysis…</p>}</section>}
    </section>}
    <section className="surface"><p className="eyebrow">Asante submission guideline · v1</p><h2>What needs your judgement?</h2>{selected.findings.map((finding) => <div className={"finding " + finding.status} key={finding.check}><strong>{finding.check}</strong><span className="badge">{finding.status}</span><p>{finding.detail}</p></div>)}</section>
    <section className="surface decision-panel"><p className="eyebrow">Human review gate · {selected.review_policy?.version || "policy pending"}</p><h2>Your decision, with reasons.</h2><label>Decision reason<textarea minLength={10} maxLength={2000} value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Explain what is ready or what the contributor needs to change." /></label><p className="muted">Approval follows the server policy and remains a human decision. Assessment concerns require judgment; pending or unavailable required assessments block approval and can be escalated.</p><div className="action-row"><button disabled={busy || reason.trim().length < 10 || !canApprove(selected)} className="button primary" onClick={() => void decide("approve")}>Approve</button>{["request_changes", "escalate", "reject"].map((action) => <button disabled={busy || reason.trim().length < 10 || ["approved", "rejected"].includes(selected.status)} className="button secondary" key={action} onClick={() => void decide(action)}>{action.replaceAll("_", " ")}</button>)}</div></section>
    <section className="surface"><p className="eyebrow">Map publishing preview</p><h3>{selected.title}</h3><p>By {selected.contributor_name} · {languages[selected.language]} · {selected.media_format}</p><span className="badge">Not published · human approval required</span></section></article>}</div>}
    {section === "Worker traces" && <section className="surface"><h2>Asante worker runs</h2><p className="muted">Planner and researcher traces from contributor projects. Submission guideline checks remain deterministic at packet intake.</p>{workerRuns.map((run) => <div className="audit-entry" key={run.runId}><strong>{run.workerType} · {run.status}</strong><p><code>{run.traceId}</code> · project <code>{run.projectId}</code></p><small>{new Date(run.createdAt).toLocaleString()}{run.providerModel ? ` · ${run.providerModel}` : ""}{run.result?.summary ? ` · ${run.result.summary}` : ""}{run.safeError ? ` · ${run.safeError}` : ""}</small></div>)}{!workerRuns.length && items.map((item) => <div className="audit-entry" key={item.submission_id}><strong>{item.title}</strong><p><code>{item.trace_id}</code></p><small>Input: contributor packet · output: guideline findings · original language: {languages[item.language]}</small></div>)}{!workerRuns.length && !items.length && <p>No worker runs yet.</p>}</section>}
    {section === "Decision history" && <section className="surface"><h2>Human decision trail</h2>{items.flatMap((item) => item.decisions.map((decision, index) => <div className="audit-entry" key={item.submission_id + index}><strong>{item.title} · {decision.action.replaceAll("_", " ")}</strong><p>{decision.reason}</p><small>{new Date(decision.at).toLocaleString()}</small></div>))}{!items.some((item) => item.decisions.length) && <p>No decisions recorded yet.</p>}</section>}
    </section></main>;
}
