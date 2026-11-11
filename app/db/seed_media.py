"""Seed the synthetic demo recording and public catalogue story thumbnails."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from minio.error import S3Error
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from asante_api.database import database_url
from asante_api.media_process import create_audio_cover, extract_poster, probe_media
from asante_api.models import StoryRecord
from asante_api.storage import media_bucket, storage_client

MEDIA_DIR = Path("/workspace/media")
VIDEO_FIXTURES = {"story-002": "story-002-market.mp4"}


def seed_demo_media() -> None:
    client = storage_client()
    bucket = media_bucket()
    key = "asante-playback-demo.mp3"
    try:
        client.stat_object(bucket, key)
    except S3Error as error:
        if error.code not in {"NoSuchKey", "NoSuchObject"}:
            raise
        client.fput_object(bucket, key, str(MEDIA_DIR / key), content_type="audio/mpeg")


def _stored_poster_is_available(client, bucket: str, key: str | None) -> bool:
    if not key:
        return False
    try:
        client.stat_object(bucket, key)
        return True
    except S3Error as error:
        if error.code in {"NoSuchKey", "NoSuchObject"}:
            return False
        raise


async def seed_story_posters() -> None:
    client = storage_client()
    bucket = media_bucket()
    engine = create_async_engine(database_url(), pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions.begin() as session:
            stories = (await session.scalars(
                select(StoryRecord).where(
                    StoryRecord.status == "published",
                    StoryRecord.active.is_(True),
                ).order_by(StoryRecord.slug)
            )).all()
            for story in stories:
                object_key = story.poster_file or f"catalogue-posters/{story.slug}.svg"
                if _stored_poster_is_available(client, bucket, story.poster_file):
                    continue
                with tempfile.TemporaryDirectory(prefix="asante-story-poster-") as temp_dir:
                    temp = Path(temp_dir)
                    video_source = None
                    fixture_name = VIDEO_FIXTURES.get(story.slug)
                    if story.media_file:
                        candidate = temp / Path(story.media_file).name
                        try:
                            client.fget_object(bucket, story.media_file, str(candidate))
                            video_source = candidate
                        except S3Error:
                            video_source = None
                    elif fixture_name and (MEDIA_DIR / fixture_name).is_file():
                        video_source = MEDIA_DIR / fixture_name

                    if story.media_format == "video" and video_source:
                        probe = probe_media(video_source)
                        if probe["hasVideo"]:
                            poster_path = temp / "poster.jpg"
                            derivative = extract_poster(video_source, poster_path)
                            object_key = f"catalogue-posters/{story.slug}.jpg"
                            client.fput_object(bucket, object_key, str(poster_path), content_type=derivative["contentType"])
                        else:
                            video_source = None

                    if not _stored_poster_is_available(client, bucket, object_key):
                        cover_path = temp / "cover.svg"
                        create_audio_cover(cover_path, story.slug)
                        object_key = f"catalogue-posters/{story.slug}.svg"
                        client.fput_object(bucket, object_key, str(cover_path), content_type="image/svg+xml")
                    story.poster_file = object_key
        await engine.dispose()
    except Exception:
        await engine.dispose()
        raise


async def seed_catalogue_media() -> None:
    seed_demo_media()
    await seed_story_posters()


if __name__ == "__main__":
    asyncio.run(seed_catalogue_media())
