"use client";

import { useEffect, useRef, useState } from "react";
import { guideSteps, TourRect, tourPosition } from "./story-domain";

export type FeatureGuideStep = {
  title: string;
  text: string;
  action: string;
  target?: string | null;
};

type FeatureGuideProps = {
  steps: readonly FeatureGuideStep[];
  step: number;
  onMove: (step: number) => void;
  eyebrow?: string;
  targetAttribute?: "tour" | "guide";
  onAction?: (step: number) => void | boolean | Promise<void | boolean>;
  onComplete?: () => void;
  placement?: "top-right" | "top-left";
  canAdvance?: boolean;
  skipLabel?: string;
  onSkip?: () => void;
};

export function FeatureGuide({ steps, step, onMove, eyebrow = "Your Asante guide", targetAttribute = "guide", onAction, onComplete, placement, canAdvance = true, skipLabel = "Skip guide", onSkip }: FeatureGuideProps) {
  const panel = useRef<HTMLDivElement>(null);
  const [rect, setRect] = useState<TourRect | null>(null);
  const [position, setPosition] = useState({ left: 14, top: 14 });
  const [advancing, setAdvancing] = useState(false);
  const guide = steps[step];

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    panel.current?.focus();
    return () => { if (previous?.isConnected) previous.focus(); };
  }, [step]);

  useEffect(() => {
    let frame = 0;
    const targetName = guide?.target;
    let target: HTMLElement | null = null;
    let lastTarget: HTMLElement | null = null;
    function measure() {
      target = targetName ? document.querySelector<HTMLElement>(`[data-${targetAttribute}="${targetName}"]`) : null;
      if (target && target !== lastTarget) target.scrollIntoView?.({ block: "nearest", inline: "nearest" });
      lastTarget = target;
      const current = target?.getBoundingClientRect();
      const view = { width: window.innerWidth, height: window.innerHeight };
      const box = current ? { left: Math.max(6, current.left - 5), top: Math.max(6, current.top - 5), right: Math.min(view.width - 6, current.right + 5), bottom: Math.min(view.height - 6, current.bottom + 5), width: current.width + 10, height: current.height + 10 } : null;
      const dimensions = panel.current?.getBoundingClientRect();
      setRect(box);
      const panelWidth = dimensions?.width || 330;
      setPosition(placement === "top-right"
        ? { left: Math.max(14, view.width - panelWidth - 20), top: 20 }
        : placement === "top-left"
          ? { left: 20, top: 20 }
          : tourPosition(box, view, { width: panelWidth, height: dimensions?.height || 300 }));
    }
    const schedule = () => { cancelAnimationFrame(frame); frame = requestAnimationFrame(measure); };
    measure();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(schedule);
    if (target) observer?.observe(target);
    if (panel.current) observer?.observe(panel.current);
    const mutations = typeof MutationObserver === "undefined" ? null : new MutationObserver(schedule);
    mutations?.observe(document.body, { childList: true, subtree: true });
    window.addEventListener("resize", schedule);
    window.addEventListener("scroll", schedule, true);
    return () => { cancelAnimationFrame(frame); observer?.disconnect(); mutations?.disconnect(); window.removeEventListener("resize", schedule); window.removeEventListener("scroll", schedule, true); };
  }, [placement, step, steps, targetAttribute, guide?.target]);

  if (!guide) return null;
  async function next() {
    if (advancing) return;
    setAdvancing(true);
    try {
      const shouldMove = await onAction?.(step);
      if (shouldMove === false) return;
      onMove(step + 1);
      if (step + 1 >= steps.length) onComplete?.();
    } catch {
      // Keep the guide on the current step when its action cannot complete.
    } finally {
      setAdvancing(false);
    }
  }
  return <div className="tour-layer">
    {rect ? <><div className="tour-shade" style={{ left: 0, top: 0, right: 0, height: rect.top }} /><div className="tour-shade" style={{ left: 0, top: rect.top, width: rect.left, height: rect.bottom - rect.top }} /><div className="tour-shade" style={{ left: rect.right, right: 0, top: rect.top, height: rect.bottom - rect.top }} /><div className="tour-shade" style={{ left: 0, right: 0, top: rect.bottom, bottom: 0 }} /><div className="tour-spotlight" style={{ left: rect.left, top: rect.top, width: rect.right - rect.left, height: rect.bottom - rect.top }} /></> : <div className="tour-shade" style={{ inset: 0 }} />}
    <div className={"guide-dialog tour-popover " + (step === 0 ? "tour-welcome" : "")} style={{ left: position.left, top: position.top }} role="dialog" aria-modal={step === 0 ? true : undefined} aria-labelledby="guide-title" ref={panel} tabIndex={-1} onKeyDown={(event) => {
      if (event.key === "Escape") onMove(steps.length);
      if (event.key === "Tab" && step === 0) {
        const controls = panel.current?.querySelectorAll<HTMLElement>("button, a");
        if (!controls?.length) return;
        const first = controls[0]; const last = controls[controls.length - 1];
        if (event.shiftKey && (document.activeElement === first || document.activeElement === panel.current)) { event.preventDefault(); last.focus(); }
        if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    }}>
      <button className="close" aria-label="Close guide" onClick={() => onMove(steps.length)}>×</button>
      <p className="eyebrow">{eyebrow} · {step + 1} of {steps.length}</p>
      <h2 id="guide-title">{guide.title}</h2><p>{guide.text}</p>
      <div className="guide-dots">{steps.map((_, index) => <span key={index} className={step === index ? "active" : ""} />)}</div>
      <button className="button primary" disabled={!canAdvance || advancing} onClick={() => void next()}>{advancing ? "Saving…" : `${guide.action} →`}</button>
      {step > 0 && <button className="quiet" onClick={() => onMove(step - 1)}>Back</button>}
      <button className="quiet" onClick={() => { if (onSkip) onSkip(); else onMove(steps.length); }}>{skipLabel}</button>
    </div>
  </div>;
}

const mapTargets = [null, "search", "location", "story", "contribute"];

export default function GuidedTour({ step, onMove, onLocate, onOpenStory }: { step: number; onMove: (step: number) => void; onLocate: () => void; onOpenStory: () => void }) {
  const steps = guideSteps.map((guide, index) => ({ ...guide, target: mapTargets[index] }));
  return <FeatureGuide
    steps={steps}
    step={step}
    onMove={onMove}
    targetAttribute="tour"
    onAction={(current) => { if (current === 2) onLocate(); if (current === 3) onOpenStory(); }}
    skipLabel={step === 2 ? "Continue without location" : "Skip guide"}
    onSkip={() => onMove(step === 2 ? 3 : steps.length)}
  />;
}
