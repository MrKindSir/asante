"use client";

import { useState } from "react";

type Cue = { start: number; end: number; text: string };
type Track = { language: string; label: string; cues: Cue[] };

export default function ReviewVideoPlayer({ source, tracks, format = "video" }: { source: string; tracks: Track[]; format?: "video" | "audio" }) {
  const [time, setTime] = useState(0);
  const [language, setLanguage] = useState("");
  const selected = tracks.find((track) => track.language === language);
  const cue = selected?.cues.find((item) => time >= item.start && time < item.end);
  return <div className="review-video-player">
    {format === "video" ? <div className="review-video-frame">
      <video src={source} controls preload="metadata" playsInline onTimeUpdate={(event) => setTime(event.currentTarget.currentTime)} />
      {cue && <div className="review-video-caption">{cue.text}</div>}
    </div> : <>
      <audio src={source} controls preload="metadata" onTimeUpdate={(event) => setTime(event.currentTarget.currentTime)} />
      {cue && <p className="review-audio-caption">{cue.text}</p>}
    </>}
    <label>Caption draft
      <select value={language} onChange={(event) => setLanguage(event.target.value)}>
        <option value="">Off</option>
        {tracks.map((track) => <option key={track.language} value={track.language}>{track.label}</option>)}
      </select>
    </label>
    <small>{tracks.length ? "Timed AI drafts for human review; verify names and translations." : "No timed transcription is available yet. Check the processing jobs below."}</small>
  </div>;
}
