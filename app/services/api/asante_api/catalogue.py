"""PostgreSQL-backed public catalogue reads for landmarks and published stories."""

from __future__ import annotations

import base64
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from geoalchemy2 import Geography, Geometry
from sqlalchemy import and_, case, cast, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import LandmarkRecord, StoryRecord


@dataclass(frozen=True)
class CatalogueCursor:
    last_slug: str
    distance_m: float | None = None


def _geography_point(latitude: float, longitude: float) -> Any:
    """Create a WGS84 geography point in longitude/latitude axis order."""
    point = func.ST_SetSRID(func.ST_MakePoint(longitude, latitude), 4326)
    return cast(point, Geography(geometry_type="POINT", srid=4326, spatial_index=False))


def _landmark_coordinates():
    point = cast(
        LandmarkRecord.location,
        Geometry(geometry_type="POINT", srid=4326, spatial_index=False),
    )
    return func.ST_Y(point).label("latitude"), func.ST_X(point).label("longitude")


def public_caption_tracks(value: Any) -> list[dict[str, Any]]:
    """Return only bounded, timed caption cues that can be synced to a media clock."""
    if isinstance(value, dict):
        entries = value.get("tracks")
        if not isinstance(entries, list):
            entries = [dict(track, language=track.get("language") or language) for language, track in value.items() if isinstance(track, dict)]
    elif isinstance(value, list):
        entries = value
    else:
        return []

    tracks: list[dict[str, Any]] = []
    total_cues = 0
    for entry in entries[:12]:
        if not isinstance(entry, dict):
            continue
        language = str(entry.get("language") or entry.get("lang") or "").strip()[:20]
        if not language:
            continue
        label = str(entry.get("label") or language).strip()[:80]
        raw_cues = entry.get("cues") or entry.get("segments")
        if not isinstance(raw_cues, list):
            continue
        cues: list[dict[str, Any]] = []
        for cue in raw_cues[:2500]:
            if total_cues >= 2500:
                break
            if not isinstance(cue, dict):
                continue
            try:
                start = float(cue.get("start", cue.get("startTime")))
                end = float(cue.get("end", cue.get("endTime")))
            except (TypeError, ValueError):
                continue
            text = str(cue.get("text") or "").strip()
            if not (math.isfinite(start) and math.isfinite(end) and 0 <= start < end and text):
                continue
            cues.append({"start": start, "end": end, "text": text[:500]})
            total_cues += 1
        if cues:
            cues.sort(key=lambda cue: cue["start"])
            tracks.append({"language": language, "label": label, "cues": cues})
    return tracks


