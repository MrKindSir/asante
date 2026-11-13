"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { attachMedia } from "./media-attach";
import { CaptionTrack, Story, languageNames } from "./story-domain";
import { openWorkspace, savePreference } from "./workspace-client";

export default function StoryPlayer({
  story,
  lowData,
  autoPlay = false,
  onAutoPlayDismiss,
}: {
  story: Story;
  lowData: boolean;
  autoPlay?: boolean;
  onAutoPlayDismiss?: () => void;
}) {
  const media = useRef<HTMLMediaElement | null>(null);
  const playButton = useRef<HTMLButtonElement | null>(null);
  const closeButton = useRef<HTMLButtonElement | null>(null);
  const autoPlayWasEnabled = useRef(autoPlay);
  const lastSaved = useRef(0);
  const [started, setStarted] = useState(autoPlay);
  const [videoOpen, setVideoOpen] = useState(autoPlay && story.media_format === "video");
  const [captionsOpen, setCaptionsOpen] = useState(false);
  const [captionTracks, setCaptionTracks] = useState<CaptionTrack[]>([]);
  const [translationStatus, setTranslationStatus] = useState<Record<string, string>>({});
  const [captionStatus, setCaptionStatus] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [captionLanguage, setCaptionLanguage] = useState("");
  const [currentTime, setCurrentTime] = useState(0);
  const [error, setError] = useState("");
  const key = "asante.playback." + story.id;
  const isVideo = story.media_format === "video";
  const activeCaptionTrack = captionTracks.find((track) => track.language === captionLanguage);
  const activeCaption = activeCaptionTrack?.cues.find((cue) => currentTime >= cue.start && currentTime < cue.end)?.text || "";
  const captionButtonLabel = captionStatus === "loading" ? "Loading captions…" : captionTracks.length ? activeCaptionTrack ? `Captions · ${activeCaptionTrack.label}` : "Show captions" : captionStatus === "error" ? "Captions could not load" : "No captions available";
  const unavailableLanguages = Object.entries(translationStatus).filter(([, state]) => state === "unavailable").map(([language]) => languageNames[language] || language);
  const captionHelp = (captionTracks.length ? "Caption text follows playback time." : captionStatus === "error" ? "Could not load this story’s timed caption choices." : captionStatus === "loading" ? "Checking this story’s available caption tracks…" : "No timed caption tracks are available for this story.") + (unavailableLanguages.length ? ` Translation unavailable: ${unavailableLanguages.join(", ")}.` : "");

  useEffect(() => {
    if (autoPlay) {
      setStarted(true);
      if (isVideo) setVideoOpen(true);
    } else if (autoPlayWasEnabled.current) {
      media.current?.pause();
      setStarted(false);
      setVideoOpen(false);
    }
    autoPlayWasEnabled.current = autoPlay;
  }, [autoPlay, isVideo]);

  useEffect(() => {
    // Video source attachment is managed by the popup effect below. Let the
    // native video controls (or the autoPlay attribute after attachment) start it.
    if (!started || isVideo) return;
    media.current?.play().catch(() => setError("Your browser blocked automatic playback. Press Play to start this story."));
  }, [started, autoPlay, isVideo]);

  useEffect(() => {
    if (videoOpen) closeButton.current?.focus();
  }, [videoOpen]);

  useEffect(() => {
    if (!videoOpen || !isVideo || !story.media_url || !(media.current instanceof HTMLVideoElement)) return;
    const element = media.current;
    const detach = attachMedia(element, story.media_url, () => setError("This recording could not be loaded. Please try again."));
    return () => {
      element.pause();
      detach();
    };
  }, [story.media_url, videoOpen, isVideo]);

  useEffect(() => {
    if (isVideo ? !videoOpen : !started) return;
    const controller = new AbortController();
    setCaptionStatus("loading");
    fetch(`/asante/api/v1/stories/${encodeURIComponent(story.id)}/captions`, { cache: "no-store", signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error("Caption track request failed");
        const payload: unknown = await response.json();
        const items = typeof payload === "object" && payload !== null && "items" in payload ? payload.items : null;
        const tracks = Array.isArray(items) ? items.filter(isCaptionTrack) : [];
        const states = typeof payload === "object" && payload !== null && "translationStatus" in payload ? payload.translationStatus : null;
        setTranslationStatus(typeof states === "object" && states !== null && !Array.isArray(states) ? Object.fromEntries(Object.entries(states).filter((entry): entry is [string, { status: string }] => typeof entry[1] === "object" && entry[1] !== null && "status" in entry[1] && typeof entry[1].status === "string").map(([language, item]) => [language, item.status])) : {});
        setCaptionTracks(tracks);
        setCaptionLanguage((current) => tracks.some((track) => track.language === current) ? current : "");
        setCaptionStatus("ready");
      })
      .catch((cause: unknown) => {
        if (cause instanceof DOMException && cause.name === "AbortError") return;
        setCaptionTracks([]);
        setTranslationStatus({});
        setCaptionLanguage("");
        setCaptionStatus("error");
      });
    return () => controller.abort();
  }, [story.id, videoOpen, started, isVideo]);

  useEffect(() => {
    if (!videoOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeVideo();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [videoOpen, autoPlay]);

  function restore() {
    void openWorkspace().then((workspace) => {
      const saved = Number(workspace.preferences[key]);
      if (media.current && Number.isFinite(saved) && saved > 0 && saved < media.current.duration) {
        media.current.currentTime = saved;
        setCurrentTime(saved);
      }
    }).catch(() => undefined);
  }

  function save() {
    if (!media.current || Math.abs(media.current.currentTime - lastSaved.current) < 5) return;
    lastSaved.current = media.current.currentTime;
    void savePreference(key, String(media.current.currentTime)).catch(() => undefined);
  }

  function startPlayback() {
    setError("");
    if (isVideo) {
      setVideoOpen(true);
    } else {
      setStarted(true);
    }
  }

  function closeVideo() {
    media.current?.pause();
    setVideoOpen(false);
    setStarted(false);
    setCaptionsOpen(false);
    if (autoPlay) onAutoPlayDismiss?.();
    requestAnimationFrame(() => playButton.current?.focus());
  }

  function onTimeUpdate() {
    if (!media.current) return;
    setCurrentTime(media.current.currentTime);
    save();
  }

  if (!story.media_url) return <div className="media-empty">
    {story.contributor_profile_url && <a href={story.contributor_profile_url}>Contributor profile: {story.contributor_name}</a>}
    <p>Original media has not been attached yet.</p><small>Choose the audio demo to try playback.</small>
  </div>;

  const mediaProps = {
    controls: true,
    autoPlay: autoPlay && started,
    preload: autoPlay ? "metadata" as const : "none" as const,
    onLoadedMetadata: restore,
    onTimeUpdate,
    onEnded: () => { void savePreference(key, null).catch(() => undefined); },
    onError: () => setError("This recording could not be loaded. Please try again."),
  };

  return <section className="story-player" aria-label="Story playback">
    {story.contributor_profile_url && <a href={story.contributor_profile_url}>Contributor profile: {story.contributor_name}</a>}
    {isVideo ? <button ref={playButton} className="button primary" onClick={startPlayback}>
      {videoOpen && started ? "Video is open" : "▶ Play video"}
    </button> : !started ? <button className="button primary" onClick={startPlayback}>▶ Play story</button> :
      <audio ref={(element) => { media.current = element; }} src={story.media_url} {...mediaProps} />}
    {lowData && <small>{isVideo ? `Video loads after Play${autoPlay ? " or enabled nearby auto-play" : ""}. Adaptive quality is not available yet.` : `Audio loads after Play${autoPlay ? " or enabled nearby auto-play" : ""}.`}</small>}
    {!isVideo && started && <div className="audio-caption-panel">
      <div className="video-caption-picker">
        <button type="button" className="button secondary" aria-expanded={captionsOpen} disabled={!captionTracks.length} onClick={() => setCaptionsOpen((open) => !open)}>{captionButtonLabel}</button>
        {captionsOpen && <div className="video-caption-menu" role="group" aria-label="Choose audio captions">
          <button type="button" className={!captionLanguage ? "active" : ""} onClick={() => { setCaptionLanguage(""); setCaptionsOpen(false); }}>Captions off</button>
          {captionTracks.map((track) => <button type="button" key={track.language} className={captionLanguage === track.language ? "active" : ""} onClick={() => { setCaptionLanguage(track.language); setCaptionsOpen(false); }}>{track.label}</button>)}
        </div>}
      </div>
      <small>{captionHelp}</small>
    </div>}
    {story.is_demo && <p className="muted">Original synthetic demo narration · not a verified heritage account.</p>}
    {error && <p role="alert">{error} <button className="quiet" onClick={() => { setError(""); startPlayback(); }}>Retry</button></p>}
    {story.transcript && <details><summary>Read the transcript</summary><p>{story.transcript}</p></details>}

    {!isVideo && started && activeCaption && typeof document !== "undefined" && createPortal(
      <div className="audio-caption-overlay" role="status" aria-live="polite" aria-atomic="true">{activeCaption}</div>,
      document.body,
    )}

    {isVideo && videoOpen && createPortal(<div className="video-playback-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) closeVideo();
    }}>
      <section className="video-playback-popup" role="dialog" aria-modal="true" aria-labelledby="video-playback-title">
        <header className="video-playback-bar">
          <div><p className="eyebrow">Video story</p><h2 id="video-playback-title">{story.title}</h2></div>
          <button ref={closeButton} type="button" className="video-playback-close" aria-label="Close video player" onClick={closeVideo}>×</button>
        </header>
        <div className="video-playback-frame">
          <video ref={(element) => { media.current = element; }} poster={story.poster_url || undefined} playsInline onPlay={() => setStarted(true)} {...mediaProps} />
          {activeCaption && <div className="video-caption-overlay" aria-live="polite" aria-atomic="true">{activeCaption}</div>}
        </div>
        <div className="video-playback-controls">
          <div className="video-caption-picker">
            <button type="button" className="button secondary" aria-expanded={captionsOpen} disabled={!captionTracks.length} onClick={() => setCaptionsOpen((open) => !open)}>
              {captionButtonLabel}
            </button>
            {captionsOpen && <div className="video-caption-menu" role="group" aria-label="Choose translated captions">
              <button type="button" className={!captionLanguage ? "active" : ""} onClick={() => { setCaptionLanguage(""); setCaptionsOpen(false); }}>Captions off</button>
              {captionTracks.map((track: CaptionTrack) => <button type="button" key={track.language} className={captionLanguage === track.language ? "active" : ""} onClick={() => { setCaptionLanguage(track.language); setCaptionsOpen(false); }}>{track.label}</button>)}
            </div>}
          </div>
          <small>{captionHelp}</small>
        </div>
        {error && <p role="alert" className="video-playback-error">{error}</p>}
      </section>
    </div>, document.body)}
  </section>;
}

function isCaptionTrack(value: unknown): value is CaptionTrack {
  if (typeof value !== "object" || value === null || !("language" in value) || !("label" in value) || !("cues" in value)) return false;
  const track = value as { language: unknown; label: unknown; cues: unknown };
  return typeof track.language === "string" && typeof track.label === "string" && Array.isArray(track.cues) && track.cues.every((cue) => {
    if (typeof cue !== "object" || cue === null || !("start" in cue) || !("end" in cue) || !("text" in cue)) return false;
    const caption = cue as { start: unknown; end: unknown; text: unknown };
    return typeof caption.start === "number" && typeof caption.end === "number" && caption.start >= 0 && caption.end > caption.start && typeof caption.text === "string";
  });
}
