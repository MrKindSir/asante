"use client";

import { FormEvent, useEffect, useState } from "react";
import { api } from "./story-domain";
import { Workspace } from "./workspace-client";

type DemoAccount = { id: string; name: string; email: string; role: "contributor" | "reviewer" };

export default function AccountAccess({ onReady, deviceName }: { onReady: (workspace: Workspace) => void; deviceName?: string }) {
  const [registering, setRegistering] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState(deviceName || "");
  const [consent, setConsent] = useState(false);
  const [importDevice, setImportDevice] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [demoAccounts, setDemoAccounts] = useState<DemoAccount[]>([]);
  const [demoAccount, setDemoAccount] = useState("");

  useEffect(() => {
    if (registering) return;
    void api<DemoAccount[]>("/v1/auth/demo-accounts").then(setDemoAccounts).catch(() => setDemoAccounts([]));
  }, [registering]);

  async function signInAsDemo(account: string) {
    if (!account) return;
    setBusy(true); setMessage("");
    try {
      const access = await api<{ role: "contributor" | "reviewer" }>("/v1/auth/demo-login", { account });
      if (access.role === "reviewer") {
        window.location.assign("/asante/review/");
        return;
      }
      onReady(await api<Workspace>("/v1/workspace"));
    } catch (cause) { setMessage((cause as Error).message); setDemoAccount(""); }
    finally { setBusy(false); }
  }

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
        <form className="surface profile-form" data-guide="portal-sign-in" onSubmit={(event) => void submit(event)}>
          <p className="eyebrow">{registering ? "Start your story" : "Welcome back"}</p>
          <h2>{registering ? "Create an Asante account" : "Sign in to Asante"}</h2>
          {!registering && demoAccounts.length > 0 && <div className="demo-login">
            <label htmlFor="demo-account">Open a demo profile</label>
            <select id="demo-account" value={demoAccount} disabled={busy} onChange={(event) => { setDemoAccount(event.target.value); void signInAsDemo(event.target.value); }}>
              <option value="">Choose a user and role…</option>
              {demoAccounts.map((account) => <option key={account.id} value={account.id}>{account.name} · {account.role}</option>)}
            </select>
            <small>Private development profiles sign in automatically. No password is shown.</small>
          </div>}
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
