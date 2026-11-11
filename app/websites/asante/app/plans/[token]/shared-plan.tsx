"use client";

import { useCallback, useEffect, useState } from "react";
import FieldReport from "../../components/FieldReport";
import { FieldReportDocument } from "../../components/plan-document";

type SharedPlanData = { title: string; document: FieldReportDocument; role: string; canEdit: boolean; version: number };

export default function SharedPlan({ token }: { token: string }) {
  const [plan, setPlan] = useState<SharedPlanData | null>(null);
  const [error, setError] = useState("");
  const [saveMessage, setSaveMessage] = useState("");

  useEffect(() => {
    let active = true;
    fetch(`/asante/api/v1/plans/share/${encodeURIComponent(token)}`, { cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) throw new Error(response.status === 404 ? "This shared field report is unavailable." : "The shared field report could not be opened.");
        return response.json() as Promise<SharedPlanData>;
      })
      .then((saved) => { if (active) setPlan(saved); })
      .catch((cause: Error) => { if (active) setError(cause.message); });
    return () => { active = false; };
  }, [token]);

  const save = useCallback(async (document: FieldReportDocument) => {
    if (!plan) return;
    const response = await fetch(`/asante/api/v1/plans/share/${encodeURIComponent(token)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", "X-Asante-Request": "1" },
      body: JSON.stringify({ expectedVersion: plan.version, document }),
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({})) as { detail?: string };
      throw new Error(body.detail || "The shared report could not be saved.");
    }
    const saved = await response.json() as { document: FieldReportDocument; version: number };
    setPlan({ ...plan, document: saved.document, version: saved.version });
    setSaveMessage("Shared field report saved.");
  }, [plan, token]);

  if (error) return <main className="shared-plan-page"><a className="brand" href="/asante/"><span className="brand-mark">a</span>asante</a><section className="surface"><h1>Field report unavailable</h1><p>{error}</p></section></main>;
  if (!plan) return <main className="shared-plan-page"><p>Opening shared field report…</p></main>;
  return <main className="shared-plan-page"><header><a className="brand" href="/asante/"><span className="brand-mark">a</span>asante</a><span className="shared-plan-role">Shared field report · {plan.canEdit ? plan.role : "viewer"}</span></header>
    <p className="feedback" role="status">{saveMessage || (plan.canEdit ? "You can edit this report." : "Read-only shared copy. The contributor keeps control of the original story project.")}</p>
    <FieldReport projectId={token} initialDocument={plan.document} editable={plan.canEdit} onSave={save} exportPath={`/asante/api/v1/plans/share/${encodeURIComponent(token)}/export`} />
    {!plan.canEdit && <p className="shared-plan-signin">Invited editor? <a href="/asante/portal/">Sign in to Asante</a>, then reopen this link.</p>}
  </main>;
}
