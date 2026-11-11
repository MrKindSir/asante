"""Seed pending-review submissions from TestData clips, including off-topic packs for the heritage gate."""
from __future__ import annotations

import asyncio
import hashlib
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from asante_api.ai.jobs import enqueue_submission_jobs
from asante_api.database import database_url
from asante_api.models import (
    AccountRecord,
    ContributorRecord,
    ProjectRecord,
    ProjectRevision,
    SubmissionPacket,
    UploadRecord,
)
from asante_api.storage import media_bucket, storage_client

TESTDATA_CANDIDATES = (
    Path(os.environ["ASANTE_TESTDATA_DIR"]) if os.environ.get("ASANTE_TESTDATA_DIR") else None,
    Path("/testdata"),
    Path("/Users/vavu/Downloads/TestData"),
)

# Mix of on-topic African stories and deliberate off-topic packets for the heritage gate.
REVIEW_FIXTURES = (
    {
        "key": "snake-folktale",
        "contributor_slug": "nomsa",
        "title": "They never knew she was a snake",
        "place": "Soweto Towers",
        "language": "en",
        "summary": (
            "African folktale from Duru Village about Obiora, whose true nature as a mystical snake "
            "is revealed on her wedding night. A heritage oral story about love, deceit, and acceptance."
        ),
        "claim": "This is a traditional African folktale shared for community listening.",
        "media_names": ("They NEVER Knew She Was a SNAKE Until Her WEDDING NIGHT.mp4",),
        "expect_gate": "accept",
    },
    {
        "key": "shadow-legend",
        "contributor_slug": "thabo",
        "title": "The boy who spoke to shadows",
        "place": "Constitution Hill",
        "language": "en",
        "summary": (
            "An African legend from the village of Oduko where shadows remember ancestral bargains. "
            "Ekanem learns the truth buried beneath centuries of whispers."
        ),
        "claim": "African folk tale for heritage storytelling.",
        "media_names": ("Folktale Stories By Unstoppable.mp4",),
        "expect_gate": "accept",
    },
    {
        "key": "sleep-history",
        "contributor_slug": "amina",
        "title": "What happened to Haile Selassie's body | History for sleep",
        "place": "Mapungubwe Hill",
        "language": "en",
        "summary": (
            "History for sleep narration about Haile Selassie's body after he was overthrown. "
            "Relaxing bedtime history channel style content, not a community oral heritage account."
        ),
        "claim": "Entertainment sleep history, not a community heritage contribution.",
        "media_names": (
            "What Happened to Haile Selassie’s Body After He Was Overthrown? | History For Sleep.mp4",
            "What Happened to Haile Selassie's Body After He Was Overthrown? | History For Sleep.mp4",
        ),
        "expect_gate": "reject",
    },
    {
        "key": "nordic-offtopic",
        "contributor_slug": "thabo",
        "title": "Nordic winter legend: The Frost Giant's Bride",
        "place": "District Six",
        "language": "en",
        "summary": (
            "A Scandinavian viking bedtime tale about a frost giant wedding in Iceland. "
            "This is European fairy storytelling with no African place, people, or cultural marker."
        ),
        "claim": "Nordic / Scandinavian folklore sample used to test the heritage gate.",
        "media_names": ("Folktale Stories By Unstoppable.mp4",),
        "expect_gate": "reject",
    },
    {
        "key": "idi-amin-doc",
        "contributor_slug": "nomsa",
        "title": "A day in the life of a dictator: Idi Amin Dada",
        "place": "Soweto Towers",
        "language": "en",
        "summary": (
            "Documentary dramatization about Ugandan dictator Idi Amin Dada and a March 1974 plot. "
            "Political entertainment documentary rather than a contributor oral heritage story."
        ),
        "claim": "Imported documentary used to exercise review and relevance checks.",
        "media_names": ("A Day in The Life of a Dictator Idi Amin Dada.mp4",),
        "expect_gate": "attention",
    },
)


def fixture_id(kind: str, name: str) -> str:
    return uuid5(NAMESPACE_URL, f"asante:review-seed:{kind}:{name}").hex


def testdata_root() -> Path:
    for candidate in TESTDATA_CANDIDATES:
        if candidate and candidate.exists():
            return candidate
    raise FileNotFoundError("ASANTE_TESTDATA_DIR /testdata is missing")


def resolve_media(root: Path, names: tuple[str, ...]) -> Path:
    for name in names:
        path = root / name
        if path.exists():
            return path
    raise FileNotFoundError(f"None of the media names exist under {root}: {names}")


def clip_media(source: Path, destination: Path, seconds: int = 45) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.stat().st_size < 40_000_000:
        shutil.copy2(source, destination)
        return
    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            "0",
            "-i",
            str(source),
            "-t",
            str(seconds),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(destination),
        ],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0 or not destination.exists() or destination.stat().st_size < 1000:
        # Fall back to a short re-encode when stream copy fails.
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                "0",
                "-i",
                str(source),
                "-t",
                str(min(seconds, 20)),
                "-vf",
                "scale=640:-2",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-c:a",
                "aac",
                "-ac",
                "1",
                str(destination),
            ],
            capture_output=True,
            check=False,
        )
    if result.returncode != 0 or not destination.exists():
        detail = (result.stderr or b"").decode("utf-8", errors="ignore")[:300]
        raise RuntimeError(f"Could not clip {source.name}: {detail}")


