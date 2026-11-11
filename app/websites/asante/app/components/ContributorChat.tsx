"use client";

import { FormEvent, ReactNode, useEffect, useRef, useState } from "react";
import { languageNames, ResearchPacket, Story } from "./story-domain";
import { Account, Media, Profile, Project, ResearchBrief, SaveProjectOptions } from "./workspace-client";
import { illustrativePublishedHistory } from "./portal-chat-domain";
import FieldReport from "./FieldReport";
import StoryPlayer from "./StoryPlayer";
import { buildFieldReportDocument, FieldReportDocument } from "./plan-document";
import { api } from "./story-domain";
import ResearchBriefForm from "./ResearchBriefForm";
import ResearchActivity from "./ResearchActivity";
import { useDraftAutosave } from "./useDraftAutosave";

type Popup = "shape" | "brief" | "profile" | "plan" | "research" | "upload" | "submit" | null;
type Worker = "planner" | "researcher";
type SubmissionPreview = {
  packet: {
    title: string; contributor_name: string; revision_id: string; revision_version: number; summary: string; claim: string; source_url: string;
    consent_scope: string; media_name: string; media_checksum: string; plan_document?: FieldReportDocument;
    research?: { sources?: Array<{ sourceId: string; title?: string; url?: string; excerpt?: string; snippet?: string; retrievalState: string }> };
    worker_runs?: Array<{ runId: string; traceId: string; workerType: string; status: string }>;
  };
  preview_hash: string;
};

type Props = {
  account: Account;
  profile: Profile;
  profileDraft: Profile;
  onProfileDraftChange: (profile: Profile) => void;
  onAutosaveProfile?: (profile: Profile) => Promise<Profile>;
  projects: Project[];
  project: Project | null;
  publishedStories: Story[];
  publishedId: string | null;
  media: Media | null;
  busy: boolean;
  message: string;
  onDismissMessage: () => void;
  activeWorker: Worker | null;
  uploadProgress: number | null;
  isUploading: boolean;
  isDirty: boolean;
  legacyCount: number;
  storageConsent: boolean;
  onStorageConsentChange: (value: boolean) => void;
  liveLocation: boolean;
  onLiveLocationChange: (value: boolean) => void;
  onImportBrowserData: () => void;
  onSelectProject: (project: Project, saved?: boolean) => void;
  onSelectPublished: (story: Story) => void;
  onClearSelection: () => boolean;
  onSaveProject: (project: Project, options?: SaveProjectOptions) => Promise<Project>;
  onSavePlanDocument: (document: FieldReportDocument) => Promise<void>;
  onUpdate: (fields: Partial<Project>) => void;
  onRunResearch: (savedBrief?: Project) => Promise<void>;
  onUploadFile: (file: File, consent: boolean) => Promise<boolean>;
  onCancelUpload: () => void;
  onSubmit: (previewHash?: string) => Promise<boolean>;
  onSaveProfile: (consent: boolean) => Promise<boolean>;
  onSignOut: () => void;
};

function blankProject(): Project {
  return {
    id: crypto.randomUUID(), title: "", place: "Constitution Hill", language: "en", format: "audio",
    audience: "Community listeners", transcript: "", claim: "", source: "", consent: false,
    suggestion: "pending", version: 0,
  };
}

function PopupFrame({ title, onClose, children, message, wide = false }: { title: string; onClose: () => void; children: ReactNode; message?: string; wide?: boolean }) {
  return (
    <div className="modal-backdrop portal-modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className={`surface portal-popup${wide ? " wide" : ""}`} role="dialog" aria-modal="true" aria-label={title}>
        <header className="portal-popup-bar"><div><p className="eyebrow">Asante story chat</p><h2>{title}</h2></div><button type="button" className="plan-results-close" aria-label={`Close ${title}`} onClick={onClose}>×</button></header>
        {message && <p className="portal-modal-feedback" role="status">{message}</p>}
        {children}
      </section>
    </div>
  );
}

function SourceCards({ research }: { research: ResearchPacket }) {
  const sources = research.sources || [];
  return (
    <>
      {research.summary && <p>{research.summary}</p>}
      {research.focus && <p className="muted">Focus: {research.focus}</p>}
      {sources.length > 0 ? (
        <ul className="source-list">{sources.map((source) => (
          <li key={source.url + source.title}>
            <div className="source-meta"><strong>{source.title || source.publisher || source.url}</strong>{source.platform && <span className="badge">{source.platform}</span>}</div>
            <a href={source.url} target="_blank" rel="noopener noreferrer">{source.url}</a>
            <p>{source.excerpt || "No excerpt was available from the collector."}</p>
            <small>{source.publisher || source.collector || "Research collector"}{source.retrievedAt ? ` · retrieved ${new Date(source.retrievedAt).toLocaleString()}` : ""} · {source.retrievalState || source.status || "metadata_only"}</small>
          </li>
        ))}</ul>
      ) : <p className="muted">No sources were returned. The researcher did not invent a source; adjust the question and retry.</p>}
      {!!research.notes?.length && <div className="portal-research-notes"><strong>Research notes</strong>{research.notes.map((note, index) => <p key={`${index}-${note}`}>{note}</p>)}</div>}
      <p className="prototype-note">These are candidate sources for human review, not verified proof.{research.retrievedAt ? ` Retrieved ${new Date(research.retrievedAt).toLocaleString()}.` : ""}</p>
    </>
  );
}

