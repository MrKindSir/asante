"use client";

import { useEffect, useRef } from "react";
import { attachMedia } from "./media-attach";
import { Story } from "./story-domain";

export function canPreviewStoryVideo(story: Story): boolean {
  return story.media_format === "video" && Boolean(story.media_url);
}

export default function StoryArtPreview({
  story,
  artClass,
  playing,
}: {
  story: Story;
  artClass: string;
  playing: boolean;
}) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const showVideo = playing && canPreviewStoryVideo(story);

  useEffect(() => {
    const element = videoRef.current;
    const url = story.media_url;
    if (!showVideo || !element || !url) return;
    element.muted = true;
    element.defaultMuted = true;
    element.playsInline = true;
    element.loop = true;
    const detach = attachMedia(element, url, () => undefined);
    void element.play().catch(() => undefined);
    return () => {
      element.pause();
      detach();
    };
  }, [showVideo, story.media_url, story.id]);

  return (
    <span className={"story-art " + artClass} aria-hidden="true">
      {showVideo ? (
        <video
          ref={videoRef}
          muted
          loop
          playsInline
          preload="metadata"
          poster={story.poster_url || undefined}
        />
      ) : story.poster_url ? (
        <img src={story.poster_url} alt="" loading="lazy" decoding="async" />
      ) : (
        <svg className="story-art-fallback" viewBox="0 0 54 72" aria-hidden="true">
          <circle cx="27" cy="25" r="16" fill="none" stroke="currentColor" strokeOpacity=".35" />
          <path d="M9 26c5-14 9 14 14 0s9-14 14 0 8 9 10 0M11 54h32M11 60h23" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
      )}
    </span>
  );
}
