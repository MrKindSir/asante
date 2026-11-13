#!/usr/bin/env python3
"""Sync TestData production clips into published MinIO keys (HubTweak HLS layout).

Package layout per video slug:
  published/{slug}/original.mp4
  published/{slug}/poster.jpg
  published/{slug}/hls/playlist.m3u8          # master
  published/{slug}/hls/1080p/playlist.m3u8
  published/{slug}/hls/1080p/segment_%03d.ts

Prefer running --build/--apply inside the API container so
``asante_api.media_process.create_hls_1080p`` is used.

Example (one story at a time):

  docker compose --env-file .env -f infrastructure/docker-compose.yml exec -T \\
    -e PYTHONPATH=/workspace \\
    -e ASANTE_MEDIA_PACKAGE_ROOT=/tmp/asante-live-media \\
    -e ASANTE_TESTDATA_PRODUCTION=/tmp/testdata-production \\
    api python /tmp/sync_live_production_media.py \\
      --build --apply --verify --prune-old-prefixes --keep-captions \\
      --slugs story-002
"""

from __future__ import annotations

import argparse
import asyncio
import mimetypes
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

# Production 45s clips → published catalogue slugs.
VIDEO_MAP: dict[str, str] = {
    "testdata-ethiopia": "ethiopia_45s.mp4",
    "testdata-idi-amin": "idi_amin_45s.mp4",
    "testdata-africa-civilizations": "africa_civilizations_45s.mp4",
    "testdata-snake-wedding": "snake_wedding_45s.mp4",
    "testdata-folktale": "folktale_45s.mp4",
    "story-002": "haile_selassie_45s.mp4",
}

AUDIO_MAP: dict[str, str] = {
    "story-001": "snake_wedding_45s.mp4",
    "story-003": "ethiopia_45s.mp4",
}

PRESERVE_AUDIO = ("story-demo",)


def _run(cmd: list[str], timeout: int = 300) -> None:
    result = subprocess.run(cmd, capture_output=True, timeout=timeout, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or b"").decode("utf-8", errors="ignore")[:600]
        raise RuntimeError(detail or f"command failed: {cmd[0]}")


def _selected_maps(slugs: set[str] | None) -> tuple[dict[str, str], dict[str, str]]:
    videos = {k: v for k, v in VIDEO_MAP.items() if not slugs or k in slugs}
    audios = {k: v for k, v in AUDIO_MAP.items() if not slugs or k in slugs}
    if slugs:
        unknown = sorted(slugs - set(videos) - set(audios) - set(PRESERVE_AUDIO))
        if unknown:
            raise SystemExit(f"Unknown slug(s): {', '.join(unknown)}")
    return videos, audios


def _create_hls_package(source: Path, hls_dir: Path) -> dict[str, Any]:
    """Build HubTweak master + 1080p package via asante_api.media_process."""
    try:
        from asante_api.media_process import create_hls_1080p
    except ImportError as error:
        raise SystemExit(
            "create_hls_1080p requires the API container (PYTHONPATH=/workspace). "
            "Copy the clip in, then run --build there."
        ) from error
    return create_hls_1080p(source, hls_dir)


def build_packages(source_dir: Path, package_root: Path, *, slugs: set[str] | None = None) -> None:
    """Create original + poster + HubTweak HLS packages from production clips."""
    if not source_dir.is_dir():
        raise SystemExit(f"Missing production source directory: {source_dir}")
    package_root.mkdir(parents=True, exist_ok=True)
    videos, audios = _selected_maps(slugs)

    for slug, filename in videos.items():
        src = source_dir / filename
        if not src.is_file():
            raise SystemExit(f"Missing clip for {slug}: {src}")
        dest = package_root / slug
        hls = dest / "hls"
        if dest.exists():
            shutil.rmtree(dest)
        hls.mkdir(parents=True)
        shutil.copy2(src, dest / "original.mp4")
        _run(
            [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-ss", "1", "-i", str(src), "-frames:v", "1", "-q:v", "3",
                "-vf", "scale=640:-2", str(dest / "poster.jpg"),
            ]
        )
        package = _create_hls_package(src, hls)
        master = hls / "playlist.m3u8"
        quality = hls / "1080p" / "playlist.m3u8"
        if not master.is_file() or not quality.is_file():
            raise SystemExit(f"HLS package incomplete for {slug}: missing master/1080p playlist")
        segments = list((hls / "1080p").glob("segment_*.ts"))
        if not segments:
            raise SystemExit(f"HLS package incomplete for {slug}: no segments")
        print(
            {
                "built": slug,
                "kind": "video",
                "bytes": (dest / "original.mp4").stat().st_size,
                "hls": {
                    "width": package.get("width"),
                    "height": package.get("height"),
                    "bitrateKbps": package.get("bitrateKbps"),
                    "segmentCount": package.get("segmentCount") or len(segments),
                },
            },
            flush=True,
        )

    for slug, filename in audios.items():
        src = source_dir / filename
        if not src.is_file():
            raise SystemExit(f"Missing clip for audio {slug}: {src}")
        dest = package_root / slug
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True)
        _run(
            [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-i", str(src), "-vn", "-ac", "2", "-ar", "44100", "-b:a", "128k",
                str(dest / "original.mp3"),
            ]
        )
        _run(
            [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-ss", "1", "-i", str(src), "-frames:v", "1", "-q:v", "3",
                "-vf", "scale=640:-2", str(dest / "poster.jpg"),
            ]
        )
        print({"built": slug, "kind": "audio", "bytes": (dest / "original.mp3").stat().st_size}, flush=True)


