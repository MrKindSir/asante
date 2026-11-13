"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "./story-domain";
import { Project, WorkerActivity, WorkerRun } from "./workspace-client";

function recordedEvents(run: WorkerRun): WorkerActivity[] {
  if (run.activity?.length) return run.activity;
  return [{ id: run.runId, at: run.finishedAt || run.createdAt, actor: `Asante ${run.workerType}`, kind: run.status,
    message: `Earlier run ${run.status}. Detailed steps were not recorded for this run.`, details: run.safeError ? [run.safeError] : [] }];
}

export default function ResearchActivity({
  project,
  accountId,
  openRequest = 0,
  closeRequest = 0,
}: {
  project: Project;
  accountId: string;
  openRequest?: number;
  closeRequest?: number;
}) {
  const [runs, setRuns] = useState<WorkerRun[]>([]);
  const [error, setError] = useState("");
  const [open, setOpen] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const opener = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLElement>(null);
  const preview = useRef<HTMLOListElement>(null);
  const liveTrail = useRef<HTMLOListElement>(null);
  const content = useRef<HTMLDivElement>(null);
  const dialog = useRef<HTMLElement>(null);
  const running = project.researchFlow?.status === "running" || runs.some((run) => run.status === "running");
  const activeLabel = project.researchFlow?.workerType || runs.find((run) => run.status === "running")?.workerType || "worker";
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    async function read() {
      try {
        const saved = await api<{ items: WorkerRun[] }>(`/v1/workspace/projects/${encodeURIComponent(project.id)}/workers`);
        if (cancelled) return;
        setRuns([...saved.items].sort((a, b) => a.createdAt.localeCompare(b.createdAt)));
        setError("");
        if (project.researchFlow?.status === "running" || saved.items.some((run) => run.status === "running")) timer = setTimeout(() => void read(), 1200);
      } catch {
        if (!cancelled) { setError("Research activity could not refresh. Your saved story is unchanged."); timer = setTimeout(() => void read(), 5000); }
      }
    }
    void read();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [project.id, project.version, project.researchFlow?.status, accountId, refresh]);
  useEffect(() => {
    if (openRequest > 0) setOpen(true);
  }, [openRequest]);
  useEffect(() => {
    if (closeRequest > 0) setOpen(false);
  }, [closeRequest]);
  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    dialog.current?.querySelector<HTMLButtonElement>("button")?.focus();
    const keyboard = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
      if (event.key === "Tab") {
        const controls = dialog.current?.querySelectorAll<HTMLElement>('button,a[href],summary,[tabindex="0"]');
        if (!controls?.length) return;
        const first = controls[0], last = controls[controls.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    };
    document.addEventListener("keydown", keyboard);
    return () => { document.removeEventListener("keydown", keyboard); previous?.focus(); };
  }, [open]);
  const events = runs.flatMap(recordedEvents);
  useEffect(() => {
    if (project.researchFlow?.status === "running") panel.current?.scrollIntoView?.({ behavior: "smooth", block: "nearest" });
  }, [project.researchFlow?.status]);
  useEffect(() => {
    if (!running) return;
    const timer = window.setTimeout(() => {
      if (preview.current) preview.current.scrollTop = preview.current.scrollHeight;
      if (open && liveTrail.current) liveTrail.current.scrollTop = liveTrail.current.scrollHeight;
      if (open && content.current) content.current.scrollTop = content.current.scrollHeight;
    }, 0);
    return () => window.clearTimeout(timer);
  }, [events.length, open, running, runs.length]);
  const handoff = [...events].reverse().find((event) => event.kind === "handoff");
  const recent = handoff ? [handoff, ...events.slice(-3).filter((event) => event.id !== handoff.id)] : events.slice(-4);
  if (!runs.length && project.researchFlow?.status !== "running" && !error) return null;
  return <>
    <div className="chat-row asante"><span className="chat-avatar asante" aria-hidden="true">↗</span><article ref={panel} className="chat-bubble asante portal-result-bubble research-activity-bubble">
      <p className="chat-label">Asante research activity{running ? " · live" : project.researchFlow?.status === "completed" ? " · finished" : ""}</p>
      <p className="muted">{running
        ? `The ${activeLabel} is still working on the server. Open the activity modal to watch recorded steps while you wait.`
        : project.researchFlow?.status === "completed"
          ? "Research finished. The recorded worker trail below is complete for this brief."
          : "Follow the recorded worker handoffs and research steps."}</p>
      {running && <p role="status"><span className="badge">running · {activeLabel}</span> Status refreshes automatically even if the browser request timed out.</p>}
      {!running && project.researchFlow?.status === "completed" && <p role="status"><span className="badge">completed</span> Research finished for this saved brief.</p>}
      <ol ref={preview} className="research-activity-preview" aria-label="Recent research activity" aria-live="polite">
        {recent.map((event) => <li key={event.id}><strong>{event.actor}</strong><p>{event.message}</p></li>)}
      </ol>
      {!events.length && <p role="status">Waiting for the first recorded worker step…</p>}
      {error && <p role="status">{error}</p>}
      <button ref={opener} type="button" className={running ? "button primary" : "button secondary"} onClick={() => setOpen(true)}>
        {running ? "Watch live research activity" : "View full research activity"}
      </button>
    </article></div>
    {open && <div className="modal-backdrop portal-modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setOpen(false); }}>
      <section ref={dialog} className="surface portal-popup wide" role="dialog" aria-modal="true" aria-label="Research activity">
        <header className="portal-popup-bar"><div><p className="eyebrow">Asante worker record</p><h2>{running ? "Live research activity" : project.researchFlow?.status === "completed" ? "Research finished" : "Research activity"}</h2></div><button type="button" className="plan-results-close" aria-label="Close research activity" onClick={() => setOpen(false)}>×</button></header>
        <div ref={content} className="portal-popup-content">
          <p>{running
            ? "This modal keeps polling the saved worker trail while the planner or researcher runs on the server. You can leave it open after a connection interrupt. The chat will also announce when research finishes."
            : project.researchFlow?.status === "completed"
              ? "Research finished for this saved brief. Sources remain candidates for human interpretation."
              : "Recorded assignments, methods, handoffs and outputs. Sources remain candidates for human interpretation."}</p>
          {running && <p role="status"><span className="badge">running · {activeLabel}</span> New steps appear here as they are recorded.</p>}
          {!running && project.researchFlow?.status === "completed" && <p role="status"><span className="badge">completed</span> Research finished. You can close this modal and review the plan and sources in the chat.</p>}
          {error && <p role="alert">{error}<button type="button" className="quiet" onClick={() => setRefresh((value) => value + 1)}>Retry activity refresh</button></p>}
          {runs.map((run) => <section className="research-run" key={run.runId}>
            <h3>Asante {run.workerType} · {run.status}</h3>
            <p className="muted">Saved revision {run.input?.projectVersion ?? "not recorded"} · {run.result?.aiUsed === false ? "Fixture / deterministic output" : run.providerModel || "Provider not recorded"}</p>
            <details><summary>Saved brief and handoff received</summary><p>{run.input?.claim || "Earlier input details are unavailable."}</p>{run.input?.researchBrief && <dl>{Object.entries(run.input.researchBrief).map(([key, value]) => <div key={key}><dt>{({ knownMaterial: "Known material", questions: "Research questions", context: "Cultural context", priorities: "Priorities", uncertainties: "Uncertainties" } as Record<string, string>)[key] || key}</dt><dd>{value || "Not supplied"}</dd></div>)}</dl>}{!!run.input?.planQuestions?.length && <><strong>Planning questions handed to researcher</strong><ul>{run.input.planQuestions.map((question, index) => <li key={index}>{question}</li>)}</ul></>}</details>
            <ol ref={run.status === "running" ? liveTrail : undefined} className="research-activity-events" aria-live={run.status === "running" ? "polite" : undefined}>{recordedEvents(run).map((event) => <li key={event.id}><div className="research-event-heading"><strong>{event.actor}</strong><time dateTime={event.at}>{new Date(event.at).toLocaleTimeString()}</time></div><p>{event.message}</p>{!!event.details?.length && <ul>{event.details.map((detail, index) => <li key={index}>{detail}</li>)}</ul>}</li>)}</ol>
            {run.result?.searchQuery && <p><strong>Search query:</strong> {run.result.searchQuery}</p>}
            {run.result?.focus && <p><strong>Research focus:</strong> {run.result.focus}</p>}
            {!!run.result?.unknowns?.length && <><strong>Uncertainties for human review</strong><ul>{run.result.unknowns.map((item, index) => <li key={index}>{item}</li>)}</ul></>}
            {!!run.result?.sources?.length && <details><summary>Candidate sources returned ({run.result.sources.length})</summary><ul>{run.result.sources.map((source, index) => <li key={index}><a href={source.url.startsWith("https://") ? source.url : undefined} target="_blank" rel="noopener noreferrer">{source.title || source.url}</a><p>{source.retrievalState || source.status || "metadata_only"} · {source.excerpt || "No excerpt available"}</p></li>)}</ul></details>}
            {run.safeError && <p role="alert">{run.safeError}</p>}
            <details><summary>Run references</summary><p>Run <code>{run.runId}</code> · Trace <code>{run.traceId}</code></p></details>
          </section>)}
        </div>
      </section>
    </div>}
  </>;
}
