"""Publish an approved review packet into the public catalogue."""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from uuid import UUID, uuid4

from geoalchemy2 import Geometry
from sqlalchemy import cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .catalogue import public_caption_tracks
from .models import LandmarkRecord, MediaDerivativeRecord, ProcessingJobRecord, ProjectRecord, StoryRecord, SubmissionPacket, UploadRecord

PLACE_LANDMARKS = {
    "Constitution Hill": (-26.1883, 28.0368),
    "Soweto Towers": (-26.2344, 27.9091),
    "Mapungubwe Hill": (-22.1920, 29.4311),
    "District Six": (-33.9273, 18.4242),
    "Addis Ababa": (9.0320, 38.7469),
    "Kampala": (0.3476, 32.5825),
    "Cairo": (30.0444, 31.2357),
    "Lagos": (6.5244, 3.3792),
    "Accra": (5.6037, -0.1870),
}


def _slugify(title: str, submission_id: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-")[:60] or "story"
    suffix = (submission_id or uuid4().hex)[-8:]
    return f"{base}-{suffix}"


def _primary_translation(snapshot: dict) -> tuple[str, str]:
    """Pick a listener-facing translation draft, preferring English when present."""
    translations = snapshot.get("translations") or snapshot.get("publishedTranslations") or {}
    if not isinstance(translations, dict) or not translations:
        return "", ""
    preferred = ("en", *sorted(code for code in translations if code != "en"))
    for code in preferred:
        payload = translations.get(code)
        if not isinstance(payload, dict):
            continue
        text = str(payload.get("text") or "").strip()
        if text:
            return text, str(code)[:20]
    return "", ""


def _distance_m(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    radius = 6_371_000
    d_lat = math.radians(lat_b - lat_a)
    d_lon = math.radians(lon_b - lon_a)
    a = math.sin(d_lat / 2) ** 2 + math.cos(math.radians(lat_a)) * math.cos(math.radians(lat_b)) * math.sin(d_lon / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


async def published_caption_tracks_for_submission(session: AsyncSession, packet: SubmissionPacket) -> list[dict]:
    """Build listener caption tracks from completed, timed media-job drafts."""
    jobs = (await session.scalars(
        select(ProcessingJobRecord).where(
            ProcessingJobRecord.submission_id == packet.id,
            ProcessingJobRecord.status == "succeeded",
        )
    )).all()
    results = {job.job_type: job.result_payload or {} for job in jobs}
    tracks: list[dict] = []
    transcript = (results.get("transcribe", {}).get("transcriptDraft") or {})
    segments = transcript.get("segments") or []
    if segments:
        language = str(transcript.get("language") or (packet.packet or {}).get("language") or "en")
        tracks.append({"language": language, "label": {"en": "English", "zu": "isiZulu", "st": "Sesotho"}.get(language, language), "cues": segments})
    tracks.extend(results.get("translate", {}).get("captionTracks") or [])
    return public_caption_tracks(tracks)


async def refresh_published_captions(session: AsyncSession, packet: SubmissionPacket) -> None:
    """Attach newly completed timed drafts to an already-published story."""
    published_id = (packet.packet or {}).get("publishedStoryId")
    if not published_id:
        return
    try:
        story = await session.get(StoryRecord, UUID(str(published_id)))
    except (TypeError, ValueError):
        return
    if story and story.status == "published" and story.active:
        story.caption_tracks = await published_caption_tracks_for_submission(session, packet)


async def _landmark_for_packet(session: AsyncSession, packet: SubmissionPacket, project: ProjectRecord | None) -> LandmarkRecord:
    place = ""
    if project and isinstance(project.content, dict):
        place = str(project.content.get("place") or "").strip()
    if place:
        landmark = await session.scalar(select(LandmarkRecord).where(LandmarkRecord.name == place, LandmarkRecord.active.is_(True)))
        if landmark:
            return landmark

    point = cast(LandmarkRecord.location, Geometry(geometry_type="POINT", srid=4326, spatial_index=False))
    rows = (
        await session.execute(
            select(
                LandmarkRecord,
                func.ST_Y(point).label("latitude"),
                func.ST_X(point).label("longitude"),
            ).where(LandmarkRecord.active.is_(True))
        )
    ).all()
    if not rows:
        raise RuntimeError("No landmarks are available for publication")

    snapshot = packet.packet or {}
    latitude = float(snapshot.get("latitude") or PLACE_LANDMARKS.get(place, (0, 0))[0] or 0)
    longitude = float(snapshot.get("longitude") or PLACE_LANDMARKS.get(place, (0, 0))[1] or 0)
    if latitude and longitude:
        best_row = min(rows, key=lambda row: _distance_m(latitude, longitude, float(row.latitude), float(row.longitude)))
        return best_row[0]
    return rows[0][0]


async def publish_approved_submission(session: AsyncSession, packet: SubmissionPacket) -> StoryRecord:
    """Create or refresh the public story row for an approved submission."""
    snapshot = dict(packet.packet or {})
    project_revision = snapshot.get("project_revision") if isinstance(snapshot.get("project_revision"), dict) else {}
    caption_tracks = await published_caption_tracks_for_submission(session, packet) or public_caption_tracks(
        snapshot.get("caption_tracks")
        or snapshot.get("captionTracks")
        or project_revision.get("caption_tracks")
        or project_revision.get("captionTracks")
    )
    poster_file = None
    if packet.upload_id:
        poster_file = await session.scalar(
            select(MediaDerivativeRecord.object_key)
            .where(
                MediaDerivativeRecord.upload_id == packet.upload_id,
                MediaDerivativeRecord.kind == "poster",
                MediaDerivativeRecord.status == "ready",
            )
            .limit(1)
        )
    published_id = snapshot.get("publishedStoryId")
    if published_id:
        try:
            existing = await session.get(StoryRecord, UUID(str(published_id)))
        except (TypeError, ValueError):
            existing = None
        if existing:
            existing.status = "published"
            existing.active = True
            existing.caption_tracks = caption_tracks
            if poster_file:
                existing.poster_file = poster_file
            existing.transcript = str(
                (snapshot.get("transcriptDraft") or {}).get("text")
                or snapshot.get("summary")
                or existing.transcript
                or ""
            )
            translation, translation_language = _primary_translation(snapshot)
            if translation:
                existing.translation = translation
                existing.translation_language = translation_language
            return existing

    project = await session.get(ProjectRecord, packet.project_id)
    upload = await session.get(UploadRecord, packet.upload_id) if packet.upload_id else None
    landmark = await _landmark_for_packet(session, packet, project)
    title = str(snapshot.get("title") or "Untitled story").strip()[:300]
    slug = _slugify(title, packet.id)
    while await session.scalar(select(StoryRecord.id).where(StoryRecord.slug == slug)):
        slug = _slugify(title, uuid4().hex)

    derivatives = snapshot.get("mediaDerivatives") if isinstance(snapshot.get("mediaDerivatives"), dict) else {}
    media_file = None
    if isinstance(derivatives.get("hls"), dict) and derivatives["hls"].get("objectKey"):
        media_file = str(derivatives["hls"]["objectKey"])
    elif upload:
        media_file = upload.object_key

    transcript = str((snapshot.get("transcriptDraft") or {}).get("text") or snapshot.get("summary") or "")
    translation, translation_language = _primary_translation(snapshot)
    story = StoryRecord(
        id=uuid4(),
        slug=slug,
        title=title,
        contributor_name=str(snapshot.get("contributor_name") or "Contributor")[:160],
        contributor_id=packet.contributor_id,
        landmark_id=landmark.id,
        language=str(snapshot.get("language") or "en")[:20],
        media_format=str(snapshot.get("media_format") or "audio")[:20],
        status="published",
        media_file=media_file,
        poster_file=poster_file,
        transcript=transcript,
        translation=translation,
        translation_language=translation_language,
        caption_tracks=caption_tracks,
        is_demo=False,
        active=True,
        created_at=datetime.now(timezone.utc),
    )
    session.add(story)
    await session.flush()

    snapshot["publishedStoryId"] = str(story.id)
    snapshot["publishedSlug"] = story.slug
    snapshot["publishedAt"] = story.created_at.isoformat()
    if snapshot.get("translations"):
        snapshot["publishedTranslations"] = snapshot["translations"]
    packet.packet = snapshot
    await session.flush()
    return story
