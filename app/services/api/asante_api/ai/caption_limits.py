"""Bounded caption/transcription limits.

Live (ASANTE_AI_BACKEND=modal) defaults stay small to protect Modal spend.
Raise the ASANTE_LIVE_* env vars when ready — no code change required.

Localhost keeps the longer defaults unless ASANTE_CAPTION_SECONDS / related
vars are set explicitly.
"""

from __future__ import annotations

import os
from typing import Any


def modal_live_enabled() -> bool:
    return (os.environ.get("ASANTE_AI_BACKEND") or "").strip().lower() == "modal"


def _positive_int(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def caption_seconds() -> int:
    """Max audio seconds sent to ASR / used for caption coverage."""
    if modal_live_enabled():
        return _positive_int("ASANTE_LIVE_CAPTION_SECONDS", _positive_int("ASANTE_CAPTION_SECONDS", 45))
    return _positive_int("ASANTE_CAPTION_SECONDS", 180)


def translate_max_cues() -> int:
    """Max timed cues translated per target language."""
    if modal_live_enabled():
        return _positive_int("ASANTE_LIVE_TRANSLATE_MAX_CUES", _positive_int("ASANTE_TRANSLATE_MAX_CUES", 12))
    return _positive_int("ASANTE_TRANSLATE_MAX_CUES", 100)


def translate_batch_size() -> int:
    if modal_live_enabled():
        return _positive_int("ASANTE_LIVE_TRANSLATE_BATCH_SIZE", _positive_int("ASANTE_TRANSLATE_BATCH_SIZE", 3))
    return _positive_int("ASANTE_TRANSLATE_BATCH_SIZE", 3)


def translate_deadline_seconds() -> float:
    if modal_live_enabled():
        return float(_positive_int("ASANTE_LIVE_TRANSLATE_DEADLINE_SECONDS", _positive_int("ASANTE_TRANSLATE_DEADLINE_SECONDS", 180)))
    return float(_positive_int("ASANTE_TRANSLATE_DEADLINE_SECONDS", 90))


def clip_segments_to_caption_window(segments: list[dict[str, Any]], *, max_seconds: int | None = None, max_cues: int | None = None) -> list[dict[str, Any]]:
    """Keep only timed cues inside the configured opening window."""
    limit_seconds = float(caption_seconds() if max_seconds is None else max_seconds)
    limit_cues = translate_max_cues() if max_cues is None else max_cues
    clipped: list[dict[str, Any]] = []
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        text = segment.get("text")
        start = segment.get("start")
        end = segment.get("end")
        if not text or not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
            continue
        if float(start) >= limit_seconds:
            continue
        clipped.append(
            {
                "start": float(start),
                "end": min(float(end), limit_seconds),
                "text": str(text).strip(),
            }
        )
        if len(clipped) >= limit_cues:
            break
    return clipped


def caption_limits_snapshot() -> dict[str, Any]:
    return {
        "liveModal": modal_live_enabled(),
        "captionSeconds": caption_seconds(),
        "translateMaxCues": translate_max_cues(),
        "translateBatchSize": translate_batch_size(),
        "translateDeadlineSeconds": translate_deadline_seconds(),
    }
