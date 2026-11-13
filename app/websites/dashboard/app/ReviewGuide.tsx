"use client";

import { useEffect, useRef } from "react";
import { ReviewGuideStep } from "./review-guide-domain";

type Props = {
  steps: readonly ReviewGuideStep[];
  step: number;
  onMove: (step: number) => void;
  onAction?: (step: number) => void;
  canAdvance?: boolean;
};

export default function ReviewGuide({ steps, step, onMove, onAction, canAdvance = true }: Props) {
  const panel = useRef<HTMLDivElement>(null);
  const guide = steps[step];
  useEffect(() => { panel.current?.focus(); }, [step]);
  if (!guide) return null;
  const next = () => { onAction?.(step); onMove(step + 1); };
  return <div className="modal-backdrop" role="presentation">
    <section className="guide-dialog" role="dialog" aria-modal="true" aria-labelledby="review-guide-title" ref={panel} tabIndex={-1}>
      <button type="button" className="close" aria-label="Close review guide" onClick={() => onMove(steps.length)}>×</button>
      <p className="eyebrow">Asante review guide · {step + 1} of {steps.length}</p>
      <h2 id="review-guide-title">{guide.title}</h2>
      <p>{guide.text}</p>
      <div className="guide-dots">{steps.map((_, index) => <span key={index} className={index === step ? "active" : ""} />)}</div>
      <button type="button" className="button primary" disabled={!canAdvance} onClick={next}>{guide.action} →</button>
      {step > 0 && <button type="button" className="quiet" onClick={() => onMove(step - 1)}>Back</button>}
      <button type="button" className="quiet" onClick={() => onMove(steps.length)}>Skip guide</button>
    </section>
  </div>;
}
