"""One-time, explicit backfill of timed drafts for published audio and video."""

from __future__ import annotations

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
from .jobs import _optional_whisper_transcribe, translate_caption_segments


LANGUAGE_NAMES = {"en": "English", "zu": "isiZulu", "st": "Sesotho"}


def speech_cues(story_slug: str, media_file: str) -> tuple[str, list[dict[str, Any]]]:
    with tempfile.TemporaryDirectory(prefix="asante-caption-backfill-") as directory:
        temporary = Path(directory)
        wav = temporary / "speech.wav"
        if media_file.endswith(".m3u8"):
            origin = os.environ.get("ASANTE_INTERNAL_PUBLIC_ORIGIN", "http://proxy").rstrip("/")
            source = f"{origin}/asante/api/v1/stories/{story_slug}/hls/index.m3u8"
        else:
            original = temporary / "original"
            storage_client().fget_object(media_bucket(), media_file, str(original))
            source = str(original)
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", source,
             "-t", "180", "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)],
            check=True, timeout=120,
        )
        transcript = _optional_whisper_transcribe(wav)
        if not transcript or not transcript.get("segments"):
            return "", []
        return str(transcript.get("language") or "en"), transcript["segments"]


def add_translation_drafts(tracks: list[dict[str, Any]], state: dict[str, Any]) -> None:
    source = next((track for track in tracks if "AI transcript draft" in track["label"]), None)
    if source is None:
        return
    segments = source["cues"]
    for target in LANGUAGE_NAMES:
        if target == source["language"]:
            continue
        existing = next((track for track in tracks if track["language"] == target), None)
        covered = len(existing["cues"]) if existing else 0
        if covered >= len(segments):
            state[target] = {"status": "draft", "coveredCues": covered, "totalCues": len(segments), "provider": state.get(target, {}).get("provider") or "stored_draft", "reason": ""}
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
            "coveredCues": len(cues), "totalCues": len(segments),
            "provider": response.get("provider") or "unavailable",
            "reason": response.get("error") or "",
        }


async def backfill() -> None:
    engine = create_async_engine(database_url())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            rows = (await session.scalars(select(StoryRecord).where(
                StoryRecord.status == "published", StoryRecord.active.is_(True),
                StoryRecord.media_format.in_(["audio", "video"]), StoryRecord.media_file.is_not(None),
            ))).all()
            candidates = [(row.slug, row.media_file, row.caption_tracks) for row in rows]
        for slug, media_file, current in candidates:
            tracks = public_caption_tracks(current)
            if not tracks:
                try:
                    language, cues = await asyncio.to_thread(speech_cues, slug, media_file)
                except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired, RuntimeError) as error:
                    print({"story": slug, "status": "unavailable", "error": type(error).__name__})
                    continue
                if not cues:
                    print({"story": slug, "status": "no_speech"})
                    continue
                tracks = [{"language": language, "label": f"{LANGUAGE_NAMES.get(language, language)} · AI transcript draft (first 3 min)", "cues": cues}]
            if not any("AI transcript draft" in track["label"] for track in tracks):
                print({"story": slug, "status": "human_tracks_preserved"})
                continue
            state = dict(current.get("translationStatus") or {}) if isinstance(current, dict) else {}
            await asyncio.to_thread(add_translation_drafts, tracks, state)
            async with factory() as session:
                async with session.begin():
                    story = await session.scalar(select(StoryRecord).where(StoryRecord.slug == slug).with_for_update())
                    if story is None or public_caption_tracks(story.caption_tracks) != public_caption_tracks(current):
                        print({"story": slug, "status": "changed_during_backfill"})
                        continue
                    story.caption_tracks = {"tracks": public_caption_tracks(tracks), "translationStatus": state}
            print({"story": slug, "tracks": [(track["language"], len(track["cues"])) for track in tracks], "translationStatus": {key: value["status"] for key, value in state.items()}})
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(backfill())
