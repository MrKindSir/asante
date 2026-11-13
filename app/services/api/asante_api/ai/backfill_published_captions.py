"""Explicit backfill of timed drafts for published audio and video.

Usage (API container):

  python -m asante_api.ai.backfill_published_captions
  python -m asante_api.ai.backfill_published_captions --force
  python -m asante_api.ai.backfill_published_captions --force --slugs story-002,testdata-idi-amin
"""

from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from ..catalogue import public_caption_tracks
from ..database import database_url
from ..models import StoryRecord
from ..storage import media_bucket, storage_client
from .caption_limits import caption_seconds, clip_segments_to_caption_window, translate_max_cues
from .jobs import _optional_whisper_transcribe, translate_caption_segments


LANGUAGE_NAMES = {"en": "English", "zu": "isiZulu", "st": "Sesotho"}


def _source_object_key(media_file: str) -> str:
    """Prefer a progressive original over HLS for offline ffmpeg/Whisper."""
    if not media_file.endswith(".m3u8"):
        return media_file
    prefix = media_file.rsplit("/", 1)[0]
    # published/<slug>/hls/index.m3u8 -> published/<slug>/original.mp4
    parent = prefix.rsplit("/", 1)[0] if prefix.endswith("/hls") or prefix.endswith("hls") else prefix
    if prefix.endswith("/hls"):
        parent = prefix[: -len("/hls")]
    client = storage_client()
    bucket = media_bucket()
    for name in ("original.mp4", "original.mp3", "original"):
        key = f"{parent}/{name}"
        try:
            client.stat_object(bucket, key)
            return key
        except Exception:
            continue
    return media_file


def speech_cues(story_slug: str, media_file: str) -> tuple[str, list[dict[str, Any]]]:
    window = caption_seconds()
    with tempfile.TemporaryDirectory(prefix="asante-caption-backfill-") as directory:
        temporary = Path(directory)
        wav = temporary / "speech.wav"
        object_key = _source_object_key(media_file)
        print({"story": story_slug, "status": "extracting", "objectKey": object_key, "window": window}, flush=True)
        if object_key.endswith(".m3u8"):
            origin = os.environ.get("ASANTE_INTERNAL_PUBLIC_ORIGIN", "http://proxy").rstrip("/")
            source = f"{origin}/asante/api/v1/stories/{story_slug}/hls/index.m3u8"
        else:
            suffix = Path(object_key).suffix or ".bin"
            original = temporary / f"original{suffix}"
            storage_client().fget_object(media_bucket(), object_key, str(original))
            source = str(original)
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                "-i", source, "-t", str(window), "-vn", "-ac", "1", "-ar", "16000",
                "-c:a", "pcm_s16le", str(wav),
            ],
            check=True,
            timeout=max(120, window + 60),
        )
        print({"story": story_slug, "status": "transcribing", "wavBytes": wav.stat().st_size}, flush=True)
        transcript = _optional_whisper_transcribe(wav)
        if not transcript or not transcript.get("segments"):
            return "", []
        segments = clip_segments_to_caption_window(
            transcript["segments"],
            max_seconds=window,
            max_cues=max(translate_max_cues() * 4, translate_max_cues()),
        )
        return str(transcript.get("language") or "en"), segments


def add_translation_drafts(tracks: list[dict[str, Any]], state: dict[str, Any]) -> None:
    source = next((track for track in tracks if "AI transcript draft" in track["label"]), None)
    if source is None:
        return
    segments = clip_segments_to_caption_window(source["cues"])
    source["cues"] = segments
    for target in LANGUAGE_NAMES:
        if target == source["language"]:
            continue
        existing = next((track for track in tracks if track["language"] == target), None)
        covered = len(existing["cues"]) if existing else 0
        if covered >= len(segments):
            state[target] = {
                "status": "draft",
                "coveredCues": covered,
                "totalCues": len(segments),
                "provider": state.get(target, {}).get("provider") or "stored_draft",
                "reason": "",
            }
            continue
        new_cues, response = translate_caption_segments(segments[covered:], source["language"], target)
        cues = (existing["cues"] if existing else []) + new_cues
        if len(cues) >= 2:
            label = f"{LANGUAGE_NAMES[target]} · AI translation draft"
            if len(cues) < len(segments):
                label = f"{LANGUAGE_NAMES[target]} · partial AI draft (to {cues[-1]['end']:.0f}s)"
            replacement = {"language": target, "label": label, "cues": cues}
            if existing:
                tracks[tracks.index(existing)] = replacement
            else:
                tracks.append(replacement)
        state[target] = {
            "status": "draft" if len(cues) == len(segments) else "partial" if len(cues) >= 2 else "unavailable",
            "coveredCues": len(cues),
            "totalCues": len(segments),
            "provider": response.get("provider") or "unavailable",
            "reason": response.get("error") or "",
        }


