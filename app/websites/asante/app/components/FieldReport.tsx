"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { FieldReportChart, FieldReportDocument, FieldReportSection, FieldReportTable, safeReportUrl } from "./plan-document";

type Props = {
  projectId: string;
  initialDocument: FieldReportDocument;
  editable: boolean;
  onSave: (document: FieldReportDocument) => Promise<void>;
  onShare?: () => Promise<void>;
  onRevokeShare?: () => Promise<void>;
  shareUrl?: string;
  onInvite?: (email: string, role: "viewer" | "editor") => Promise<void>;
  collaborators?: Array<{ email: string; role: "viewer" | "editor" }>;
  exportPath?: string;
};

type ExportFormat = "pdf" | "text" | "json";

export default function FieldReport({ projectId, initialDocument, editable, onSave, onShare, onRevokeShare, shareUrl = "", onInvite, collaborators = [], exportPath, }: Props) {
  const [document, setDocument] = useState(initialDocument);
  const [mode, setMode] = useState<"view" | "edit">("view");
  const [saveState, setSaveState] = useState("Saved");
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<"viewer" | "editor">("viewer");
  const baseline = useRef(JSON.stringify(initialDocument));
  const saving = useRef(false);
  const saveCallback = useRef(onSave);
  saveCallback.current = onSave;

  useEffect(() => {
    setDocument(initialDocument);
    baseline.current = JSON.stringify(initialDocument);
    setSaveState("Saved");
  }, [projectId]);

  useEffect(() => {
    if (!editable || mode !== "edit") return;
    const snapshot = JSON.stringify(document);
    if (snapshot === baseline.current) return;
    setSaveState("Unsaved changes");
    const timer = window.setTimeout(async () => {
      if (saving.current) return;
      saving.current = true;
      setSaveState("Saving…");
      try {
        await saveCallback.current(document);
        baseline.current = snapshot;
        setSaveState("Saved");
      } catch {
        setSaveState("Save failed. Your edits remain here; retry by editing a field.");
      } finally { saving.current = false; }
    }, 750);
    return () => window.clearTimeout(timer);
  }, [document, editable, mode]);

  async function download(format: ExportFormat) {
    const path = exportPath || `/asante/api/v1/workspace/projects/${encodeURIComponent(projectId)}/plan-document/export`;
    const response = await fetch(`${path}?format=${format}`, { cache: "no-store" });
    if (!response.ok) throw new Error("The report export is unavailable. Please retry.");
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = window.document.createElement("a");
    link.href = url;
    link.download = `asante-field-report.${format === "text" ? "txt" : format}`;
    link.click();
    URL.revokeObjectURL(url);
  }

  async function invite(event: FormEvent) {
    event.preventDefault();
    if (!onInvite) return;
    await onInvite(inviteEmail, inviteRole);
    setInviteEmail("");
  }

  function updateSection(index: number, fields: Partial<FieldReportSection>) {
    setDocument((current) => ({ ...current, sections: current.sections.map((item, itemIndex) => itemIndex === index ? { ...item, ...fields } : item) }));
  }
  function updateChart(index: number, next: FieldReportChart) {
    setDocument((current) => ({ ...current, charts: current.charts.map((item, itemIndex) => itemIndex === index ? next : item) }));
  }
  function updateTable(index: number, next: FieldReportTable) {
    setDocument((current) => ({ ...current, tables: current.tables.map((item, itemIndex) => itemIndex === index ? next : item) }));
  }

  return <div className="field-report-shell">
    <div className="field-report-toolbar">
      <div><span className="field-report-brand">ASANTE / FIELD REPORT</span><span className="field-report-save" role="status">{saveState}</span></div>
      <div className="action-row field-report-actions">
        {editable && <button type="button" className="button secondary" onClick={() => setMode(mode === "view" ? "edit" : "view")}>{mode === "view" ? "Edit report" : "View report"}</button>}
        <details className="field-report-download"><summary className="button secondary">Download report</summary><div>{(["pdf", "text", "json"] as ExportFormat[]).map((format) => <button type="button" key={format} onClick={() => void download(format).catch((error: Error) => setSaveState(error.message))}>Download {format.toUpperCase()}</button>)}</div></details>
        {editable && onShare && <button type="button" className="button primary" onClick={() => void onShare()}>Share report</button>}
      </div>
    </div>
    {shareUrl && <section className="field-report-share"><label>Read-only share link<input readOnly value={shareUrl} onFocus={(event) => event.currentTarget.select()} /></label><div className="action-row"><button type="button" className="button secondary" onClick={() => void navigator.clipboard?.writeText(shareUrl).then(() => setSaveState("Share link copied"))}>Copy link</button>{editable && onRevokeShare && <button type="button" className="button secondary" onClick={() => void onRevokeShare()}>Revoke link and invites</button>}</div>
      {editable && onInvite && <><form className="field-report-invite" onSubmit={(event) => void invite(event)}><label>Invite an existing Asante account<input type="email" required value={inviteEmail} onChange={(event) => setInviteEmail(event.target.value)} placeholder="name@example.org" /></label><select aria-label="Collaborator role" value={inviteRole} onChange={(event) => setInviteRole(event.target.value as "viewer" | "editor")}><option value="viewer">Viewer</option><option value="editor">Editor</option></select><button className="button secondary" type="submit">Add collaborator</button></form><p className="muted">Invites apply to existing Asante accounts. Share the link with the invited person; viewer access is read-only.</p>{collaborators.length > 0 && <ul className="field-report-collaborators">{collaborators.map((item) => <li key={item.email}>{item.email}<span>{item.role}</span></li>)}</ul>}</>}
    </section>}
    {mode === "edit" && editable ? <div className="field-report-editor">
      <p className="field-report-editor-note">Edit the report sections directly. Changes autosave to this story project.</p>
      <label>Report title<input maxLength={300} value={document.title} onChange={(event) => setDocument({ ...document, title: event.target.value })} /></label>
      <label>Subtitle<input maxLength={300} value={document.subtitle} onChange={(event) => setDocument({ ...document, subtitle: event.target.value })} /></label>
      <label>Place<input maxLength={200} value={document.landmark} onChange={(event) => setDocument({ ...document, landmark: event.target.value })} /></label>
      <label>Executive summary<textarea rows={4} maxLength={5000} value={document.summary} onChange={(event) => setDocument({ ...document, summary: event.target.value })} /></label>
      {document.sections.map((section, index) => <fieldset key={section.id} className="field-report-editor-section"><legend>{section.icon || "•"} Section {index + 1}</legend><label>Section title<input maxLength={160} value={section.title} onChange={(event) => updateSection(index, { title: event.target.value })} /></label><label>Section notes<textarea rows={3} maxLength={5000} value={section.body} onChange={(event) => updateSection(index, { body: event.target.value })} /></label><label>Bullets, one per line<textarea rows={4} maxLength={5000} value={section.bullets.join("\n")} onChange={(event) => updateSection(index, { bullets: event.target.value.split("\n").slice(0, 40) })} /></label><button type="button" className="quiet" onClick={() => setDocument({ ...document, sections: document.sections.filter((_, itemIndex) => itemIndex !== index) })}>Remove section</button></fieldset>)}
      <button type="button" className="button secondary" onClick={() => setDocument({ ...document, sections: [...document.sections, { id: crypto.randomUUID(), title: "New section", body: "", bullets: [] }] })}>Add section</button>
      {document.charts.map((chart, index) => <fieldset key={chart.id} className="field-report-editor-section"><legend>Chart: {chart.title}</legend><label>Chart title<input value={chart.title} onChange={(event) => updateChart(index, { ...chart, title: event.target.value })} /></label>{chart.series.map((item, seriesIndex) => <div className="field-report-series-edit" key={`${chart.id}-${seriesIndex}`}><label>Label<input value={item.label} onChange={(event) => updateChart(index, { ...chart, series: chart.series.map((series, i) => i === seriesIndex ? { ...series, label: event.target.value } : series) })} /></label><label>Value<input type="number" value={item.value} onChange={(event) => updateChart(index, { ...chart, series: chart.series.map((series, i) => i === seriesIndex ? { ...series, value: Number(event.target.value) || 0 } : series) })} /></label></div>)}</fieldset>)}
      {document.tables.map((table, index) => <fieldset key={table.id} className="field-report-editor-section"><legend>Table: {table.title}</legend><label>Table title<input value={table.title} onChange={(event) => updateTable(index, { ...table, title: event.target.value })} /></label>{table.rows.map((row, rowIndex) => <div className="field-report-series-edit" key={`${table.id}-${rowIndex}`}>{row.map((cell, cellIndex) => <label key={cellIndex}>{table.columns[cellIndex] || `Column ${cellIndex + 1}`}<input value={cell} onChange={(event) => updateTable(index, { ...table, rows: table.rows.map((cells, i) => i === rowIndex ? cells.map((value, j) => j === cellIndex ? event.target.value : value) : cells) })} /></label>)}</div>)}</fieldset>)}
      <p className="muted">Research references and image credits remain attached to their original sources. Candidate sources still require human interpretation.</p>
    </div> : <ReportView document={document} />}
  </div>;
}