export default function ContributorChat(props: Props) {
  const {
    account, profile, profileDraft, onProfileDraftChange, projects, project, publishedStories, publishedId,
    media, busy, message, onDismissMessage, activeWorker, uploadProgress, isUploading, isDirty, legacyCount, storageConsent,
    onStorageConsentChange, liveLocation, onLiveLocationChange, onImportBrowserData, onSelectProject, onSelectPublished,
    onClearSelection, onSaveProject, onSavePlanDocument, onRunResearch, onUploadFile, onCancelUpload, onSubmit, onSaveProfile, onSignOut,
  } = props;
  const [popup, setPopup] = useState<Popup>(null);
  const [shapeDraft, setShapeDraft] = useState<Project | null>(null);
  const [briefDraft, setBriefDraft] = useState<{ claim: string; source: string; answers: ResearchBrief } | null>(null);
  const [shapeSaving, setShapeSaving] = useState(false);
  const [profileSaving, setProfileSaving] = useState(false);
  const [briefSaving, setBriefSaving] = useState(false);
  const saving = useRef(false);
  const scope = useRef("");
  scope.current = `${account.id}:${project?.id || "new"}`;
  const [planActionBusy, setPlanActionBusy] = useState(false);
  const [uploadConsent, setUploadConsent] = useState(false);
  const [planDocument, setPlanDocument] = useState<FieldReportDocument | null>(null);
  const [shareUrl, setShareUrl] = useState("");
  const [collaborators, setCollaborators] = useState<Array<{ email: string; role: "viewer" | "editor" }>>([]);
  const [shareMessage, setShareMessage] = useState("");
  const [submissionPreview, setSubmissionPreview] = useState<SubmissionPreview | null>(null);
  const [submissionPreviewMessage, setSubmissionPreviewMessage] = useState("");
  const selectedStory = publishedStories.find((story) => story.id === publishedId) || null;
  const canEdit = Boolean(project && !project.submissionId);
  const briefComplete = Boolean(project?.claim.trim() && project.researchBrief?.questions.trim());
  const shapeAutosave = useDraftAutosave({
    scope: `${account.id}:shape:${shapeDraft?.id}`, value: shapeDraft, enabled: popup === "shape" && Boolean(shapeDraft && !shapeDraft.submissionId),
    save: (draft) => onSaveProject(draft, { background: true }),
    onSaved: (saved) => setShapeDraft((current) => current?.id === saved.id ? { ...current, version: saved.version } : current),
  });
  const briefAutosave = useDraftAutosave({
    scope: `${account.id}:brief:${project?.id}`, value: briefDraft, enabled: popup === "brief" && canEdit,
    save: (draft) => {
      if (!project) throw new Error("Reopen the project before saving.");
      return onSaveProject({ ...project, claim: draft.claim, source: draft.source, researchBrief: draft.answers }, { background: true });
    },
  });
  const profileAutosave = useDraftAutosave({
    scope: `${account.id}:profile`, value: profileDraft, baseline: profile,
    enabled: popup === "profile" && storageConsent && Boolean(props.onAutosaveProfile),
    save: async (draft) => {
      if (!props.onAutosaveProfile) throw new Error("Profile autosave is unavailable.");
      return props.onAutosaveProfile(draft);
    },
  });
  const noteAutosave = useDraftAutosave({
    scope: `${account.id}:notes:${project?.id}`, value: project ? { claim: project.claim } : null,
    enabled: canEdit && popup === null && !busy,
    save: (draft) => {
      if (!project) throw new Error("Reopen the project before saving.");
      return onSaveProject({ ...project, claim: draft.claim }, { background: true });
    },
  });
  function autosaveFeedback(state: { status: string; flush: () => Promise<unknown> }) {
    return <p className="form-save-status" role="status">{state.status}{state.status.startsWith("Save failed") && <button type="button" className="quiet" onClick={() => void state.flush().catch(() => undefined)}>Retry autosave</button>}</p>;
  }
  async function flushOpenForm() {
    if (popup === "shape" && shapeAutosave.dirty) await shapeAutosave.flush();
    if (popup === "brief" && briefAutosave.dirty) await briefAutosave.flush();
    if (popup === "profile" && storageConsent && profileAutosave.dirty) await profileAutosave.flush();
    if (popup === null && noteAutosave.dirty) await noteAutosave.flush();
  }
  async function closeForm() {
    try { await flushOpenForm(); setPopup(null); } catch { /* Retain unsaved inputs and show retry. */ }
  }

  useEffect(() => {
    setPopup(null); setBriefDraft(null); setShapeDraft(null); setShareUrl(""); setCollaborators([]);
  }, [project?.id]);

  function openBrief() {
    if (!project || !canEdit) return;
    onDismissMessage();
    setBriefDraft({ claim: project.claim, source: project.source, answers: project.researchBrief || {
      knownMaterial: project.transcript.slice(0, 5000), questions: "", context: "", priorities: "", uncertainties: "",
    } });
    setPopup("brief");
  }

  async function saveBrief(start: boolean) {
    if (!project || !canEdit || !briefDraft || !briefDraft.claim.trim() || !briefDraft.answers.questions.trim() || saving.current) return;
    const currentScope = scope.current;
    saving.current = true; setBriefSaving(true);
    try {
      const saved = await briefAutosave.flush();
      if (scope.current !== currentScope) return;
      setPopup(null);
      if (start) await onRunResearch(saved);
    } catch { /* Keep entered answers in the popup on validation or save failure. */ }
    finally { saving.current = false; setBriefSaving(false); }
  }

  useEffect(() => {
    if (popup !== "plan" || !project) return;
    setPlanDocument(project.planDocument || buildFieldReportDocument(project));
    setShareUrl("");
    setCollaborators([]);
    let cancelled = false;
    api<{ share: { token: string } | null; collaborators: Array<{ email: string; role: "viewer" | "editor" }> }>(`/v1/workspace/projects/${project.id}/plan-share`)
      .then((saved) => {
        if (cancelled) return;
        setCollaborators(saved.collaborators);
        if (saved.share) setShareUrl(`${window.location.origin}/asante/plans/${encodeURIComponent(saved.share.token)}/`);
      })
      .catch(() => { /* No share exists yet; the field report remains usable. */ });
    return () => { cancelled = true; };
  }, [popup, project?.id]);

  useEffect(() => {
    if (popup !== "submit" || !project || project.submissionId) return;
    setSubmissionPreview(null);
    if (isDirty) {
      setSubmissionPreviewMessage("Save your latest story edits, then reopen this review step to load the authoritative packet preview.");
      return;
    }
    let cancelled = false;
    setSubmissionPreviewMessage("Loading the saved submission snapshot…");
    api<SubmissionPreview>(`/v1/submissions/preview/${encodeURIComponent(project.id)}?expected_version=${project.version}`)
      .then((preview) => { if (!cancelled) { setSubmissionPreview(preview); setSubmissionPreviewMessage(""); } })
      .catch((error: Error) => { if (!cancelled) setSubmissionPreviewMessage(error.message); });
    return () => { cancelled = true; };
  }, [popup, project?.id, project?.version, project?.submissionId, isDirty]);

  async function createShare() {
    if (!project) return;
    try {
      if (canEdit && planDocument) await onSavePlanDocument(planDocument);
      const saved = await api<{ token: string }>(`/v1/workspace/projects/${project.id}/plan-share`, {});
      setShareUrl(`${window.location.origin}/asante/plans/${encodeURIComponent(saved.token)}/`);
      const access = await api<{ collaborators: Array<{ email: string; role: "viewer" | "editor" }> }>(`/v1/workspace/projects/${project.id}/plan-share`);
      setCollaborators(access.collaborators);
      setShareMessage("Read-only link created. Invite an existing account below to grant editing access.");
    } catch (cause) { setShareMessage((cause as Error).message); }
  }

  async function inviteCollaborator(email: string, role: "viewer" | "editor") {
    if (!project) return;
    try {
      await api(`/v1/workspace/projects/${project.id}/plan-share/collaborators`, { email, role });
      const access = await api<{ collaborators: Array<{ email: string; role: "viewer" | "editor" }> }>(`/v1/workspace/projects/${project.id}/plan-share`);
      setCollaborators(access.collaborators);
      setShareMessage(`${email} added as ${role}.`);
    } catch (cause) { setShareMessage((cause as Error).message); }
  }

  async function revokeShare() {
    if (!project) return;
    const response = await fetch(`/asante/api/v1/workspace/projects/${encodeURIComponent(project.id)}/plan-share`, { method: "DELETE", headers: { "X-Asante-Request": "1" } });
    if (!response.ok) { setShareMessage("The share link could not be revoked."); return; }
    setShareUrl("");
    setCollaborators([]);
    setShareMessage("The share link and collaborator access were revoked.");
  }

  async function openNewChat() {
    try { await flushOpenForm(); } catch { return; }
    if (!onClearSelection()) return;
    setShapeDraft(blankProject());
    setPopup("shape");
  }

  async function chooseProject(next: Project) {
    if (next.id === project?.id) return;
    try { await flushOpenForm(); } catch { return; }
    onSelectProject(next, true);
  }

  function openShape() {
    if (!project) return;
    setShapeDraft({ ...project });
    setPopup("shape");
  }

  async function saveShape(event: FormEvent) {
    event.preventDefault();
    if (!shapeDraft || shapeDraft.title.trim().length < 3 || saving.current) return;
    saving.current = true; setShapeSaving(true);
    const currentScope = scope.current;
    try {
      const saved = await shapeAutosave.flush();
      if (scope.current !== currentScope) return;
      onSelectProject(saved, true);
      setPopup(null);
    } catch { /* The workspace message keeps the save failure visible; retain the shape popup. */ }
    finally { saving.current = false; setShapeSaving(false); }
  }

  async function decidePlan(suggestion: "accepted" | "rejected") {
    if (!project) return;
    setPlanActionBusy(true);
    try {
      const saved = await onSaveProject({ ...project, suggestion });
      onSelectProject(saved, true);
    } catch {
      // The workspace message keeps the save failure visible.
    } finally {
      setPlanActionBusy(false);
    }
  }

  async function submitUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const input = event.currentTarget.elements.namedItem("story-media") as HTMLInputElement | null;
    const file = input?.files?.[0];
    if (file && uploadConsent && await onUploadFile(file, uploadConsent)) setPopup(null);
  }

  async function submitPacket() {
    if (submissionPreview && await onSubmit(submissionPreview.preview_hash)) setPopup(null);
  }

  async function saveForSubmissionPreview() {
    if (!project) return;
    try { await onSaveProject(project); } catch { /* The workspace keeps the save error visible. */ }
  }

  async function saveProfile(event: FormEvent) {
    event.preventDefault();
    if (storageConsent && props.onAutosaveProfile) {
      setProfileSaving(true);
      try { await profileAutosave.flush(); setPopup(null); } catch { /* Retain profile edits. */ }
      finally { setProfileSaving(false); }
    } else if (await onSaveProfile(storageConsent)) setPopup(null);
  }

  const title = project?.title || selectedStory?.title || "Your Asante story chats";
  return (
    <main className="portal-chat-shell">
      <aside className="portal-chat-rail" aria-label="Story chats">
        <div className="portal-chat-brand"><a className="brand" href="/asante/portal/"><span className="brand-mark">a</span>asante</a><p className="eyebrow">Story chats</p></div>
        <div className="portal-chat-list" aria-label="Your project chats">
          <p className="portal-list-label">Drafts and projects</p>
          {projects.map((item) => <button type="button" key={item.id} className={`portal-chat-item${project?.id === item.id ? " active" : ""}`} onClick={() => chooseProject(item)}>
            <strong>{item.title || "Untitled story"}</strong><small>{item.submissionId ? "Sent for human review" : item.research ? "Research updated" : item.plan ? "Plan ready" : "Story draft"}</small>
          </button>)}
          {!projects.length && <p className="muted portal-list-empty">Your new story chats will appear here.</p>}
        </div>
        {!!publishedStories.length && <div className="portal-chat-list published-chat-list" aria-label="Published story chats">
          <p className="portal-list-label">Published stories</p>
          {publishedStories.map((story) => <button type="button" key={story.id} className={`portal-chat-item${publishedId === story.id ? " active" : ""}`} onClick={() => onSelectPublished(story)}>
            <strong>{story.title}</strong><small>{story.landmark} · published story</small>
          </button>)}
        </div>}
        <footer className="portal-chat-profile">
          <button type="button" className="portal-profile-control" onClick={() => setPopup("profile")}><span className="avatar">{profile.name.slice(0, 2).toUpperCase()}</span><span><strong>{profile.name}</strong><small>Profile settings</small></span><span aria-hidden="true">›</span></button>
          <button type="button" className="quiet" onClick={() => void flushOpenForm().then(onSignOut).catch(() => undefined)}>Sign out</button>
          <small>{account.email}</small>
        </footer>
      </aside>

      <section className="portal-chat-stage" aria-label="Story conversation">
        {message && <p className="feedback portal-chat-feedback" role="status">{message}<button type="button" aria-label="Dismiss message" onClick={onDismissMessage}>×</button></p>}
        {legacyCount > 0 && <div className="portal-import-banner"><p>{legacyCount} saved Asante browser record{legacyCount === 1 ? "" : "s"} can be backed up and imported into this account.</p><button type="button" className="button secondary" disabled={busy} onClick={onImportBrowserData}>Import browser records</button></div>}
        {project ? <>
          <header className="portal-chat-header"><div><p className="eyebrow">{project.submissionId ? "Submitted story chat" : "Draft story chat"}</p><h1>{title}</h1><p className="muted">{project.place} · {languageNames[project.language] || project.language} · {project.format}</p></div><div className="portal-chat-header-actions" aria-label="Story actions"><button type="button" className="button primary" disabled={!canEdit || busy || !project.claim.trim()} onClick={() => void onSaveProject(project)}>{busy ? "Saving…" : "Save note"}</button><button type="button" className="button secondary" disabled={!canEdit || busy} onClick={() => setPopup("submit")}>{project.submissionId ? "Submission sent" : "Review & submit"}</button></div></header>
          <div className="portal-chat-thread" role="log" aria-live="polite">
            <div className="chat-day">Story chat · {project.status === "draft" || !project.status ? "Draft" : project.status.replaceAll("_", " ")}</div>
            <div className="chat-row you"><span className="chat-avatar you" aria-hidden="true">{profile.name.slice(0, 1).toUpperCase()}</span><article className="chat-bubble user"><p className="chat-label">01 / Shape your story</p><h2>{project.title || "Untitled story"}</h2><p>{project.place} · {languageNames[project.language] || project.language} · {project.format} · for {project.audience || "your listeners"}</p>{project.claim && <><p><strong>Your claim or research question</strong></p><p>{project.claim}</p></>}{project.source && <p><strong>Source to consider:</strong> <a href={project.source} target="_blank" rel="noopener noreferrer">{project.source}</a></p>}{project.transcript && <details><summary>Story notes and original words</summary><p>{project.transcript}</p></details>}<div className="chat-actions"><button type="button" className="button secondary" disabled={!canEdit || busy} onClick={openShape}>Edit story details</button>{!project.submissionId && <button type="button" className="button secondary" disabled={busy} onClick={() => void onSaveProject(project)}>Save story notes</button>}</div></article></div>

            {!project.submissionId && <div className="chat-row asante"><span className="chat-avatar asante" aria-hidden="true">✦</span><article className="chat-bubble asante portal-result-bubble" data-testid="research-step">
              <p className="chat-label">02 / Prepare your research brief</p>
              <p>Tell us more about your story so the Asante workers can prepare relevant research and a field report.</p>
              <p className="muted">{!briefComplete ? "Your research brief is incomplete." : project.researchFlow?.status === "completed" ? "Research completed for this saved brief. Candidate evidence requires human interpretation." : project.researchFlow?.status === "failed" ? "Research failed. Your saved brief is preserved." : project.researchFlow?.status === "running" ? "Research is in progress for your saved brief." : "Brief saved. Research has not completed for these answers."}</p>
              {project.researchFlow?.status === "failed" && <p role="alert">{project.researchFlow.safeError || "The worker could not complete research. Retry using the saved brief."}</p>}
              <div className="chat-actions portal-action-stack">
                <button type="button" className="button primary" disabled={busy || activeWorker !== null} onClick={openBrief}>{briefComplete ? "Edit research brief" : "Complete research brief"}</button>
                <button type="button" className="button secondary" disabled={busy || activeWorker !== null} onClick={openShape}>Edit story details</button>
                {briefComplete && project.researchFlow?.status !== "completed" && <button type="button" className="button secondary" disabled={busy || activeWorker !== null} onClick={() => void onRunResearch()}>{project.researchFlow?.status === "failed" ? "Retry research" : "Start research"}</button>}
                {project.researchFlow?.status === "completed" && project.plan && project.research?.sources?.length && project.planDocument ? <><button type="button" className="button primary" onClick={() => setPopup("plan")}>Open field report</button><button type="button" className="button secondary" onClick={() => setPopup("research")}>Open sources</button></> : null}
              </div>
            </article></div>}

            <ResearchActivity key={`${account.id}:${project.id}`} project={project} accountId={account.id} />

            {activeWorker && <div className="chat-row asante" role="status"><span className="chat-avatar asante" aria-hidden="true">✦</span><article className="chat-bubble working"><span className="worker-busy-dot" aria-hidden="true"/><div><p className="chat-label">Asante {activeWorker === "planner" ? "story planner" : "researcher"} is working</p><p>{activeWorker === "planner" ? "Preparing the story plan…" : "Finding candidate evidence… Sources require human interpretation."}</p></div></article></div>}

            {project.plan && <div className="chat-row asante"><span className="chat-avatar asante" aria-hidden="true">✦</span><article className="chat-bubble asante portal-result-bubble"><p className="chat-label">Story plan · {project.suggestion}{project.plan.aiUsed ? " · AI-assisted" : " · fixture"}</p><p>A planning suggestion is ready. Review it, then accept or reject it. Your original details stay separate.</p><div className="chat-actions portal-action-stack"><button type="button" className="button primary" onClick={() => setPopup("plan")}>View plan</button>{project.suggestion === "pending" && <><button type="button" className="button secondary" disabled={!canEdit || busy || planActionBusy} onClick={() => void decidePlan("accepted")}>Accept plan</button><button type="button" className="button secondary" disabled={!canEdit || busy || planActionBusy} onClick={() => void decidePlan("rejected")}>Reject plan</button></>}</div></article></div>}

            {project.research && <div className="chat-row asante"><span className="chat-avatar asante" aria-hidden="true">⌕</span><article className="chat-bubble asante portal-result-bubble"><p className="chat-label">Research results · candidate evidence</p><p>{project.research.summary || `${project.research.sources?.length || 0} candidate sources collected.`}</p><p className="muted">{project.research.sources?.length || 0} source candidates. Open each source and decide what it supports.</p><div className="chat-actions portal-action-stack"><button type="button" className="button primary" onClick={() => setPopup("research")}>Review sources</button></div></article></div>}

            {(media || project.media) && <div className="chat-row you"><span className="chat-avatar you" aria-hidden="true">♪</span><article className="chat-bubble user"><p className="chat-label">Original recording · {project.submissionId ? "included in submitted packet" : "stored and verified"}</p><p>{media?.name || project.media?.name}</p><div className="chat-actions"><button type="button" className="button secondary" onClick={() => setPopup("upload")}>View recording</button></div></article></div>}

            {project.submissionId && <div className="chat-row asante"><span className="chat-avatar asante" aria-hidden="true">✓</span><article className="chat-bubble asante"><p className="chat-label">Sent for human review</p><p>Packet reference <code>{project.submissionId}</code>. A human reviewer decides what happens next. This chat cannot publish the story.</p></article></div>}
          </div>
          <div className="portal-chat-composer">
            <button type="button" className="button secondary portal-upload-action" disabled={!canEdit || busy} onClick={() => setPopup("upload")}>＋ Upload recording</button>
            <label className="portal-note-field"><span className="visually-hidden">Story question or notes</span><textarea rows={2} maxLength={5000} disabled={!canEdit || busy} value={project.claim} onChange={(event) => props.onUpdate({ claim: event.target.value })} placeholder="Add a research question or note to your story…" /></label>
          </div>
        </> : selectedStory ? <>
          <header className="portal-chat-header"><div><p className="eyebrow">Published story chat · archive</p><h1>{selectedStory.title}</h1><p className="muted">{selectedStory.landmark} · {languageNames[selectedStory.language] || selectedStory.language}</p></div></header>
          <div className="portal-chat-thread" role="log">
            <div className="chat-day">Published story archive</div>
            <div className="chat-row you published-media-row"><span className="chat-avatar you" aria-hidden="true">♪</span><article className="chat-bubble user portal-result-bubble published-media-bubble"><p className="chat-label">Published recording · processed media</p><p>{selectedStory.media_format === "video" ? "The preserved video, poster, playback stream and available timed captions are attached to this story." : "The preserved audio and available timed captions are attached to this story."}</p><StoryPlayer key={selectedStory.id} story={selectedStory} lowData={false} /><p className="muted published-media-status">{selectedStory.media_url ? "Media is processed and available for playback. Choose captions after pressing Play." : "This published record has no playable media attached."}</p></article></div>
            <div className="portal-illustrative-label">Illustrative archive history · not actual worker or reviewer logs</div>
            {illustrativePublishedHistory(selectedStory.title).map((entry, index) => <div className={`chat-row ${index === 0 ? "you" : "asante"}`} key={entry}><span className={`chat-avatar ${index === 0 ? "you" : "asante"}`} aria-hidden="true">{index === 0 ? "S" : "a"}</span><article className={`chat-bubble ${index === 0 ? "user" : "asante"}`}><p className="chat-label">{index === 0 ? "Story archive" : index === 1 ? "Asante archive preview" : "Human review · illustrative"}</p><p>{entry}</p></article></div>)}
            {selectedStory.transcript && <div className="chat-row asante"><span className="chat-avatar asante" aria-hidden="true">a</span><article className="chat-bubble asante"><p className="chat-label">Published story</p><p>{selectedStory.transcript}</p></article></div>}
          </div>
          <div className="portal-chat-composer archive-composer"><p className="muted">Published story archives are read-only. Use the + button to start another story chat.</p></div>
        </> : <div className="portal-chat-empty"><span className="brand-mark">a</span><p className="eyebrow">Contributor story chats</p><h1>What story would you like to tell?</h1><p>Use the + button to shape a story, ask the Asante team for a plan or candidate evidence, and prepare a recording for human review.</p></div>}

        <button type="button" className="chat-fab portal-chat-fab" aria-label="New story chat" title="New chat" onClick={openNewChat}>＋</button>
      </section>

      {popup === "shape" && shapeDraft && <PopupFrame title={project ? "Edit your story" : "01 / Shape your story"} onClose={() => { if (!shapeSaving) void closeForm(); }} message={message} wide>
        <form className="portal-popup-content" onSubmit={(event) => void saveShape(event)}>
          {autosaveFeedback(shapeAutosave)}
          <p className="muted">Start with the details you know. You can refine the story later, and your words remain yours.</p>
          <fieldset disabled={shapeSaving}>
          <label>Story title<input required minLength={3} maxLength={200} value={shapeDraft.title} onChange={(event) => setShapeDraft({ ...shapeDraft, title: event.target.value })} placeholder="e.g. The river remembers" /></label>
          <div className="field-grid"><label>Place<select value={shapeDraft.place} onChange={(event) => setShapeDraft({ ...shapeDraft, place: event.target.value })}><option>Constitution Hill</option><option>Soweto Towers</option><option>Mapungubwe Hill</option><option>District Six</option></select></label><label>Original language<select value={shapeDraft.language} onChange={(event) => setShapeDraft({ ...shapeDraft, language: event.target.value })}>{Object.entries(languageNames).map(([code, name]) => <option key={code} value={code}>{name}</option>)}</select></label><label>Story format<select value={shapeDraft.format} onChange={(event) => setShapeDraft({ ...shapeDraft, format: event.target.value })}><option value="audio">Audio</option><option value="video">Video</option></select></label><label>Audience<input maxLength={120} value={shapeDraft.audience} onChange={(event) => setShapeDraft({ ...shapeDraft, audience: event.target.value })} /></label></div>
          <label>Claim, question, or notes<textarea rows={5} maxLength={5000} value={shapeDraft.claim} onChange={(event) => setShapeDraft({ ...shapeDraft, claim: event.target.value })} placeholder="What question should research help you explore? What should listeners understand?" /></label>
          <label>Existing source URL (optional)<input type="url" pattern="https://.*" title="Enter a secure https:// link" value={shapeDraft.source} onChange={(event) => setShapeDraft({ ...shapeDraft, source: event.target.value })} placeholder="https://…" /></label>
          <label>Original story words (optional)<textarea rows={5} maxLength={20000} value={shapeDraft.transcript} onChange={(event) => setShapeDraft({ ...shapeDraft, transcript: event.target.value })} placeholder="Keep your original words here…" /></label>
          </fieldset>
          <div className="action-row portal-popup-actions"><button className="button primary" type="submit" disabled={busy || shapeSaving || shapeDraft.title.trim().length < 3}>{busy ? "Saving…" : project ? "Save story details" : "Save and open chat"}</button><button type="button" className="button secondary" onClick={() => void closeForm()}>Close</button></div>
        </form>
      </PopupFrame>}

      {popup === "brief" && briefDraft && canEdit && <PopupFrame title="02 / Prepare your research brief" onClose={() => { if (!briefSaving) void closeForm(); }} message={message} wide>
        {autosaveFeedback(briefAutosave)}
        <ResearchBriefForm draft={briefDraft} onChange={setBriefDraft} onSave={(start) => void saveBrief(start)} busy={busy || briefSaving} />
      </PopupFrame>}

      {popup === "profile" && <PopupFrame title="Profile settings" onClose={() => { if (!profileSaving) void closeForm(); }} message={message}><form className="portal-popup-content" onSubmit={(event) => void saveProfile(event)}>
        {storageConsent ? autosaveFeedback(profileAutosave) : <p className="form-save-status">Confirm storage consent below to enable profile autosave.</p>}
        <fieldset disabled={profileSaving}>
        <label>Attribution name<input required minLength={2} maxLength={120} value={profileDraft.name} onChange={(event) => onProfileDraftChange({ ...profileDraft, name: event.target.value })} /></label>
        <label>Bio<textarea maxLength={5000} rows={4} value={profileDraft.bio} onChange={(event) => onProfileDraftChange({ ...profileDraft, bio: event.target.value })} /></label>
        <label>Preferred language<select value={profileDraft.language} onChange={(event) => onProfileDraftChange({ ...profileDraft, language: event.target.value })}>{Object.entries(languageNames).map(([code, name]) => <option key={code} value={code}>{name}</option>)}</select></label>
        <label className="check">
          <input type="checkbox" checked={liveLocation} onChange={(event) => onLiveLocationChange(event.target.checked)} />
          Live location on the map
        </label>
        <p className="muted">Turn this off to stop using your location on the listener map. Distances stay optional either way.</p>
        <label className="check"><input required type="checkbox" checked={storageConsent} onChange={(event) => onStorageConsentChange(event.target.checked)} /> Store these profile changes in Asante.</label>
        <p className="muted">Your public profile shows approved stories and attribution, not your email address.</p>
        </fieldset>
        <div className="action-row portal-popup-actions"><button className="button primary" disabled={busy || profileSaving} type="submit">{busy || profileSaving ? "Saving…" : "Save profile"}</button><a className="button secondary" href={`/asante/profiles/${account.profileId}/`} target="_blank" rel="noopener noreferrer">View public profile</a></div>
      </form></PopupFrame>}

      {popup === "plan" && project?.plan && planDocument && <PopupFrame title="Asante field report" onClose={() => setPopup(null)} message={message || shareMessage} wide><div className="portal-popup-content field-report-popup-content"><p className="muted">{project.suggestion === "accepted" ? "You accepted this planning suggestion." : project.suggestion === "rejected" ? "You rejected this planning suggestion." : "This is a planning suggestion for you to review."} {project.plan.aiUsed ? "Prepared with the configured AI provider." : "Prepared in fixture mode."} · Trace <code>{project.plan.trace_id}</code></p>
        <FieldReport key={project.id} projectId={project.id} initialDocument={planDocument} editable={canEdit} onSave={onSavePlanDocument} onShare={createShare} onRevokeShare={revokeShare} shareUrl={shareUrl} onInvite={inviteCollaborator} collaborators={collaborators} />
        <div className="action-row portal-popup-actions field-report-decision"><button type="button" className="button primary" disabled={busy || planActionBusy || !canEdit || project.suggestion === "accepted"} onClick={() => void decidePlan("accepted")}>Accept plan</button><button type="button" className="button secondary" disabled={busy || planActionBusy || !canEdit || project.suggestion === "rejected"} onClick={() => void decidePlan("rejected")}>Reject plan</button><button type="button" className="button secondary" disabled={busy || !canEdit} onClick={openBrief}>Edit research brief</button><button type="button" className="button secondary" disabled={!canEdit || busy} onClick={openShape}>Edit story details</button></div>
      </div></PopupFrame>}

      {popup === "research" && project?.research && <PopupFrame title="Candidate research sources" onClose={() => setPopup(null)} message={message} wide><div className="portal-popup-content"><SourceCards research={project.research}/><div className="action-row portal-popup-actions"><button type="button" className="button primary" disabled={busy || !canEdit} onClick={openBrief}>Edit research brief</button><button type="button" className="button secondary" onClick={() => setPopup(null)}>Done reviewing</button></div></div></PopupFrame>}

      {popup === "upload" && project && <PopupFrame title="Upload your recording" onClose={() => { if (!isUploading) setPopup(null); }} message={message}><form className="portal-popup-content portal-upload-form" onSubmit={(event) => void submitUpload(event)}>
        {media || project.media ? <div className="portal-media-preview"><strong>{media?.name || project.media?.name}</strong><p>{media ? (media.size / 1024 / 1024).toFixed(2) : ""} {media ? "MB · stored and verified" : "Recording is stored and verified"}</p>{(media || project.media)?.type.startsWith("video/") ? <video src={(media || project.media)?.url} controls preload="metadata" playsInline /> : <audio src={(media || project.media)?.url} controls preload="metadata" />}</div> : <p>Choose an audio or video recording. Asante stores the original and checks its actual format, duration and checksum.</p>}
        {canEdit && <><label className="file-drop"><span className="file-drop-title">Choose audio or video</span><input name="story-media" type="file" accept="audio/mpeg,audio/wav,audio/ogg,video/mp4,video/webm" disabled={busy} /><small>Audio up to 100 MB · video up to 500 MB · maximum 10 minutes</small></label><label className="check"><input type="checkbox" checked={uploadConsent} onChange={(event) => setUploadConsent(event.target.checked)} /> I consent to storing this original recording for Asante review.</label></>}
        {!media && !project.media && <p className="muted">Your recording is not uploaded yet.</p>}
        {uploadProgress !== null && <p role="status">{uploadProgress < 100 ? `Uploading ${uploadProgress}%` : "Verifying recording…"}<button type="button" className="quiet" onClick={onCancelUpload}>Cancel upload</button></p>}
        <p className="prototype-note">Consent to store and analyse the media format is requested before upload. Your original is preserved.</p>
        {canEdit && <div className="action-row portal-popup-actions"><button type="submit" className="button primary" disabled={busy || !uploadConsent}>{isUploading ? "Uploading…" : media || project.media ? "Replace recording" : "Upload recording"}</button><button type="button" className="button secondary" disabled={isUploading} onClick={() => setPopup(null)}>Close</button></div>}
      </form></PopupFrame>}

      {popup === "submit" && project && <PopupFrame title="Review and submit" onClose={() => setPopup(null)} message={message} wide><div className="portal-popup-content"><p>Check this saved revision before sending it to the human review team. Submission does not publish the story.</p><p role="status" className="muted">{submissionPreviewMessage}</p>{isDirty && <button type="button" className="button secondary" disabled={busy} onClick={() => void saveForSubmissionPreview()}>Save edits and load packet preview</button>}{submissionPreview && <section className="submission-snapshot"><p className="eyebrow">Server snapshot · revision {submissionPreview.packet.revision_version}</p><h3>{submissionPreview.packet.title}</h3><p>By {submissionPreview.packet.contributor_name} · {submissionPreview.packet.media_name}</p><p>Consent scope: {submissionPreview.packet.consent_scope}</p><h4>Original narrative</h4><p>{submissionPreview.packet.summary || "No narrative supplied."}</p><h4>Claim and source</h4><p>{submissionPreview.packet.claim || "No specific claim supplied."}</p>{submissionPreview.packet.source_url && <p>{submissionPreview.packet.source_url}</p>}<details><summary>Included plan and report</summary>{submissionPreview.packet.plan_document ? <><h3>{submissionPreview.packet.plan_document.title}</h3><p>{submissionPreview.packet.plan_document.summary}</p>{submissionPreview.packet.plan_document.sections.map((section) => <section key={section.id}><h4>{section.title}</h4>{section.body && <p>{section.body}</p>}{section.bullets.length > 0 && <ul>{section.bullets.map((bullet, index) => <li key={index}>{bullet}</li>)}</ul>}</section>)}</> : <p>No saved field report.</p>}</details><details><summary>Submitted evidence sources</summary>{(submissionPreview.packet.research?.sources || []).map((source) => <article key={source.sourceId}><strong>{source.title || source.url || source.sourceId}</strong><span className="badge">{source.retrievalState}</span><p>{source.excerpt || source.snippet || "Metadata only; no excerpt was submitted."}</p></article>)}{!(submissionPreview.packet.research?.sources || []).length && <p>No research sources attached.</p>}</details><details><summary>Linked worker runs</summary>{(submissionPreview.packet.worker_runs || []).map((run) => <p key={run.runId}>{run.workerType} · {run.status} · <code>{run.traceId}</code></p>)}{!(submissionPreview.packet.worker_runs || []).length && <p>No planner/researcher runs attached.</p>}</details><p className="muted">Snapshot hash: <code>{submissionPreview.preview_hash}</code></p></section>}
        <dl><dt>Story</dt><dd>{project.title}</dd><dt>Attribution</dt><dd>{profile.name}</dd><dt>Place</dt><dd>{project.place}</dd><dt>Language</dt><dd>{languageNames[project.language] || project.language}</dd><dt>Recording</dt><dd>{media?.name || project.media?.name || "Upload required"}</dd><dt>Plan</dt><dd>{project.plan ? `Suggestion ${project.suggestion}` : "No plan prepared"}</dd><dt>Research</dt><dd>{project.research ? `${project.research.sources?.length || 0} candidate sources` : "No sources collected"}</dd></dl>
        <label className="check"><input type="checkbox" disabled={busy || Boolean(project.submissionId)} checked={project.consent} onChange={(event) => props.onUpdate({ consent: event.target.checked })}/> I consent to sending this story packet, its location, and attribution to Asante human review.</label>
        <p className="muted">A reviewer will make the decision. Nothing publishes automatically from this chat.</p>
        <div className="action-row portal-popup-actions"><button type="button" className="button primary" disabled={busy || !submissionPreview || !media && !project.media || !project.consent || project.title.trim().length < 3 || Boolean(project.submissionId)} onClick={() => void submitPacket()}>{busy ? "Sending packet…" : "Send for human review"}</button><button type="button" className="button secondary" onClick={() => setPopup(null)}>Keep editing</button></div>
      </div></PopupFrame>}
    </main>
  );
}