async def backfill(*, force: bool = False, slugs: set[str] | None = None) -> None:
    engine = create_async_engine(database_url())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            query = select(StoryRecord).where(
                StoryRecord.status == "published",
                StoryRecord.active.is_(True),
                StoryRecord.media_format.in_(["audio", "video"]),
                StoryRecord.media_file.is_not(None),
            )
            if slugs:
                query = query.where(StoryRecord.slug.in_(sorted(slugs)))
            rows = (await session.scalars(query)).all()
            candidates = [(row.slug, row.media_file, row.caption_tracks) for row in rows]
        print({"candidates": len(candidates), "force": force, "captionSeconds": caption_seconds()}, flush=True)
        for slug, media_file, current in candidates:
            tracks = [] if force else public_caption_tracks(current)
            if not tracks:
                try:
                    language, cues = await asyncio.to_thread(speech_cues, slug, media_file)
                except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired, RuntimeError) as error:
                    print({"story": slug, "status": "unavailable", "error": type(error).__name__, "detail": str(error)[:200]})
                    continue
                if not cues:
                    print({"story": slug, "status": "no_speech"})
                    continue
                tracks = [
                    {
                        "language": language,
                        "label": f"{LANGUAGE_NAMES.get(language, language)} · AI transcript draft (first {caption_seconds()}s)",
                        "cues": cues,
                    }
                ]
            if not any("AI transcript draft" in track["label"] for track in tracks):
                print({"story": slug, "status": "human_tracks_preserved"})
                continue
            state: dict[str, Any] = {} if force else (dict(current.get("translationStatus") or {}) if isinstance(current, dict) else {})
            if force:
                # Drop prior translation tracks so targets are rebuilt against the new transcript.
                tracks = [track for track in tracks if "AI transcript draft" in track["label"]]
            await asyncio.to_thread(add_translation_drafts, tracks, state)
            async with factory() as session:
                async with session.begin():
                    story = await session.scalar(select(StoryRecord).where(StoryRecord.slug == slug).with_for_update())
                    if story is None:
                        print({"story": slug, "status": "missing"})
                        continue
                    if not force and public_caption_tracks(story.caption_tracks) != public_caption_tracks(current):
                        print({"story": slug, "status": "changed_during_backfill"})
                        continue
                    english = next((track for track in tracks if track.get("language") == "en"), tracks[0])
                    story.transcript = " ".join(cue["text"] for cue in english.get("cues") or [] if cue.get("text"))
                    zu = next((track for track in tracks if track.get("language") == "zu"), None)
                    if zu and zu.get("cues"):
                        story.translation = " ".join(cue["text"] for cue in zu["cues"] if cue.get("text"))
                        story.translation_language = "zu"
                    story.caption_tracks = {"tracks": public_caption_tracks(tracks), "translationStatus": state}
            print(
                {
                    "story": slug,
                    "status": "ok",
                    "tracks": [(track["language"], len(track["cues"])) for track in tracks],
                    "translationStatus": {key: value.get("status") for key, value in state.items()},
                }
            )
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Re-transcribe and rebuild translation drafts")
    parser.add_argument("--slugs", default="", help="Comma-separated story slugs (default: all published with media)")
    args = parser.parse_args(argv)
    selected = {item.strip() for item in args.slugs.split(",") if item.strip()} or None
    asyncio.run(backfill(force=args.force, slugs=selected))


if __name__ == "__main__":
    main()
