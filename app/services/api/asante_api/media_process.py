"""Bounded ffmpeg/ffprobe media derivative processing for Asante uploads."""
from __future__ import annotations

import json
import hashlib
import random
import subprocess
import tempfile
from pathlib import Path
from typing import Any


class MediaProcessError(ValueError):
    """Raised when ffmpeg/ffprobe cannot produce a required derivative."""


def create_audio_cover(destination: str | Path, seed: str) -> dict[str, Any]:
    """Create decorative, non-documentary cover art for an audio story."""
    destination = Path(destination)
    rng = random.Random(int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16], 16))
    palettes = [
        ("#0f6b63", "#e1a751", "#f1d6a0", "#171f1d"),
        ("#355b72", "#df8a62", "#e6ebdf", "#162a33"),
        ("#49684c", "#d1a447", "#f0e3bb", "#18251c"),
        ("#765040", "#e0a559", "#f3dfbd", "#33231e"),
    ]
    background, accent, light, dark = rng.choice(palettes)
    circles = "".join(
        f'<circle cx="{rng.randint(-80, 720)}" cy="{rng.randint(-80, 920)}" r="{rng.randint(50, 230)}" fill="{rng.choice((accent, light))}" opacity="{rng.uniform(0.08, 0.25):.2f}"/>'
        for _ in range(7)
    )
    bars = "".join(
        f'<rect x="{98 + i * 20}" y="{420 - height / 2:.0f}" width="7" height="{height:.0f}" rx="3.5" fill="{light}" opacity="{rng.uniform(0.55, 0.95):.2f}"/>'
        for i in range(23)
        for height in [rng.randint(20, 150)]
    )
    destination.write_text(
        f'''<svg xmlns="http://www.w3.org/2000/svg" width="640" height="840" viewBox="0 0 640 840" role="img" aria-label="Decorative Asante audio cover art">
<defs><linearGradient id="wash" x1="0" y1="0" x2="1" y2="1"><stop stop-color="{background}"/><stop offset="1" stop-color="{dark}"/></linearGradient><pattern id="grid" width="32" height="32" patternUnits="userSpaceOnUse"><path d="M32 0H0V32" fill="none" stroke="{light}" stroke-opacity=".08"/></pattern></defs>
<rect width="640" height="840" fill="url(#wash)"/><rect width="640" height="840" fill="url(#grid)"/>{circles}
<path d="M70 420c70-150 150 150 230 0s160-150 270 0" fill="none" stroke="{accent}" stroke-width="8" stroke-linecap="round" opacity=".85"/>
<g>{bars}</g><circle cx="320" cy="420" r="132" fill="none" stroke="{light}" stroke-opacity=".3" stroke-width="2"/><circle cx="320" cy="420" r="160" fill="none" stroke="{accent}" stroke-opacity=".45" stroke-width="2"/>
<path d="M56 700h528" stroke="{light}" stroke-opacity=".36"/><text x="56" y="750" fill="{light}" font-family="sans-serif" font-size="18" letter-spacing="5">ASANTE · AUDIO STORY</text></svg>''',
        encoding="utf-8",
    )
    return {"kind": "poster", "path": str(destination), "contentType": "image/svg+xml", "generated": "decorative_audio_art"}


def run_command(args: list[str], timeout: int = 60) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(args, capture_output=True, timeout=timeout, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or b"").decode("utf-8", errors="ignore")[:400]
        raise MediaProcessError(detail or f"Command failed: {args[0]}")
    return result


def probe_media(path: str | Path) -> dict[str, Any]:
    result = run_command(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=format_name,duration,size:stream=index,codec_type,codec_name,width,height",
            "-of",
            "json",
            str(path),
        ],
        timeout=20,
    )
    info = json.loads(result.stdout)
    duration = float(info.get("format", {}).get("duration") or 0)
    streams = info.get("streams") or []
    has_video = any(stream.get("codec_type") == "video" for stream in streams)
    has_audio = any(stream.get("codec_type") == "audio" for stream in streams)
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    return {
        "duration": duration,
        "format": info.get("format", {}).get("format_name") or "",
        "hasVideo": has_video,
        "hasAudio": has_audio,
        "width": int(video.get("width") or 0) if video else 0,
        "height": int(video.get("height") or 0) if video else 0,
    }


