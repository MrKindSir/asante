"use client";

type Props = {
  message: string;
  onDismiss: () => void;
  className?: string;
};

export default function FeedbackTicker({ message, onDismiss, className = "" }: Props) {
  if (!message) return null;

  return (
    <div className={`feedback-ticker ${className}`}>
      <span className="feedback-ticker-label">Update</span>
      <span className="visually-hidden" role="status" aria-live="polite" aria-atomic="true">{message}</span>
      <div className="feedback-ticker-window" aria-hidden="true">
        <div className="feedback-ticker-track" key={message} style={{ animationDuration: `${Math.max(20, message.length / 5)}s` }}>
          <span className="feedback-ticker-item">{message}</span>
          <span className="feedback-ticker-item">{message}</span>
        </div>
      </div>
      <button type="button" className="feedback-ticker-close" onClick={onDismiss} aria-label="Dismiss feedback" title="Dismiss feedback">
        <span aria-hidden="true">×</span>
      </button>
    </div>
  );
}