def put_object(local_path: Path, object_key: str, content_type: str) -> tuple[int, str]:
    client = storage_client()
    bucket = media_bucket()
    checksum = hashlib.sha256(local_path.read_bytes()).hexdigest()
    client.fput_object(bucket, object_key, str(local_path), content_type=content_type)
    return local_path.stat().st_size, checksum


async def seed_review_submissions() -> None:
    if os.environ.get("ASANTE_ENV") != "development":
        raise ValueError("Review submission seeding is restricted to development")

    root = testdata_root()
    engine = create_async_engine(database_url())
    created = 0
    try:
        async with async_sessionmaker(engine, expire_on_commit=False).begin() as session:
            for fixture in REVIEW_FIXTURES:
                submission_id = fixture_id("submission", fixture["key"])
                if await session.get(SubmissionPacket, submission_id):
                    continue

                email = f"{fixture['contributor_slug']}@asante.test"
                account = await session.scalar(select(AccountRecord).where(AccountRecord.email == email))
                if not account:
                    raise ValueError(f"Missing test account {email}; run seed_accounts first")
                contributor = await session.get(ContributorRecord, account.contributor_id)
                if not contributor:
                    raise ValueError(f"Missing contributor for {email}")

                project_id = fixture_id("project", fixture["key"])
                revision_id = fixture_id("revision", fixture["key"])
                upload_id = fixture_id("upload", fixture["key"])
                source = resolve_media(root, fixture["media_names"])
                with tempfile.TemporaryDirectory(prefix="asante-review-seed-") as temporary:
                    clip_path = Path(temporary) / f"{fixture['key']}.mp4"
                    clip_media(source, clip_path)
                    object_key = f"uploads/{contributor.id}/{project_id}/{upload_id}/original.mp4"
                    size, checksum = put_object(clip_path, object_key, "video/mp4")

                content = {
                    "title": fixture["title"],
                    "place": fixture["place"],
                    "language": fixture["language"],
                    "format": "video",
                    "audience": "Community listeners",
                    "transcript": fixture["summary"],
                    "claim": fixture["claim"],
                    "source": "",
                    "consent": True,
                    "plan": None,
                    "research": None,
                    "suggestion": "pending",
                    "verification": None,
                    "uploadId": upload_id,
                    "mediaDerivatives": {},
                    "extraNotes": f"seed expect_gate={fixture['expect_gate']}",
                }
                if not await session.get(ProjectRecord, project_id):
                    session.add(ProjectRecord(id=project_id, contributor_id=contributor.id, version=1, content=content))
                    await session.flush()
                    session.add(ProjectRevision(id=revision_id, project_id=project_id, version=1, content=content))
                if not await session.get(UploadRecord, upload_id):
                    session.add(
                        UploadRecord(
                            id=upload_id,
                            project_id=project_id,
                            contributor_id=contributor.id,
                            name=source.name,
                            content_type="video/mp4",
                            size=size,
                            checksum=checksum,
                            object_key=object_key,
                            status="verified",
                            expires_at=datetime.now(timezone.utc) + timedelta(days=3650),
                        )
                    )
                    await session.flush()

                coordinates = {
                    "Constitution Hill": (-26.1883, 28.0368),
                    "Soweto Towers": (-26.2344, 27.9091),
                    "Mapungubwe Hill": (-22.1920, 29.4311),
                    "District Six": (-33.9273, 18.4242),
                }
                latitude, longitude = coordinates[fixture["place"]]
                snapshot = {
                    "title": fixture["title"],
                    "contributor_name": contributor.profile.get("name") or fixture["contributor_slug"],
                    "language": fixture["language"],
                    "media_format": "video",
                    "latitude": latitude,
                    "longitude": longitude,
                    "consent_given": True,
                    "summary": fixture["summary"],
                    "claim": fixture["claim"],
                    "source_url": "",
                    "media_name": source.name,
                    "media_size": size,
                    "media_checksum": checksum,
                    "media_verified": True,
                    "mediaDerivatives": {},
                    "plan": None,
                    "research": None,
                    "suggestion": None,
                    "verification": None,
                    "trace_id": "trace_" + fixture_id("trace", fixture["key"]),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "human_gate": "required_before_publication",
                    "sharedContract": "asante.verification.v1",
                    "seedKey": fixture["key"],
                    "seedExpectGate": fixture["expect_gate"],
                }
                packet = SubmissionPacket(
                    id=submission_id,
                    project_id=project_id,
                    revision_id=revision_id,
                    contributor_id=contributor.id,
                    upload_id=upload_id,
                    packet=snapshot,
                    status="pending_review",
                    version=1,
                )
                session.add(packet)
                await session.flush()
                await enqueue_submission_jobs(session, packet)
                created += 1
    finally:
        await engine.dispose()
    print(f"Seeded {created} review submission(s) from {root}")


if __name__ == "__main__":
    asyncio.run(seed_review_submissions())
