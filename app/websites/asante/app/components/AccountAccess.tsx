"use client";

import { FormEvent, useState } from "react";
import { api } from "./story-domain";
import { Workspace } from "./workspace-client";

export default function AccountAccess({ onReady, deviceName }: { onReady: (workspace: Workspace) => void; deviceName?: string }) {
  const [registering, setRegistering] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState(deviceName || "");
  const [consent, setConsent] = useState(false);
  const [importDevice, setImportDevice] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setMessage("");
    try {
      const account = await api<{ role: "contributor" | "reviewer" }>(registering ? "/v1/auth/register" : "/v1/auth/login", registering ? { email, password, name, consent, import_device: importDevice } : { email, password });
      setPassword("");
      if (account.role === "reviewer") {
        window.location.assign("/asante/review/");
        return;
      }
      onReady(await api<Workspace>("/v1/workspace"));
    } catch (cause) { setMessage((cause as Error).message); }
    finally { setBusy(false); }
  }

  return (
    <main className="account-page">
      <a className="brand" href="/asante/"><span className="brand-mark">a</span>asante</a>
      <div className="account-grid">
        <section>
          <p className="eyebrow">One sign-in</p>
          <h1>Stories and<br />careful review.</h1>
          <p>Contributors open the story portal. Reviewers open the review desk. Your role decides which workspace appears after sign-in.</p>
          <a href="/asante/">← Back to the map</a>
        </section>
        <form className="surface profile-form" onSubmit={(event) => void submit(event)}>
          <p className="eyebrow">{registering ? "Start your story" : "Welcome back"}</p>
          <h2>{registering ? "Create an Asante account" : "Sign in to Asante"}</h2>
          {registering && <label>Attribution name<input required minLength={2} maxLength={120} value={name} onChange={(event) => setName(event.target.value)} autoComplete="name" /></label>}
          <label>Email<input type="email" required value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="username" /></label>
          <label>Password<input type="password" required minLength={12} maxLength={128} value={password} onChange={(event) => setPassword(event.target.value)} autoComplete={registering ? "new-password" : "current-password"} /></label>
          {registering && (
            <>
              <p className="muted">Use at least 12 characters. Your attribution name will identify your public contributor profile.</p>
              <label className="check"><input required type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} /> Store my account and contributor profile in Asante.</label>
              {deviceName && <label className="check"><input type="checkbox" checked={importDevice} onChange={(event) => { setImportDevice(event.target.checked); if (event.target.checked) setName(deviceName); }} /> Link this device&apos;s existing workspace, credited to {deviceName}, to this new account.</label>}
            </>
          )}
          <button disabled={busy} className="button primary">{busy ? "Opening…" : registering ? "Create account & enter →" : "Sign in →"}</button>
          <button disabled={busy} type="button" className="quiet" onClick={() => { setRegistering(!registering); setPassword(""); setMessage(""); }}>{registering ? "Already have an account? Sign in" : "New here? Create an account"}</button>
          <p role="status" className="feedback">{message}</p>
        </form>
      </div>
    </main>
  );
}
