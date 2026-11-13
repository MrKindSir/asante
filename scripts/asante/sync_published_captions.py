#!/usr/bin/env python3
"""Export/import published story caption bundles (transcript + caption_tracks).

Run inside the API container (PYTHONPATH=/workspace).

  # On localhost after local backfill:
  python /tmp/sync_published_captions.py export --out /tmp/captions.json

  # On live:
  python /tmp/sync_published_captions.py import --in /tmp/captions.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from asante_api.database import database_url
from asante_api.models import StoryRecord


DEFAULT_SLUGS = (
    "testdata-ethiopia",
    "testdata-idi-amin",
    "testdata-africa-civilizations",
    "testdata-snake-wedding",
    "testdata-folktale",
    "story-001",
    "story-002",
    "story-003",
    "story-demo",
)


async def export_captions(slugs: list[str], out_path: Path) -> int:
    engine = create_async_engine(database_url(), pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    payload: dict[str, Any] = {"version": 1, "stories": {}}
    try:
        async with sessions() as session:
            rows = (await session.scalars(select(StoryRecord).where(StoryRecord.slug.in_(slugs)))).all()
            for row in rows:
                payload["stories"][row.slug] = {
                    "transcript": row.transcript or "",
                    "translation": row.translation or "",
                    "translation_language": row.translation_language or "",
                    "caption_tracks": row.caption_tracks or {},
                }
                tracks = (row.caption_tracks or {}).get("tracks") if isinstance(row.caption_tracks, dict) else []
                print({"export": row.slug, "tracks": len(tracks or []), "transcriptChars": len(row.transcript or "")}, flush=True)
    finally:
        await engine.dispose()
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print({"wrote": str(out_path), "stories": len(payload["stories"])}, flush=True)
    return 0


async def import_captions(in_path: Path, slugs: list[str] | None) -> int:
    payload = json.loads(in_path.read_text(encoding="utf-8"))
    stories = payload.get("stories") or {}
    if not isinstance(stories, dict):
        raise SystemExit("Invalid captions payload: stories must be an object")
    selected = slugs or sorted(stories.keys())
    engine = create_async_engine(database_url(), pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions.begin() as session:
            for slug in selected:
                bundle = stories.get(slug)
                if not isinstance(bundle, dict):
                    print({"import": slug, "status": "missing_in_payload"}, flush=True)
                    continue
                result = await session.execute(
                    update(StoryRecord)
                    .where(StoryRecord.slug == slug)
                    .values(
                        transcript=str(bundle.get("transcript") or ""),
                        translation=str(bundle.get("translation") or ""),
                        translation_language=str(bundle.get("translation_language") or "")[:20],
                        caption_tracks=bundle.get("caption_tracks") or {},
                    )
                )
                print({"import": slug, "updated": bool(result.rowcount)}, flush=True)
    finally:
        await engine.dispose()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    export_p = sub.add_parser("export")
    export_p.add_argument("--out", required=True)
    export_p.add_argument("--slugs", default=",".join(DEFAULT_SLUGS))
    import_p = sub.add_parser("import")
    import_p.add_argument("--in", dest="infile", required=True)
    import_p.add_argument("--slugs", default="")
    args = parser.parse_args(argv)
    if args.command == "export":
        slugs = [item.strip() for item in args.slugs.split(",") if item.strip()]
        return asyncio.run(export_captions(slugs, Path(args.out)))
    slugs = [item.strip() for item in args.slugs.split(",") if item.strip()] or None
    return asyncio.run(import_captions(Path(args.infile), slugs))


if __name__ == "__main__":
    sys.exit(main())