def _content_type(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(str(path))
    if guessed:
        return guessed
    suffix = path.suffix.lower()
    return {
        ".m3u8": "application/vnd.apple.mpegurl",
        ".ts": "video/mp2t",
        ".mp4": "video/mp4",
        ".mp3": "audio/mpeg",
        ".jpg": "image/jpeg",
        ".svg": "image/svg+xml",
    }.get(suffix, "application/octet-stream")


def _storage():
    from asante_api.storage import media_bucket, storage_client

    return storage_client(), media_bucket()


def _upload_tree(local_root: Path, object_prefix: str) -> list[str]:
    client, bucket = _storage()
    uploaded: list[str] = []
    for path in sorted(local_root.rglob("*")):
        if not path.is_file():
            continue
        # Skip macOS AppleDouble / resource-fork junk.
        if path.name.startswith("._") or path.name == ".DS_Store":
            continue
        relative = path.relative_to(local_root).as_posix()
        key = f"{object_prefix.rstrip('/')}/{relative}"
        client.fput_object(bucket, key, str(path), content_type=_content_type(path))
        uploaded.append(key)
    return uploaded


def _delete_prefix(prefix: str) -> int:
    from minio.deleteobjects import DeleteObject

    client, bucket = _storage()
    objects = [DeleteObject(obj.object_name) for obj in client.list_objects(bucket, prefix=prefix, recursive=True)]
    if not objects:
        return 0
    errors = list(client.remove_objects(bucket, objects))
    if errors:
        raise RuntimeError(f"Failed deleting {prefix}: {errors[0]}")
    return len(objects)


def plan_updates(package_root: Path, *, slugs: set[str] | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    videos, audios = _selected_maps(slugs)
    for slug in videos:
        pkg = package_root / slug
        playlist = pkg / "hls" / "playlist.m3u8"
        quality = pkg / "hls" / "1080p" / "playlist.m3u8"
        poster = pkg / "poster.jpg"
        original = pkg / "original.mp4"
        if not playlist.is_file() or not quality.is_file() or not poster.is_file() or not original.is_file():
            raise SystemExit(f"Incomplete HubTweak video package for {slug} under {pkg}")
        rows.append(
            {
                "slug": slug,
                "media_format": "video",
                "media_file": f"published/{slug}/hls/playlist.m3u8",
                "poster_file": f"published/{slug}/poster.jpg",
                "package": str(pkg),
                "prefix": f"published/{slug}/",
            }
        )
    for slug in audios:
        pkg = package_root / slug
        audio = pkg / "original.mp3"
        poster = pkg / "poster.jpg"
        if not audio.is_file() or not poster.is_file():
            raise SystemExit(f"Incomplete audio package for {slug} under {pkg}")
        rows.append(
            {
                "slug": slug,
                "media_format": "audio",
                "media_file": f"published/{slug}/original.mp3",
                "poster_file": f"published/{slug}/poster.jpg",
                "package": str(pkg),
                "prefix": f"published/{slug}/",
            }
        )
    return rows


async def apply_story_updates(rows: list[dict[str, Any]], *, clear_captions: bool) -> None:
    from sqlalchemy import update
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from asante_api.database import database_url
    from asante_api.models import StoryRecord

    engine = create_async_engine(database_url(), pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions.begin() as session:
            for row in rows:
                values: dict[str, Any] = {
                    "media_format": row["media_format"],
                    "media_file": row["media_file"],
                    "poster_file": row["poster_file"],
                    "active": True,
                    "status": "published",
                }
                if clear_captions:
                    values["caption_tracks"] = {}
                    values["transcript"] = ""
                    values["translation"] = ""
                    values["translation_language"] = ""
                result = await session.execute(
                    update(StoryRecord).where(StoryRecord.slug == row["slug"]).values(**values)
                )
                if result.rowcount == 0:
                    raise RuntimeError(f"No story row for slug={row['slug']}")
                print(
                    {
                        "updated_story": row["slug"],
                        "media_file": row["media_file"],
                        "cleared_captions": clear_captions,
                    },
                    flush=True,
                )
    finally:
        await engine.dispose()


async def verify_stories(slugs: list[str]) -> None:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from asante_api.database import database_url
    from asante_api.models import StoryRecord

    engine = create_async_engine(database_url(), pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    client, bucket = _storage()
    try:
        async with sessions() as session:
            rows = (await session.scalars(select(StoryRecord).where(StoryRecord.slug.in_(slugs)))).all()
            by_slug = {row.slug: row for row in rows}
            for slug in slugs:
                story = by_slug.get(slug)
                if story is None:
                    print({"verify": slug, "ok": False, "error": "missing_story"}, flush=True)
                    continue
                media_ok = bool(story.media_file) and client.bucket_exists(bucket)
                keys = [story.media_file, story.poster_file]
                missing = []
                for key in keys:
                    if not key:
                        missing.append("(empty)")
                        continue
                    try:
                        client.stat_object(bucket, key)
                    except Exception:
                        missing.append(key)
                quality_key = None
                segments: list[str] = []
                if story.media_file and story.media_file.endswith(".m3u8"):
                    prefix = story.media_file.rsplit("/", 1)[0] + "/"
                    quality_key = prefix + "1080p/playlist.m3u8"
                    try:
                        client.stat_object(bucket, quality_key)
                    except Exception:
                        missing.append(quality_key)
                    segments = [
                        obj.object_name
                        for obj in client.list_objects(bucket, prefix=prefix + "1080p/", recursive=True)
                        if obj.object_name.endswith(".ts")
                    ]
                    if story.media_file.endswith("/hls/playlist.m3u8") and not segments:
                        missing.append("(no 1080p segments)")
                print(
                    {
                        "verify": slug,
                        "ok": not missing and media_ok and (not story.media_file.endswith(".m3u8") or len(segments) >= 1),
                        "media_format": story.media_format,
                        "media_file": story.media_file,
                        "poster_file": story.poster_file,
                        "quality_playlist": quality_key,
                        "hls_segments": len(segments),
                        "missing_objects": missing,
                    },
                    flush=True,
                )
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        default=os.environ.get("ASANTE_TESTDATA_PRODUCTION", ""),
        help="Local TestData/production directory (build mode)",
    )
    parser.add_argument(
        "--package-root",
        default=os.environ.get("ASANTE_MEDIA_PACKAGE_ROOT", "/tmp/asante-live-media"),
        help="Directory of per-slug media packages",
    )
    parser.add_argument("--build", action="store_true", help="Build packages from --source into --package-root")
    parser.add_argument("--apply", action="store_true", help="Upload packages to MinIO and update story rows")
    parser.add_argument("--verify", action="store_true", help="Verify MinIO objects and story pointers")
    parser.add_argument(
        "--slugs",
        default="",
        help="Comma-separated story slugs (default: all VIDEO_MAP + AUDIO_MAP)",
    )
    parser.add_argument(
        "--keep-captions",
        action="store_true",
        help="Do not clear caption_tracks/transcript when applying",
    )
    parser.add_argument(
        "--prune-old-prefixes",
        action="store_true",
        help="Delete existing published/<slug>/ objects before upload",
    )
    args = parser.parse_args(argv)
    selected = {item.strip() for item in args.slugs.split(",") if item.strip()} or None

    package_root = Path(args.package_root)
    if args.build:
        source = Path(args.source)
        if not args.source:
            raise SystemExit("Pass --source /path/to/TestData/production (or ASANTE_TESTDATA_PRODUCTION)")
        build_packages(source, package_root, slugs=selected)

    rows = plan_updates(package_root, slugs=selected)
    if not args.apply and not args.verify and not args.build:
        for row in rows:
            print({"plan": row["slug"], **{k: row[k] for k in ("media_format", "media_file", "poster_file", "package")}})
        return 0

    if args.apply:
        for row in rows:
            prefix = row["prefix"]
            if args.prune_old_prefixes:
                deleted = _delete_prefix(prefix)
                print({"pruned": prefix, "objects": deleted}, flush=True)
            uploaded = _upload_tree(Path(row["package"]), prefix.rstrip("/"))
            print({"uploaded": row["slug"], "objects": len(uploaded)}, flush=True)
        asyncio.run(apply_story_updates(rows, clear_captions=not args.keep_captions))

    if args.verify or args.apply:
        verify_slugs = [row["slug"] for row in rows]
        if not selected:
            verify_slugs = verify_slugs + list(PRESERVE_AUDIO)
        asyncio.run(verify_stories(verify_slugs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