function ReportView({ document }: { document: FieldReportDocument }) {
  const max = Math.max(1, ...document.charts.flatMap((chart) => chart.series.map((item) => Math.abs(item.value))));
  return <article className="field-report-document">
    <header className="field-report-cover"><p>ASANTE / CONTRIBUTOR FIELD REPORT</p><h1>{document.title}</h1>{document.subtitle && <p className="field-report-subtitle">{document.subtitle}</p>}<div className="field-report-place">⌖ {document.landmark || "Place not specified"}</div><div className="field-report-cover-rule" /></header>
    <section className="field-report-summary"><h2>01 / Executive summary</h2><p>{document.summary}</p></section>
    {document.sections.map((section, index) => <section className="field-report-section" key={section.id}><h2><span>{section.icon || "•"}</span>{String(index + 2).padStart(2, "0")} / {section.title}</h2>{section.body && <p>{section.body}</p>}{section.bullets.length > 0 && <ul>{section.bullets.map((bullet, bulletIndex) => <li key={`${section.id}-${bulletIndex}`}>{bullet}</li>)}</ul>}</section>)}
    {document.charts.map((chart) => <figure className="field-report-chart" key={chart.id}><figcaption>{chart.title}</figcaption>{chart.series.map((item, index) => <div className="field-report-chart-row" key={`${chart.id}-${index}`}><span>{item.label}</span><div><i style={{ width: `${Math.max(2, Math.abs(item.value) / max * 100)}%` }} /></div><strong>{item.value}{chart.unit ? ` ${chart.unit}` : ""}</strong></div>)}</figure>)}
    {document.tables.map((table) => <section className="field-report-table-wrap" key={table.id}><h2>{table.title}</h2><div className="field-report-table-scroll"><table><thead><tr>{table.columns.map((column, index) => <th key={`${table.id}-h-${index}`}>{column}</th>)}</tr></thead><tbody>{table.rows.map((row, rowIndex) => <tr key={`${table.id}-r-${rowIndex}`}>{row.map((cell, cellIndex) => <td key={`${table.id}-${rowIndex}-${cellIndex}`}>{cell}</td>)}</tr>)}</tbody></table></div></section>)}
    {document.images.length > 0 && <section className="field-report-images"><h2>Related visual references</h2><div>{document.images.map((image, index) => <figure key={`${image.url}-${index}`}><a href={safeReportUrl(image.url)} target="_blank" rel="noopener noreferrer"><img src={safeReportUrl(image.url)} alt={image.caption || "Related source image"} loading="lazy" /></a><figcaption>{image.caption}<small>Credit: {image.credit || "Credit unavailable"}{image.sourceUrl && <> · <a href={safeReportUrl(image.sourceUrl)} target="_blank" rel="noopener noreferrer">Source</a></>}</small></figcaption></figure>)}</div></section>}
    {document.sources.length > 0 && <section className="field-report-sources"><h2>References / candidate sources</h2><ol>{document.sources.map((source, index) => <li key={`${source.url}-${index}`}><strong>{source.title || source.url}</strong><a href={safeReportUrl(source.url)} target="_blank" rel="noopener noreferrer">{source.url}</a>{source.excerpt && <p>{source.excerpt}</p>}<small>{source.publisher || "Publisher unconfirmed"}{source.retrievedAt && ` · Retrieved ${new Date(source.retrievedAt).toLocaleDateString()}`}{source.status && ` · ${source.status}`}</small></li>)}</ol><p className="field-report-caveat">Sources are candidates for human review. They are not proof of heritage claims.</p></section>}
    <footer className="field-report-human-gate"><span>HUMAN REVIEW GATE</span><p>{document.humanGate || "A human reviewer must approve publication."}</p><small>Asante workers do not publish stories.</small></footer>
  </article>;
}