def extract_audio_track(source: str | Path, destination: str | Path) -> dict[str, Any]:
    """Extract a normalized mono WAV speech track from audio or video."""
    source = Path(source)
    destination = Path(destination)
    probe = probe_media(source)
    if not probe["hasAudio"]:
        raise MediaProcessError("Source has no audio track to extract")
    run_command(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(source),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(destination),
        ],
        timeout=90,
    )
    if not destination.exists() or destination.stat().st_size < 100:
        raise MediaProcessError("Audio extraction produced an empty file")
    audio_probe = probe_media(destination)
    return {
        "kind": "audio_track",
        "path": str(destination),
        "contentType": "audio/wav",
        "duration": audio_probe["duration"],
        "sourceDuration": probe["duration"],
    }


def extract_poster(source: str | Path, destination: str | Path, at_seconds: float = 1.0) -> dict[str, Any]:
    source = Path(source)
    destination = Path(destination)
    probe = probe_media(source)
    if not probe["hasVideo"]:
        raise MediaProcessError("Source has no video frame for a poster")
    stamp = 0.0 if probe["duration"] < 1 else min(max(at_seconds, 0.0), max(probe["duration"] - 0.1, 0.0))
    try:
        run_command(
            [
                "ffmpeg",
                "-y",
                "-ss",
                f"{stamp:.2f}",
                "-i",
                str(source),
                "-frames:v",
                "1",
                "-q:v",
                "3",
                "-vf",
                "scale=640:-2",
                str(destination),
            ],
            timeout=60,
        )
    except MediaProcessError:
        stamp = 0.0
        run_command(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(source),
                "-frames:v",
                "1",
                "-q:v",
                "3",
                "-vf",
                "scale=640:-2",
                str(destination),
            ],
            timeout=60,
        )
    if not destination.exists() or destination.stat().st_size < 50:
        raise MediaProcessError("Poster extraction produced an empty file")
    return {
        "kind": "poster",
        "path": str(destination),
        "contentType": "image/jpeg" if destination.suffix.lower() in {".jpg", ".jpeg"} else "image/png",
        "timestamp": stamp,
        "width": min(probe["width"] or 640, 640),
    }


def extract_keyframes(source: str | Path, output_dir: str | Path, limit: int = 12) -> list[dict[str, Any]]:
    source = Path(source)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    probe = probe_media(source)
    if not probe["hasVideo"]:
        raise MediaProcessError("Source has no video frames")
    duration = max(probe["duration"], 0.1)
    count = max(1, min(limit, 4, 4 if duration >= 4 else max(1, int(duration))))
    frames: list[dict[str, Any]] = []
    for index in range(count):
        stamp = 0.0 if duration < 1 else min((duration * (index + 0.5)) / count, max(duration - 0.05, 0))
        destination = output_dir / f"keyframe_{index:02d}.jpg"
        try:
            run_command(
                [
                    "ffmpeg",
                    "-y",
                    "-ss",
                    f"{stamp:.2f}",
                    "-i",
                    str(source),
                    "-frames:v",
                    "1",
                    "-q:v",
                    "3",
                    "-vf",
                    "scale=480:-2",
                    str(destination),
                ],
                timeout=60,
            )
        except MediaProcessError:
            run_command(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(source),
                    "-frames:v",
                    "1",
                    "-q:v",
                    "3",
                    "-vf",
                    "scale=480:-2",
                    str(destination),
                ],
                timeout=60,
            )
            stamp = 0.0
        if destination.exists() and destination.stat().st_size > 50:
            frames.append(
                {
                    "kind": "keyframe",
                    "path": str(destination),
                    "contentType": "image/jpeg",
                    "timestamp": stamp,
                    "index": index,
                }
            )
    if not frames:
        raise MediaProcessError("Keyframe extraction produced no frames")
    return frames


def process_upload_file(source: str | Path, work_dir: str | Path | None = None, cover_seed: str | None = None) -> dict[str, Any]:
    """Build the AS-10 derivative set for a verified original."""
    source = Path(source)
    probe = probe_media(source)
    temporary = Path(work_dir) if work_dir else Path(tempfile.mkdtemp(prefix="asante-media-"))
    temporary.mkdir(parents=True, exist_ok=True)
    derivatives: list[dict[str, Any]] = []
    if probe["hasAudio"]:
        audio_path = temporary / "speech.wav"
        derivatives.append(extract_audio_track(source, audio_path))
    if probe["hasVideo"]:
        poster_path = temporary / "poster.jpg"
        derivatives.append(extract_poster(source, poster_path))
        derivatives.extend(extract_keyframes(source, temporary / "keyframes", limit=4))
    elif probe["hasAudio"]:
        derivatives.append(create_audio_cover(temporary / "poster.svg", cover_seed or source.name))
    if not derivatives:
        raise MediaProcessError("No audio or video streams available for processing")
    return {"probe": probe, "derivatives": derivatives, "workDir": str(temporary)}
