"use client";

import { useEffect, useRef, useState } from "react";

function fingerprint(value: unknown): string {
  return JSON.stringify(value, (key, item: unknown) => key === "version" ? undefined : item);
}

export function useDraftAutosave<T, R>({ scope, value, enabled, save, onSaved, baseline, delay = 900 }: {
  scope: string; value: T | null; enabled: boolean; save: (value: T) => Promise<R>;
  onSaved?: (result: R) => void; baseline?: T | null; delay?: number;
}) {
  const alive = useRef(true);
  const [status, setStatus] = useState("Saved");
  const latest = useRef({ value, save, onSaved });
  latest.current = { value, save, onSaved };
  const key = `${scope}:${enabled}`;
  type Session = { key: string; baseline: string; last?: R; chain: Promise<unknown> };
  const session = useRef<Session>({ key, baseline: fingerprint(baseline === undefined ? value : baseline), chain: Promise.resolve() });
  if (session.current.key !== key) session.current = { key, baseline: fingerprint(baseline === undefined ? value : baseline), chain: Promise.resolve() };
  const snapshot = fingerprint(value);
  const dirty = enabled && snapshot !== session.current.baseline;

  async function flush(): Promise<R> {
    const input = latest.current.value;
    const context = session.current;
    if (!enabled || input === null) throw new Error("This form is no longer editable.");
    const requested = fingerprint(input);
    const task = context.chain.catch(() => undefined).then(async () => {
      if (!alive.current || session.current !== context) throw new Error("The form changed before its save completed.");
      if (context.baseline === requested && context.last !== undefined) return context.last;
      setStatus("Saving…");
      try {
        const saved = await latest.current.save(input);
        if (alive.current && session.current === context) {
          context.baseline = requested; context.last = saved;
          latest.current.onSaved?.(saved);
          setStatus(fingerprint(latest.current.value) === requested ? "Saved" : "Unsaved changes");
        }
        return saved;
      } catch (cause) {
        if (alive.current && session.current === context) setStatus(`Save failed. Your edits remain here. ${(cause as Error).message}`);
        throw cause;
      }
    });
    context.chain = task;
    return task;
  }
  const flushRef = useRef(flush); flushRef.current = flush;
  useEffect(() => { setStatus(dirty ? "Unsaved changes" : "Saved"); }, [key]);
  useEffect(() => {
    if (!enabled || !dirty) return;
    setStatus("Unsaved changes");
    const timer = window.setTimeout(() => { void flushRef.current().catch(() => { /* Retain inputs and expose retry. */ }); }, delay);
    return () => window.clearTimeout(timer);
  }, [snapshot, key, enabled, delay]);
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  return { status, dirty, flush };
}