def encode_catalogue_cursor(last_slug: str, distance_m: float | None = None) -> str:
    payload = json.dumps(
        {"last": last_slug, "distanceM": distance_m}, separators=(",", ":")
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def decode_catalogue_cursor(cursor: str | None) -> CatalogueCursor | None:
    if cursor is None:
        return None
    try:
        encoded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(encoded.encode("ascii")))
        last_slug = payload["last"]
        if not isinstance(last_slug, str) or not last_slug or len(last_slug) > 100:
            raise ValueError
        distance_m = payload.get("distanceM")
        if distance_m is not None:
            if isinstance(distance_m, bool) or not isinstance(distance_m, (int, float)):
                raise ValueError
            distance_m = float(distance_m)
            if not math.isfinite(distance_m) or distance_m < 0:
                raise ValueError
        return CatalogueCursor(last_slug=last_slug, distance_m=distance_m)
    except (ValueError, KeyError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Invalid catalogue cursor") from error


def parse_bbox(value: str | None) -> tuple[float, float, float, float] | None:
    """Parse `west,south,east,north`; west > east represents the antimeridian."""
    if value is None:
        return None
    try:
        values = tuple(float(part.strip()) for part in value.split(","))
    except ValueError as error:
        raise ValueError("bbox must contain four finite coordinates") from error
    if len(values) != 4 or not all(math.isfinite(part) for part in values):
        raise ValueError("bbox must contain four finite coordinates")
    west, south, east, north = values
    if not (-180 <= west <= 180 and -180 <= east <= 180):
        raise ValueError("bbox longitude must be between -180 and 180")
    if not (-90 <= south < north <= 90):
        raise ValueError("bbox latitude must be ordered between -90 and 90")
    if west == east:
        raise ValueError("bbox west and east must differ")
    return west, south, east, north


def _bbox_filter(bbox: tuple[float, float, float, float]):
    west, south, east, north = bbox
    if west < east:
        envelope = func.ST_MakeEnvelope(west, south, east, north, 4326)
        geography_envelope = cast(
            envelope,
            Geography(geometry_type="POLYGON", srid=4326, spatial_index=False),
        )
        return func.ST_Intersects(LandmarkRecord.location, geography_envelope)

    western_envelope = cast(
        func.ST_MakeEnvelope(west, south, 180, north, 4326),
        Geography(geometry_type="POLYGON", srid=4326, spatial_index=False),
    )
    eastern_envelope = cast(
        func.ST_MakeEnvelope(-180, south, east, north, 4326),
        Geography(geometry_type="POLYGON", srid=4326, spatial_index=False),
    )
    return or_(
        func.ST_Intersects(LandmarkRecord.location, western_envelope),
        func.ST_Intersects(LandmarkRecord.location, eastern_envelope),
    )


async def list_landmarks(session: AsyncSession) -> list[dict[str, Any]]:
    latitude, longitude = _landmark_coordinates()
    statement = (
        select(
            LandmarkRecord.slug.label("id"),
            LandmarkRecord.name,
            LandmarkRecord.region,
            latitude,
            longitude,
            literal(None).label("distance_m"),
        )
        .where(LandmarkRecord.active.is_(True))
        .order_by(LandmarkRecord.name, LandmarkRecord.slug)
    )
    rows = (await session.execute(statement)).mappings().all()
    return [dict(row) for row in rows]


async def list_nearby_landmarks(
    session: AsyncSession,
    latitude: float,
    longitude: float,
    radius_m: float,
    limit: int,
) -> list[dict[str, Any]]:
    point = _geography_point(latitude, longitude)
    distance = func.ST_Distance(LandmarkRecord.location, point)
    coordinates = _landmark_coordinates()
    statement = (
        select(
            LandmarkRecord.slug.label("id"),
            LandmarkRecord.name,
            LandmarkRecord.region,
            coordinates[0],
            coordinates[1],
            distance.label("distance_m"),
        )
        .where(
            LandmarkRecord.active.is_(True),
            func.ST_DWithin(LandmarkRecord.location, point, radius_m),
        )
        .order_by(distance, LandmarkRecord.slug)
        .limit(limit)
    )
    rows = (await session.execute(statement)).mappings().all()
    return [
        {**dict(row), "distance_m": round(float(row["distance_m"]), 2)}
        for row in rows
    ]


async def list_landmark_page(
    session: AsyncSession,
    *,
    page_size: int,
    cursor: CatalogueCursor | None,
    bbox: tuple[float, float, float, float] | None = None,
) -> dict[str, Any]:
    latitude, longitude = _landmark_coordinates()
    statement = select(
        LandmarkRecord.slug.label("id"),
        LandmarkRecord.name,
        LandmarkRecord.region,
        latitude,
        longitude,
    ).where(LandmarkRecord.active.is_(True))
    if bbox is not None:
        statement = statement.where(_bbox_filter(bbox))
    if cursor is not None:
        if cursor.distance_m is not None:
            raise ValueError("Cursor sort does not match the landmark catalogue")
        statement = statement.where(LandmarkRecord.slug > cursor.last_slug)
    statement = statement.order_by(LandmarkRecord.slug).limit(page_size + 1)
    rows = (await session.execute(statement)).mappings().all()
    has_more = len(rows) > page_size
    page = rows[:page_size]
    return {
        "items": [dict(row) for row in page],
        "next_cursor": encode_catalogue_cursor(page[-1]["id"]) if has_more and page else None,
    }


async def list_published_stories(
    session: AsyncSession,
    latitude: float | None = None,
    longitude: float | None = None,
    radius_m: float | None = None,
    limit: int = 100,
    contributor_id: str | None = None,
) -> list[dict[str, Any]]:
    """Read public stories globally or within an explicitly requested radius."""
    coordinates = _landmark_coordinates()
    distance = None
    if latitude is not None and longitude is not None:
        point = _geography_point(latitude, longitude)
        distance = func.ST_Distance(LandmarkRecord.location, point)

    statement = (
        select(
            StoryRecord.slug.label("id"),
            StoryRecord.title,
            StoryRecord.contributor_name,
            StoryRecord.contributor_id,
            StoryRecord.language,
            StoryRecord.media_format,
            StoryRecord.status,
            LandmarkRecord.name.label("landmark"),
            LandmarkRecord.slug.label("landmark_id"),
            (distance if distance is not None else literal(None)).label("distance_m"),
            coordinates[0],
            coordinates[1],
            LandmarkRecord.region,
            StoryRecord.media_file,
            StoryRecord.poster_file,
            StoryRecord.transcript,
            StoryRecord.is_demo,
        )
        .join(StoryRecord.landmark)
        .where(
            StoryRecord.status == "published",
            StoryRecord.active.is_(True),
            LandmarkRecord.active.is_(True),
        )
    )
    if contributor_id is not None:
        statement = statement.where(StoryRecord.contributor_id == contributor_id)
    if radius_m is not None:
        statement = statement.where(
            func.ST_DWithin(
                LandmarkRecord.location,
                _geography_point(latitude or 0, longitude or 0),
                radius_m,
            )
        )

    if distance is not None:
        statement = statement.order_by(distance, StoryRecord.slug)
    else:
        statement = statement.order_by(
            case((StoryRecord.media_file.is_(None), 1), else_=0),
            StoryRecord.title,
            StoryRecord.slug,
        )
    statement = statement.limit(limit)
    rows = (await session.execute(statement)).mappings().all()
    items: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["distance_m"] = round(float(item["distance_m"]), 2) if item["distance_m"] is not None else None
        media_file = item.pop("media_file")
        poster_file = item.pop("poster_file", None)
        item["media_url"] = (
            f"/asante/api/v1/stories/{item['id']}/hls/index.m3u8"
            if media_file and str(media_file).endswith(".m3u8")
            else (f"/asante/api/v1/stories/{item['id']}/media" if media_file else None)
        )
        item["poster_url"] = f"/asante/api/v1/stories/{item['id']}/poster" if poster_file else None
        item["contributor_profile_url"] = f"/asante/profiles/{item['contributor_id']}/" if item["contributor_id"] else None
        items.append(item)
    return items


async def list_public_story_page(
    session: AsyncSession,
    *,
    page_size: int,
    cursor: CatalogueCursor | None,
    search: str | None = None,
    language: str | None = None,
    region: str | None = None,
    media_format: str | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    radius_m: float | None = None,
) -> dict[str, Any]:
    coordinates = _landmark_coordinates()
    distance = None
    point = None
    if latitude is not None and longitude is not None:
        point = _geography_point(latitude, longitude)
        distance = func.ST_Distance(LandmarkRecord.location, point)

    statement = (
        select(
            StoryRecord.slug.label("id"),
            StoryRecord.title,
            StoryRecord.contributor_name,
            StoryRecord.contributor_id,
            StoryRecord.language,
            StoryRecord.media_format,
            StoryRecord.status,
            LandmarkRecord.name.label("landmark"),
            LandmarkRecord.slug.label("landmark_id"),
            (distance if distance is not None else literal(None)).label("distance_m"),
            coordinates[0],
            coordinates[1],
            LandmarkRecord.region,
            StoryRecord.media_file,
            StoryRecord.poster_file,
            StoryRecord.transcript,
            StoryRecord.is_demo,
        )
        .join(StoryRecord.landmark)
        .where(
            StoryRecord.status == "published",
            StoryRecord.active.is_(True),
            LandmarkRecord.active.is_(True),
        )
    )
    if bbox is not None:
        statement = statement.where(_bbox_filter(bbox))
    if radius_m is not None and point is not None:
        statement = statement.where(func.ST_DWithin(LandmarkRecord.location, point, radius_m))
    if language:
        statement = statement.where(func.lower(StoryRecord.language) == language.lower())
    if region:
        statement = statement.where(func.lower(LandmarkRecord.region) == region.lower())
    if media_format:
        statement = statement.where(func.lower(StoryRecord.media_format) == media_format.lower())
    if search:
        escaped = search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        statement = statement.where(
            or_(
                StoryRecord.title.ilike(pattern, escape="\\"),
                StoryRecord.contributor_name.ilike(pattern, escape="\\"),
                LandmarkRecord.name.ilike(pattern, escape="\\"),
                LandmarkRecord.region.ilike(pattern, escape="\\"),
            )
        )
    if cursor is not None:
        if distance is None:
            if cursor.distance_m is not None:
                raise ValueError("Cursor sort does not match the story catalogue")
            statement = statement.where(StoryRecord.slug > cursor.last_slug)
        else:
            if cursor.distance_m is None:
                raise ValueError("Cursor sort does not match the story catalogue")
            statement = statement.where(
                or_(
                    distance > cursor.distance_m,
                    and_(distance == cursor.distance_m, StoryRecord.slug > cursor.last_slug),
                )
            )
    if distance is None:
        statement = statement.order_by(StoryRecord.slug)
    else:
        statement = statement.order_by(distance, StoryRecord.slug)
    statement = statement.limit(page_size + 1)
    rows = (await session.execute(statement)).mappings().all()
    has_more = len(rows) > page_size
    page = rows[:page_size]
    items: list[dict[str, Any]] = []
    last_distance_m: float | None = None
    for row in page:
        item = dict(row)
        if item["distance_m"] is not None:
            last_distance_m = float(item["distance_m"])
            item["distance_m"] = round(last_distance_m, 2)
        media_file = item.pop("media_file")
        poster_file = item.pop("poster_file", None)
        item["media_url"] = (
            f"/asante/api/v1/stories/{item['id']}/hls/index.m3u8"
            if media_file and str(media_file).endswith(".m3u8")
            else (f"/asante/api/v1/stories/{item['id']}/media" if media_file else None)
        )
        item["poster_url"] = f"/asante/api/v1/stories/{item['id']}/poster" if poster_file else None
        item["contributor_profile_url"] = f"/asante/profiles/{item['contributor_id']}/" if item["contributor_id"] else None
        items.append(item)
    return {
        "items": items,
        "next_cursor": encode_catalogue_cursor(
            page[-1]["id"], last_distance_m
        ) if has_more and page else None,
    }


async def published_story_media_file(session: AsyncSession, story_slug: str) -> str | None:
    """Return the media file only for an active, published story."""
    statement = (
        select(StoryRecord.media_file)
        .join(StoryRecord.landmark)
        .where(
            StoryRecord.slug == story_slug,
            StoryRecord.status == "published",
            StoryRecord.active.is_(True),
            LandmarkRecord.active.is_(True),
        )
    )
    return await session.scalar(statement)


async def published_story_poster_file(session: AsyncSession, story_slug: str) -> str | None:
    """Return the poster object key for an active, published story."""
    statement = (
        select(StoryRecord.poster_file)
        .join(StoryRecord.landmark)
        .where(
            StoryRecord.slug == story_slug,
            StoryRecord.status == "published",
            StoryRecord.active.is_(True),
            LandmarkRecord.active.is_(True),
        )
    )
    return await session.scalar(statement)


async def published_story_caption_tracks(session: AsyncSession, story_slug: str) -> list[dict[str, Any]] | None:
    """Return bounded timed captions only for an active, published story."""
    state = await published_story_caption_state(session, story_slug)
    return state["items"] if state is not None else None


async def published_story_caption_state(session: AsyncSession, story_slug: str) -> dict[str, Any] | None:
    """Expose available cues and safe translation outcomes for one published story."""
    statement = (
        select(StoryRecord.caption_tracks)
        .join(StoryRecord.landmark)
        .where(
            StoryRecord.slug == story_slug,
            StoryRecord.status == "published",
            StoryRecord.active.is_(True),
            LandmarkRecord.active.is_(True),
        )
    )
    value = await session.scalar(statement)
    if value is None:
        return None
    raw_state = value.get("translationStatus") if isinstance(value, dict) else None
    translation_state = {
        str(language)[:20]: {
            "status": str(item.get("status") or "unavailable")[:20],
            "coveredCues": int(item.get("coveredCues") or 0),
            "totalCues": int(item.get("totalCues") or 0),
            "provider": str(item.get("provider") or "unavailable")[:40],
            "reason": str(item.get("reason") or "")[:200],
        }
        for language, item in (raw_state or {}).items()
        if isinstance(item, dict)
    } if isinstance(raw_state, dict) else {}
    return {"items": public_caption_tracks(value), "translationStatus": translation_state}


def published_hls_object_key(media_file: str, name: str) -> str | None:
    """Resolve a sibling HLS playlist/segment key under the published media prefix."""
    if "/" not in media_file or not media_file.endswith(".m3u8"):
        return None
    if name != Path(name).name or ".." in name or "/" in name or "\\" in name:
        return None
    if not (name.endswith(".m3u8") or name.endswith(".ts")):
        return None
    return f"{media_file.rsplit('/', 1)[0]}/{name}"

