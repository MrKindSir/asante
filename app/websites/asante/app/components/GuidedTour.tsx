"use client";

import { useEffect, useRef, useState } from "react";
import { guideSteps, TourRect, tourPosition } from "./story-domain";

const targets = [null, "search", "location", "story", "contribute"];
type Props = { step: number; onMove: (step: number) => void; onLocate: () => void; onOpenStory: () => void };

export default function GuidedTour({ step, onMove, onLocate, onOpenStory }: Props) {
  const panel = useRef<HTMLDivElement>(null);
  const [rect, setRect] = useState<TourRect | null>(null);
  const [position, setPosition] = useState({ left: 14, top: 14 });
  const [viewport, setViewport] = useState({ width: 0, height: 0 });
  const guide = guideSteps[step];

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    panel.current?.focus();
    return () => { if (previous?.isConnected) previous.focus(); };
  }, [step]);

  useEffect(() => {
    let frame = 0;
    const targetName = targets[step];
    let target = targetName ? document.querySelector<HTMLElement>('[data-tour="' + targetName + '"]') : null;
    if (!target && targetName === "story") target = document.querySelector<HTMLElement>('[data-tour="story-list"]');
    target?.scrollIntoView({ block: "nearest", inline: "nearest" });
    function measure() {
      const current = target?.getBoundingClientRect();
      const view = { width: window.innerWidth, height: window.innerHeight };
      const box = current ? { left: Math.max(6, current.left - 5), top: Math.max(6, current.top - 5), right: Math.min(view.width - 6, current.right + 5), bottom: Math.min(view.height - 6, current.bottom + 5), width: current.width + 10, height: current.height + 10 } : null;
      const dimensions = panel.current?.getBoundingClientRect();
      setRect(box); setViewport(view);
      setPosition(tourPosition(box, view, { width: dimensions?.width || 330, height: dimensions?.height || 300 }));
    }
    const schedule = () => { cancelAnimationFrame(frame); frame = requestAnimationFrame(measure); };
    measure();
    const observer = new ResizeObserver(schedule);
    if (target) observer.observe(target);
    if (panel.current) observer.observe(panel.current);
    window.addEventListener("resize", schedule);
    window.addEventListener("scroll", schedule, true);
    return () => { cancelAnimationFrame(frame); observer.disconnect(); window.removeEventListener("resize", schedule); window.removeEventListener("scroll", schedule, true); };
  }, [step]);

  function next() {
    if (step === 2) onLocate();
    if (step === 3) onOpenStory();
    onMove(step + 1);
  }
  return <div className="tour-layer">
    {rect ? <><div className="tour-shade" style={{ left: 0, top: 0, right: 0, height: rect.top }} /><div className="tour-shade" style={{ left: 0, top: rect.top, width: rect.left, height: rect.bottom - rect.top }} /><div className="tour-shade" style={{ left: rect.right, right: 0, top: rect.top, height: rect.bottom - rect.top }} /><div className="tour-shade" style={{ left: 0, right: 0, top: rect.bottom, bottom: 0 }} /><div className="tour-spotlight" style={{ left: rect.left, top: rect.top, width: rect.right - rect.left, height: rect.bottom - rect.top }} /></> : <div className="tour-shade" style={{ inset: 0 }} />}
    <div className={"guide-dialog tour-popover " + (step === 0 ? "tour-welcome" : "")} style={{ left: position.left, top: position.top }} role="dialog" aria-modal={step === 0 ? true : undefined} aria-labelledby="guide-title" ref={panel} tabIndex={-1} onKeyDown={(event) => {
      if (event.key === "Escape") onMove(5);
      if (event.key === "Tab" && step === 0) {
        const controls = panel.current?.querySelectorAll<HTMLElement>("button, a");
        if (!controls?.length) return;
        const first = controls[0]; const last = controls[controls.length - 1];
        if (event.shiftKey && (document.activeElement === first || document.activeElement === panel.current)) { event.preventDefault(); last.focus(); }
        if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    }}>
      <button className="close" aria-label="Close guide" onClick={() => onMove(5)}>×</button>
      <p className="eyebrow">Your Asante guide · {step + 1} of 5</p>
      <h2 id="guide-title">{guide.title}</h2><p>{guide.text}</p>
      <div className="guide-dots">{guideSteps.map((_, index) => <span key={index} className={step === index ? "active" : ""} />)}</div>
      <button className="button primary" onClick={next}>{guide.action} →</button>
      {step === 4 && <a className="button secondary" href="/asante/portal/">Create a profile</a>}
      {step > 0 && <button className="quiet" onClick={() => onMove(step - 1)}>Back</button>}
      <button className="quiet" onClick={() => step === 2 ? onMove(3) : onMove(5)}>{step === 2 ? "Continue without location" : "Skip guide"}</button>
    </div>
  </div>;
}
