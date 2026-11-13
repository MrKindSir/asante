"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api, AsanteApiError, mediaError, mutationHeaders, supportingDocumentError } from "./story-domain";

import { captureAsanteStorage, openWorkspace, savePreference, uploadFile, Profile, Project, Media, Workspace, migrateBrowserStorage, Account, SaveProjectOptions } from "./workspace-client";

const liveLocationKey = "asante.liveLocation";

import AccountAccess from "./AccountAccess";
import { Story } from "./story-domain";
import ContributorChat from "./ContributorChat";
import { portalChatHref, readPortalChatSelection } from "./portal-chat-domain";
import { portalGuideKey, portalGuideSteps, readPortalGuide } from "./portal-guide-domain";
import { portalResearchGuideKey, portalResearchGuideSteps, readPortalResearchGuide } from "./portal-research-guide-domain";
import { portalMediaGuideKey, portalMediaGuideSteps, readPortalMediaGuide } from "./portal-media-guide-domain";
import { portalSubmitGuideKey, portalSubmitGuideSteps, readPortalSubmitGuide } from "./portal-submit-guide-domain";
import { FieldReportDocument } from "./plan-document";

export default function ContributorWorkspace() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const chatSelection = readPortalChatSelection(new URLSearchParams(searchParams.toString()));
  const [account, setAccount] = useState<Account | null>(null);
  const [publishedStories, setPublishedStories] = useState<Story[]>([]);
  const accountId = useRef<string | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [profileDraft, setProfileDraft] = useState<Profile>({ name: "", email: "", bio: "", language: "en" });
  const [projects, setProjects] = useState<Project[]>([]);
  const [project, setProject] = useState<Project | null>(null);
  const projectRef = useRef(project); projectRef.current = project;
  const savedVersions = useRef(new Map<string, number>());
  const selection = useRef<string | null>(null);
  const accountEpoch = useRef(0);
  const saves = useRef(new Map<string, Promise<Project>>());
  const researchLock = useRef(false);
  const researchFlowSeen = useRef<{ projectId: string | null; status?: string }>({ projectId: null });
  const activeWorker = project?.researchFlow?.status === "running" ? project.researchFlow.workerType || null : null;
  const [media, setMedia] = useState<Media | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [activityOpenRequest, setActivityOpenRequest] = useState(0);
  const [storageConsent, setStorageConsent] = useState(false);
  const [liveLocation, setLiveLocation] = useState(false);
  const [ready, setReady] = useState(false);
  const [legacyCount, setLegacyCount] = useState(0);
  const [portalGuideStep, setPortalGuideStep] = useState<number | null>(null);
  const [portalResearchGuideStep, setPortalResearchGuideStep] = useState<number | null>(null);
  const [portalMediaGuideStep, setPortalMediaGuideStep] = useState<number | null>(null);
  const [portalSubmitGuideStep, setPortalSubmitGuideStep] = useState<number | null>(null);

  const [dirty, setDirty] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);
  const uploadController = useRef<AbortController | null>(null);

  function applyWorkspace(saved: Workspace) {
    const nextId = saved.account?.id || null;
    if (accountId.current !== nextId) {
      accountEpoch.current += 1;
      selection.current = null;
      setBusy(false); researchLock.current = false; saves.current.clear(); savedVersions.current.clear();
      setMessage("");
      setStorageConsent(false);
      setProject(null);
      setMedia(null);
      setDirty(false);
      if (accountId.current) router.replace(portalChatHref({ projectId: null, publishedId: null }));
    }
    accountId.current = nextId;
    setAccount(saved.account || null);
    setPublishedStories(saved.publishedStories || []);
    setProfile(saved.profile);
    if (saved.profile) setProfileDraft(saved.profile);
    setProjects(saved.projects);
    setLiveLocation(saved.preferences?.[liveLocationKey] === "true");
    setPortalGuideStep(readPortalGuide(saved.preferences?.[portalGuideKey]));
    setPortalResearchGuideStep(readPortalResearchGuide(saved.preferences?.[portalResearchGuideKey]));
    setPortalMediaGuideStep(readPortalMediaGuide(saved.preferences?.[portalMediaGuideKey]));
    setPortalSubmitGuideStep(readPortalSubmitGuide(saved.preferences?.[portalSubmitGuideKey]));
  }
  useEffect(() => {
    let active = true;
    try { setLegacyCount(Object.keys(captureAsanteStorage(localStorage, sessionStorage)).length); } catch { /* Storage may be blocked. */ }
    openWorkspace().then((saved) => { if (active) applyWorkspace(saved); })
      .catch((cause: Error) => { if (active) setMessage(cause.message); })
      .finally(() => { if (active) setReady(true); });
    return () => { active = false; uploadController.current?.abort(); };
  }, []);

  async function updateLiveLocation(enabled: boolean) {
    setLiveLocation(enabled);
    try {
      await savePreference(liveLocationKey, String(enabled));
      setMessage(enabled ? "Live location enabled for the map." : "Live location turned off. The map will stop using your location.");
    } catch (cause) {
      setLiveLocation(!enabled);
      setMessage((cause as Error).message);
    }
  }
  function movePortalGuide(next: number) {
    const step = next >= portalGuideSteps.length ? null : Math.max(0, next);
    setPortalGuideStep(step);
    void savePreference(portalGuideKey, JSON.stringify({ version: 1, step: step ?? portalGuideSteps.length })).catch(() => undefined);
  }
  function replayPortalGuide() {
    setPortalGuideStep(0);
    void savePreference(portalGuideKey, JSON.stringify({ version: 1, step: 0 })).catch(() => undefined);
  }
  function movePortalResearchGuide(next: number) {
    const step = next >= portalResearchGuideSteps.length ? null : Math.max(0, next);
    setPortalResearchGuideStep(step);
    void savePreference(portalResearchGuideKey, JSON.stringify({ version: 1, step: step ?? portalResearchGuideSteps.length })).catch(() => undefined);
  }
  function replayPortalResearchGuide() {
    setPortalResearchGuideStep(0);
    void savePreference(portalResearchGuideKey, JSON.stringify({ version: 1, step: 0 })).catch(() => undefined);
  }
  function movePortalMediaGuide(next: number) {
    const step = next >= portalMediaGuideSteps.length ? null : Math.max(0, next);
    setPortalMediaGuideStep(step);
    void savePreference(portalMediaGuideKey, JSON.stringify({ version: 1, step: step ?? portalMediaGuideSteps.length })).catch(() => undefined);
  }
  function replayPortalMediaGuide() {
    setPortalMediaGuideStep(0);
    void savePreference(portalMediaGuideKey, JSON.stringify({ version: 1, step: 0 })).catch(() => undefined);
  }
  function movePortalSubmitGuide(next: number) {
    const step = next >= portalSubmitGuideSteps.length ? null : Math.max(0, next);
    setPortalSubmitGuideStep(step);
    void savePreference(portalSubmitGuideKey, JSON.stringify({ version: 1, step: step ?? portalSubmitGuideSteps.length })).catch(() => undefined);
  }
  function replayPortalSubmitGuide() {
    setPortalSubmitGuideStep(0);
    void savePreference(portalSubmitGuideKey, JSON.stringify({ version: 1, step: 0 })).catch(() => undefined);
  }
  useEffect(() => {
    if (ready && account?.role === "reviewer") window.location.replace("/asante/review/");
  }, [ready, account]);
  useEffect(() => {
    const projectId = searchParams.get("project");
    if (!projectId) {
      if (searchParams.has("published")) {
        selection.current = null;
        setProject(null);
        setMedia(null);
        setDirty(false);
      }
      return;
    }
    if (projects.length === 0) return;
    const found = projects.find((item) => item.id === projectId);
    if (!found) return;
    selection.current = found.id;
    setProject((current) => {
      if (current?.id === found.id) return current;
      setMedia(found.media || null);
      setDirty(false);
      return found;
    });
  }, [searchParams, projects]);

  function selectProjectChat(next: Project, saved = false) {
    if (!saved && dirty && project?.id !== next.id && !window.confirm("Discard the unsaved story changes?")) return;
    selection.current = next.id;
    setProject(next);
    setMedia(next.media || null);
    setDirty(false);
    setMessage("");
    router.push(portalChatHref({ projectId: next.id, publishedId: null }));
  }

  function selectPublishedChat(story: Story) {
    if (dirty && !window.confirm("Discard the unsaved story changes?")) return;
    selection.current = null;
    setProject(null);
    setMedia(null);
    setDirty(false);
    setMessage("");
    router.push(portalChatHref({ projectId: null, publishedId: story.id }));
  }

  function clearChatSelection(): boolean {
    if (dirty && !window.confirm("Discard the unsaved story changes?")) return false;
    selection.current = null;
    setProject(null);
    setMedia(null);
    setDirty(false);
    setMessage("");
    router.push(portalChatHref({ projectId: null, publishedId: null }));
    return true;
  }
  async function signOut() {
    if (dirty && !window.confirm("Sign out and discard unsaved changes? Saved drafts remain in Asante.")) return;
    setBusy(true);
    try { await api("/v1/auth/logout", {}); setAccount(null); setProfile(null); setProjects([]); setProject(null); setMedia(null); setPublishedStories([]); setDirty(false); accountId.current = null; accountEpoch.current += 1; selection.current = null; setMessage(""); }
    catch (cause) { setMessage((cause as Error).message); }
    finally { setBusy(false); }
  }
  useEffect(() => {
    const refreshAccount = () => {
      const epoch = accountEpoch.current;
      void api<Workspace>("/v1/workspace").then((saved) => {
        if (epoch === accountEpoch.current && (saved.account?.id || null) !== accountId.current) applyWorkspace(saved);
      }).catch((cause: unknown) => {
        if (epoch === accountEpoch.current && cause instanceof AsanteApiError && cause.status === 401) applyWorkspace({ account: null, profile: null, projects: [], preferences: {} });
      });
    };
    window.addEventListener("focus", refreshAccount);
    return () => window.removeEventListener("focus", refreshAccount);
  }, []);
  function applySavedProject(saved: Project, epoch: number) {
    if (epoch !== accountEpoch.current) return;
    savedVersions.current.set(`${epoch}:${saved.id}`, saved.version);
    setProjects((items) => [saved, ...items.filter((item) => item.id !== saved.id)]);
    if (selection.current === saved.id) {
      setProject(saved); setMedia(saved.media || null); setDirty(false);
    }
  }
  function saveProject(next: Project, options: SaveProjectOptions = {}): Promise<Project> {
    const epoch = accountEpoch.current;
    const savingKey = `${epoch}:${next.id}`;
    const pending = saves.current.get(savingKey);
    if (pending) return pending.then(() => {
      if (epoch !== accountEpoch.current) throw new Error("Your account changed before this save.");
      return saveProject(next, options);
    });
    const selected = selection.current;
    if (!options.background) { setBusy(true); setMessage(""); }
    const saving = (async () => {
      try {
        const base = projectRef.current;
        const version = Math.max(savedVersions.current.get(savingKey) ?? 0, next.version);
        const saved = await api<Project>("/v1/workspace/projects", { ...next, version });
        if (epoch !== accountEpoch.current) throw new Error("Your account changed. Reopen the saved story in its original account.");
        savedVersions.current.set(savingKey, saved.version);
        if (options.background) {
          setProjects((items) => [saved, ...items.filter((item) => item.id !== saved.id)]);
          if (selection.current === saved.id) {
            const current = projectRef.current;
            if (current && base && current !== base) {
              const changed = Object.fromEntries(Object.entries(current).filter(([key, value]) => key !== "version" && key !== "researchFlow" && JSON.stringify(value) !== JSON.stringify(base[key as keyof Project])));
              setProject({ ...saved, ...changed });
            } else { setProject(saved); setDirty(false); }
          }
        } else applySavedProject(saved, epoch);
        if (selection.current !== selected) throw new Error("The draft was saved in its original chat. Reopen it to continue.");
        if (!options.background) setMessage("Draft saved to Asante.");
        return saved;
      } catch (cause) {
        if (!options.background && epoch === accountEpoch.current && selection.current === selected) setMessage((cause as Error).message);
        throw cause;
      } finally {
        saves.current.delete(savingKey);
        if (!options.background && epoch === accountEpoch.current && !researchLock.current) setBusy(false);
      }
    })();
    saves.current.set(savingKey, saving);
    return saving;
  }
  async function savePlanDocument(document: FieldReportDocument): Promise<void> {
    if (!project || project.submissionId) throw new Error("Submitted story plans are frozen.");
    const savingAccount = accountId.current;
    const savingEpoch = accountEpoch.current;
    const response = await fetch(`/asante/api/v1/workspace/projects/${encodeURIComponent(project.id)}/plan-document`, {
      method: "PUT",
      headers: mutationHeaders(),
      body: JSON.stringify({ expectedVersion: project.version, document }),
    });
    if (!response.ok) {
      let detail = "The field report could not be saved.";
      try { const body = await response.json() as { detail?: unknown }; if (typeof body.detail === "string") detail = body.detail; } catch { /* Keep the safe fallback. */ }
      throw new Error(detail);
    }
    const saved = await response.json() as { document: FieldReportDocument; version: number };
    if (savingEpoch !== accountEpoch.current || savingAccount !== accountId.current) throw new Error("Your account changed before the report was saved.");
    const updated = { ...project, planDocument: saved.document, version: saved.version };
    applySavedProject(updated, savingEpoch);
    if (selection.current === updated.id) setMessage("Field report autosaved to this story project.");
  }
  function update(fields: Partial<Project>) {
    if (!project || busy) return;
    if (project.submissionId) { setMessage("Submitted revisions are preserved. Duplicate this project to edit."); return; }
    setProject({ ...project, ...fields }); setDirty(true);
  }
  async function saveProfile(draft = profileDraft, background = false): Promise<boolean> {
    const savingAccount = accountId.current;
    const epoch = accountEpoch.current;
    if (!background) setBusy(true);
    try {
      const saved = await api<Profile>("/v1/workspace/profile", draft);
      if (epoch !== accountEpoch.current || savingAccount !== accountId.current) throw new Error("Your account changed. Reopen your profile before editing.");
      setProfile(saved); if (!background) setMessage("Contributor profile saved to Asante.");
      return true;
    } catch (cause) {
      if (background) throw cause;
      if (epoch === accountEpoch.current) setMessage((cause as Error).message);
      return false;
    } finally { if (!background && epoch === accountEpoch.current) setBusy(false); }
  }
  async function runResearch(savedBrief?: Project, requestedWorker?: "planner" | "researcher"): Promise<void> {
    const initial = savedBrief || project;
    if (!initial || initial.submissionId || !initial.researchBrief || researchLock.current) return;
    researchLock.current = true;
    const epoch = accountEpoch.current;
    const selected = initial.id;
    const stillHere = () => epoch === accountEpoch.current && selection.current === selected;
    setBusy(true); setMessage("");
    let saved = initial;
    try {
      if (!savedBrief && dirty) saved = await saveProject(initial);
      if (!stillHere()) return;
      // Always carry the returned server version into the next worker call.
      const workerTypes = requestedWorker ? [requestedWorker] : (["planner", "researcher"] as const);
      for (const workerType of workerTypes) {
        const planHash = saved.plan?.researchInputHash;
        if (workerType === "planner" && planHash && planHash === saved.researchFlow?.inputHash) continue;
        if (workerType === "researcher" && saved.researchFlow?.status === "completed") continue;
        const running: Project = { ...saved, researchFlow: { status: "running", workerType, inputHash: saved.researchFlow?.inputHash || "" } };
        applySavedProject(running, epoch);
        const result = await api<Partial<Project> & { status: string; projectVersion: number; safeError?: string }>(
          `/v1/workspace/projects/${saved.id}/workers`, { workerType, expectedVersion: saved.version },
        );
        if (epoch !== accountEpoch.current) return;
        if (result.status !== "succeeded") throw new Error(result.safeError || "The worker did not attach results to this revision. Reopen the saved draft before retrying.");
        saved = { ...saved, plan: result.plan, research: result.research, suggestion: result.suggestion || saved.suggestion,
          planDocument: result.planDocument, researchFlow: result.researchFlow, version: result.projectVersion };
        applySavedProject(saved, epoch);
      }
      if (stillHere() && saved.researchFlow?.status === "completed") {
        setMessage("Research finished. Review the plan and candidate sources below — they still need your interpretation.");
      }
    } catch (cause) {
      let latestFlow: Project["researchFlow"];
      if (epoch === accountEpoch.current) {
        try {
          const workspace = await api<Workspace>("/v1/workspace");
          if (epoch === accountEpoch.current) {
            const latest = workspace.projects.find((item) => item.id === selected);
            if (latest) { latestFlow = latest.researchFlow; applySavedProject(latest, epoch); }
          }
        } catch { /* Keep the saved brief and expose the request failure. */ }
        if (stillHere()) {
          if (latestFlow?.status !== "running" && latestFlow?.status !== "completed") setProject((current) => current?.id === selected ? { ...current, researchFlow: { status: "failed", inputHash: current.researchFlow?.inputHash || "", safeError: (cause as Error).message } } : current);
          if (latestFlow?.status === "running") {
            setMessage("Connection interrupted. The worker kept running on the server. Watch live research activity for progress — this chat will update when it finishes.");
            setActivityOpenRequest((value) => value + 1);
          } else if (latestFlow?.status === "completed") {
            setMessage("Research finished. Review the plan and candidate sources below — they still need your interpretation.");
          } else {
            setMessage((cause as Error).message);
          }
        }
      }
    } finally {
      if (epoch === accountEpoch.current) { researchLock.current = false; setBusy(false); }
    }
  }
  useEffect(() => {
    const projectId = project?.id || null;
    const status = project?.researchFlow?.status;
    if (researchFlowSeen.current.projectId !== projectId) {
      researchFlowSeen.current = { projectId, status };
      return;
    }
    const previous = researchFlowSeen.current.status;
    researchFlowSeen.current = { projectId, status };
    if (previous !== "running") return;
    if (status === "completed") {
      setMessage("Research finished. Review the plan and candidate sources below — they still need your interpretation.");
    } else if (status === "failed") {
      setMessage(project?.researchFlow?.safeError || "Research failed. Your saved brief is preserved.");
    }
  }, [project?.id, project?.researchFlow?.status, project?.researchFlow?.safeError]);
  const mediaJobsBusy = Boolean(project?.mediaJobs?.some((job) => job.status === "queued" || job.status === "running"));
  useEffect(() => {
    if (project?.researchFlow?.status !== "running" || researchLock.current) return;
    const epoch = accountEpoch.current;
    const id = project.id;
    let cancelled = false;
    const timer = window.setInterval(() => {
      void api<Workspace>("/v1/workspace").then((workspace) => {
        if (cancelled || epoch !== accountEpoch.current || selection.current !== id) return;
        const latest = workspace.projects.find((item) => item.id === id);
        if (latest) applySavedProject(latest, epoch);
      }).catch(() => { /* A refresh never starts another worker. */ });
    }, 2000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [project?.id, project?.researchFlow?.status, busy]);
  useEffect(() => {
    if (!mediaJobsBusy || !project) return;
    const epoch = accountEpoch.current;
    const id = project.id;
    let cancelled = false;
    const timer = window.setInterval(() => {
      void api<Workspace>("/v1/workspace").then((workspace) => {
        if (cancelled || epoch !== accountEpoch.current || selection.current !== id) return;
        const latest = workspace.projects.find((item) => item.id === id);
        if (!latest) return;
        applySavedProject(latest, epoch);
        const pending = latest.mediaJobs?.some((job) => job.status === "queued" || job.status === "running");
        if (!pending && latest.transcriptDraft?.status === "draft") {
          setMessage("Transcription and translation drafts are ready for this recording. They still need human review.");
        }
      }).catch(() => { /* Polling never starts media jobs. */ });
    }, 2500);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [project?.id, mediaJobsBusy]);
  async function prepareFile(file: File, consent: boolean, purpose: "media" | "supporting_document" = "media"): Promise<boolean> {
    if (!project || !consent) return false;
    const error = purpose === "supporting_document" ? supportingDocumentError(file) : mediaError(file);
    if (error) { setMessage(error); return false; }
    setBusy(true); setMessage(""); setProgress(0);
    const controller = new AbortController(); uploadController.current = controller;
    try {
      const saved = dirty ? await saveProject(project) : project;
      setBusy(true);
      const intent = await api<{ uploadUrl: string }>("/v1/uploads", { project_id: saved.id, name: file.name, size: file.size, content_type: file.type, purpose, consent_given: true });
      await uploadFile(intent.uploadUrl, file, setProgress, controller.signal);
      const workspace = await api<Workspace>("/v1/workspace");
      applyWorkspace(workspace);
      const updated = workspace.projects.find((item) => item.id === saved.id);
      if (updated) { setProject(updated); setMedia(updated.media || null); setDirty(false); }
      setMessage(updated?.mediaJobs?.length
        ? "Original media stored in Asante. Transcription and translation jobs are queued within the live caption caps."
        : "Original media stored in Asante and verified by the server.");
      return true;
    } catch (cause) { setMessage((cause as Error).message); return false; }
    finally { setBusy(false); setProgress(null); uploadController.current = null; }
  }
  async function submit(previewHash?: string, consentGiven = project?.consent ?? false): Promise<boolean> {
    if (!project || !profile || !consentGiven || !(media || project.media)) return false;
    setBusy(true); setMessage("");
    try {
      const saved = dirty ? await saveProject(project) : project;
      setBusy(true);
      const preview = previewHash ? { preview_hash: previewHash } : await api<{ preview_hash: string }>(`/v1/submissions/preview/${encodeURIComponent(saved.id)}?expected_version=${saved.version}`);
      await api("/v1/submissions", { project_id: saved.id, expected_version: saved.version, consent_given: consentGiven, preview_hash: preview.preview_hash });
      const workspace = await api<Workspace>("/v1/workspace"); applyWorkspace(workspace);
      const updated = workspace.projects.find((item) => item.id === saved.id);
      if (updated) { setProject(updated); setMedia(updated.media || null); }
      setMessage("Packet and original media saved for human review. Nothing was published automatically.");
      return true;
    } catch (cause) { setMessage((cause as Error).message); return false; }
    finally { setBusy(false); }
  }
  async function clearSavedBrowserData() {
    setBusy(true);
    try { const saved = await migrateBrowserStorage(localStorage, sessionStorage); applyWorkspace(saved); setLegacyCount(0); setMessage("Asante browser records backed up, verified and cleared. Server data and your private session are retained."); }
    catch (cause) { setMessage((cause as Error).message); }
    finally { setBusy(false); }
  }

  if (!ready) return <main className="account-page"><p>Opening your workspace…</p></main>;
  if (!account) return <AccountAccess onReady={applyWorkspace} deviceName={profile?.name} />;
  if (account.role === "reviewer") return <main className="account-page"><p>Opening the review dashboard...</p></main>;
  if (!profile) return <main className="account-page"><p>Loading your contributor profile…</p></main>;

  return <ContributorChat
    key={account.id}
    account={account}
    profile={profile}
    profileDraft={profileDraft}
    onProfileDraftChange={setProfileDraft}
    onAutosaveProfile={async (draft) => {
      if (!storageConsent) throw new Error("Confirm profile storage consent before autosaving.");
      await saveProfile(draft, true);
      return draft;
    }}
    projects={projects}
    project={project}
    publishedStories={publishedStories}
    publishedId={chatSelection.publishedId}
    media={media}
    busy={busy}
    message={message}
    onDismissMessage={() => setMessage("")}
    activeWorker={activeWorker}
    activityOpenRequest={activityOpenRequest}
    uploadProgress={progress}
    isUploading={progress !== null}
    isDirty={dirty}
    legacyCount={legacyCount}
    storageConsent={storageConsent}
    onStorageConsentChange={setStorageConsent}
    liveLocation={liveLocation}
    onLiveLocationChange={(value) => void updateLiveLocation(value)}
    onImportBrowserData={() => void clearSavedBrowserData()}
    onSelectProject={selectProjectChat}
    onSelectPublished={selectPublishedChat}
    onClearSelection={clearChatSelection}
    onSaveProject={saveProject}
    onSavePlanDocument={savePlanDocument}
    onUpdate={update}
    onRunResearch={runResearch}
    onRunWorker={(workerType, savedBrief) => runResearch(savedBrief, workerType)}
    onUploadFile={prepareFile}
    onCancelUpload={() => uploadController.current?.abort()}
    onSubmit={submit}
    onSaveProfile={async (consent) => {
      if (!consent) {
        setMessage("Confirm that Asante may store these profile changes before saving.");
        return false;
      }
      return saveProfile();
    }}
    onSignOut={() => void signOut()}
    portalGuideStep={portalGuideStep}
    onPortalGuideMove={movePortalGuide}
    onPortalGuideReplay={replayPortalGuide}
    portalResearchGuideStep={portalResearchGuideStep}
    onPortalResearchGuideMove={movePortalResearchGuide}
    onPortalResearchGuideReplay={replayPortalResearchGuide}
    portalMediaGuideStep={portalMediaGuideStep}
    onPortalMediaGuideMove={movePortalMediaGuide}
    onPortalMediaGuideReplay={replayPortalMediaGuide}
    portalSubmitGuideStep={portalSubmitGuideStep}
    onPortalSubmitGuideMove={movePortalSubmitGuide}
    onPortalSubmitGuideReplay={replayPortalSubmitGuide}
  />;
}
