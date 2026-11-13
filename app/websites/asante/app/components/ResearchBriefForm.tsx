"use client";

import { ResearchBrief } from "./workspace-client";

export type BriefDraft = { claim: string; source: string; answers: ResearchBrief };

export default function ResearchBriefForm({ draft, onChange, onSave, busy }: {
  draft: BriefDraft; onChange: (draft: BriefDraft) => void; onSave: (start: boolean) => void; busy: boolean;
}) {
  const fields: Array<{ key: keyof ResearchBrief; label: string; required?: boolean }> = [
    { key: "knownMaterial", label: "What you already know, remember, or have recorded (optional)" },
    { key: "questions", label: "Questions the research should answer", required: true },
    { key: "context", label: "Relevant people, dates, places, and cultural context (optional)" },
    { key: "priorities", label: "Research priorities (optional)" },
    { key: "uncertainties", label: "Uncertainties to explore (optional)" },
  ];
  return <form className="portal-popup-content" onSubmit={(event) => {
    event.preventDefault();
    const submitter = (event.nativeEvent as SubmitEvent).submitter as HTMLButtonElement | null;
    onSave(submitter?.value === "start");
  }}>
    <p>Oral history is welcome. A source URL is optional. Add other sources or links in what you already know.</p>
    <fieldset disabled={busy}>
      <label>Main story question or claim<textarea aria-label="Main story question or claim" required maxLength={5000} rows={3} value={draft.claim} onChange={(event) => onChange({ ...draft, claim: event.target.value })} /></label>
      {fields.map(({ key, label, required }) => <label key={key}>{label}<textarea aria-label={label} required={required} maxLength={5000} rows={3} value={draft.answers[key]} onChange={(event) => onChange({ ...draft, answers: { ...draft.answers, [key]: event.target.value } })} /></label>)}
      <label>Existing source URL (optional)<input type="url" pattern="https://.*" value={draft.source} onChange={(event) => onChange({ ...draft, source: event.target.value })} /></label>
    </fieldset>
    <div className="action-row portal-popup-actions"><button type="submit" value="save" className="button secondary" disabled={busy}>Save brief</button><button type="submit" value="start" className="button primary" disabled={busy}>Save and start research</button></div>
  </form>;
}
