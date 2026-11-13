from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from math import asin, cos, radians, sin, sqrt
import os
import secrets
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool
from sqlalchemy import text
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from .catalogue import (
    CatalogueCursor,
    decode_catalogue_cursor,
    list_landmarks,
    list_landmark_page,
    list_nearby_landmarks,
    list_published_stories,
    list_public_story_page,
    parse_bbox,
    published_story_caption_state,
    published_hls_object_key,
    published_story_media_file,
    published_story_poster_file,
)
from .database import dispose_database_engine, get_session
from .models import ContributorRecord, AccountRecord
from .auth import mutation
from .storage import media_bytes, media_response, media_bucket, storage_client


SUPPORTED_FORMATS = {"audio", "video"}
SUPPORTED_LANGUAGES = {"en", "zu", "st"}
EARTH_RADIUS_M = 6_371_000


class PlanRequest(BaseModel):
    topic: str = Field(min_length=3, max_length=200)
    place_name: str = Field(min_length=2, max_length=120)
    language: str
    media_format: str
    audience: str = Field(min_length=2, max_length=120)

    @field_validator("language")
    @classmethod
    def validate_language(cls, value: str) -> str:
        if value not in SUPPORTED_LANGUAGES:
            raise ValueError(f"language must be one of: {', '.join(sorted(SUPPORTED_LANGUAGES))}")
        return value

    @field_validator("media_format")
    @classmethod
    def validate_media_format(cls, value: str) -> str:
        if value not in SUPPORTED_FORMATS:
            raise ValueError(f"media_format must be one of: {', '.join(sorted(SUPPORTED_FORMATS))}")
        return value


def distance_m(latitude_a: float, longitude_a: float, latitude_b: float, longitude_b: float) -> float:
    """Return the great-circle distance between two WGS84 coordinates in metres."""
    latitude_delta = radians(latitude_b - latitude_a)
    longitude_delta = radians(longitude_b - longitude_a)
    a = sin(latitude_delta / 2) ** 2 + cos(radians(latitude_a)) * cos(radians(latitude_b)) * sin(longitude_delta / 2) ** 2
    return 2 * EARTH_RADIUS_M * asin(sqrt(a))


def build_story_plan(topic: str, place_name: str, language: str, media_format: str, audience: str) -> dict:
    return {
        "topic": topic,
        "place_name": place_name,
        "language": language,
        "media_format": media_format,
        "audience": audience,
        "worker_steps": [
            "shape the story question and intended audience",
            "prepare a research brief and candidate evidence list",
            "prepare a recording and translation checklist",
            "assemble attribution, consent, and review metadata",
        ],
        "human_gate": "required_before_publication",
    }


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await dispose_database_engine()


app = FastAPI(title="Asante API", version="0.1.0", lifespan=lifespan)
from .workspace import router as workspace_router
from .uploads import router as uploads_router

from .auth import router as auth_router
from .workers_api import router as workers_router
from .plan_documents import router as plan_documents_router
app.include_router(auth_router)
app.include_router(workspace_router)
app.include_router(uploads_router)
app.include_router(workers_router)
app.include_router(plan_documents_router)


@app.get("/v1/profiles/{profile_id}")
async def contributor_profile(profile_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    from sqlalchemy import select
    profile = await session.get(ContributorRecord, profile_id)
    account = await session.scalar(select(AccountRecord).where(AccountRecord.contributor_id == profile_id, AccountRecord.role == "contributor"))
    if not profile or not account:
        raise HTTPException(404, "Contributor profile not found")
    return {"id": profile.id, "name": profile.profile.get("name", "Contributor"), "language": profile.profile.get("language", "en"), "stories": await list_published_stories(session, contributor_id=profile.id)}


@app.middleware("http")
async def private_cache_policy(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith(("/v1/auth", "/v1/workspace", "/v1/uploads", "/v1/review", "/v1/submissions", "/v1/plans")):
        response.headers["Cache-Control"] = "no-store"
    return response


def _catalogue_bbox(value: str | None) -> tuple[float, float, float, float] | None:
    try:
        return parse_bbox(value)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


def _catalogue_cursor(value: str | None) -> CatalogueCursor | None:
    try:
        return decode_catalogue_cursor(value)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


def _story_v2(item: dict) -> dict:
    return {
        "id": item["id"],
        "title": item["title"],
        "contributorName": item["contributor_name"],
        "contributorId": item["contributor_id"],
        "contributorProfileUrl": item["contributor_profile_url"],
        "language": item["language"],
        "mediaFormat": item["media_format"],
        "status": item["status"],
        "landmark": item["landmark"],
        "landmarkId": item["landmark_id"],
        "distanceM": item["distance_m"],
        "latitude": item["latitude"],
        "longitude": item["longitude"],
        "region": item["region"],
        "mediaUrl": item["media_url"],
        "posterUrl": item["poster_url"],
        "transcript": item["transcript"],
        "isDemo": item["is_demo"],
    }


@app.get("/v1/landmarks")
async def landmark_catalog(session: AsyncSession = Depends(get_session)) -> dict:
    return {"items": await list_landmarks(session)}


@app.get("/v2/landmarks")
async def landmark_catalog_v2(
    page_size: int = Query(default=20, ge=1, le=100, alias="pageSize"),
    cursor: str | None = Query(default=None, max_length=256),
    bbox: str | None = Query(default=None, max_length=80),
    session: AsyncSession = Depends(get_session),
) -> dict:
    cursor_value = _catalogue_cursor(cursor)
    if cursor_value is not None and cursor_value.distance_m is not None:
        raise HTTPException(status_code=422, detail="Cursor sort does not match the landmark catalogue")
    result = await list_landmark_page(
        session,
        page_size=page_size,
        cursor=cursor_value,
        bbox=_catalogue_bbox(bbox),
    )
    return {
        "items": [
            {
                "id": item["id"],
                "name": item["name"],
                "region": item["region"],
                "latitude": item["latitude"],
                "longitude": item["longitude"],
            }
            for item in result["items"]
        ],
        "nextCursor": result["next_cursor"],
    }


@app.get("/v1/stories")
async def story_catalog(
    latitude: float | None = Query(default=None, ge=-90, le=90),
    longitude: float | None = Query(default=None, ge=-180, le=180),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if (latitude is None) != (longitude is None):
        raise HTTPException(status_code=422, detail="Supply both coordinates or neither")
    items = await list_published_stories(session, latitude=latitude, longitude=longitude)
    return {"items": items}


@app.get("/v2/stories")
async def story_catalog_v2(
    search: str | None = Query(default=None, max_length=200),
    language: str | None = Query(default=None, max_length=20),
    region: str | None = Query(default=None, max_length=200),
    media_format: str | None = Query(default=None, max_length=20, alias="mediaFormat"),
    bbox: str | None = Query(default=None, max_length=80),
    latitude: float | None = Query(default=None, ge=-90, le=90),
    longitude: float | None = Query(default=None, ge=-180, le=180),
    page_size: int = Query(default=20, ge=1, le=100, alias="pageSize"),
    cursor: str | None = Query(default=None, max_length=256),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if (latitude is None) != (longitude is None):
        raise HTTPException(status_code=422, detail="Supply both coordinates or neither")
    cursor_value = _catalogue_cursor(cursor)
    if cursor_value is not None and ((latitude is None) != (cursor_value.distance_m is None)):
        raise HTTPException(status_code=422, detail="Cursor sort does not match the story catalogue")
    result = await list_public_story_page(
        session,
        page_size=page_size,
        cursor=cursor_value,
        search=search.strip() if search and search.strip() else None,
        language=language.strip() if language and language.strip() else None,
        region=region.strip() if region and region.strip() else None,
        media_format=media_format.strip() if media_format and media_format.strip() else None,
        bbox=_catalogue_bbox(bbox),
        latitude=latitude,
        longitude=longitude,
    )
    return {
        "items": [_story_v2(item) for item in result["items"]],
        "nextCursor": result["next_cursor"],
    }


@app.get("/v2/stories/nearby")
async def nearby_stories_v2(
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
    radius_m: float = Query(default=50_000, gt=0, le=500_000, alias="radiusM"),
    page_size: int = Query(default=20, ge=1, le=100, alias="pageSize"),
    cursor: str | None = Query(default=None, max_length=256),
    session: AsyncSession = Depends(get_session),
) -> dict:
    cursor_value = _catalogue_cursor(cursor)
    if cursor_value is not None and cursor_value.distance_m is None:
        raise HTTPException(status_code=422, detail="Cursor sort does not match the nearby story catalogue")
    result = await list_public_story_page(
        session,
        page_size=page_size,
        cursor=cursor_value,
        latitude=latitude,
        longitude=longitude,
        radius_m=radius_m,
    )
    return {
        "items": [_story_v2(item) for item in result["items"]],
        "nextCursor": result["next_cursor"],
    }


@app.api_route("/v1/stories/{story_id}/media", methods=["GET", "HEAD"])
async def story_media(
    story_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Response:
    media_file = await published_story_media_file(session, story_id)
    if not media_file:
        raise HTTPException(status_code=404, detail="Approved story media is not available")
    return await run_in_threadpool(media_response, media_file, request.headers.get("range"), request.method == "HEAD")


@app.api_route("/v1/stories/{story_id}/hls/{asset_path:path}", methods=["GET", "HEAD"])
async def story_hls_asset(
    story_id: str,
    asset_path: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Response:
    playlist_file = await published_story_media_file(session, story_id)
    if not playlist_file:
        raise HTTPException(status_code=404, detail="Approved story media is not available")
    object_key = published_hls_object_key(playlist_file, asset_path)
    if not object_key:
        raise HTTPException(status_code=404, detail="Approved video stream asset is not available")
    if asset_path.endswith(".m3u8"):
        body = await run_in_threadpool(media_bytes, object_key)
        base = f"/asante/api/v1/stories/{story_id}/hls/"
        # Nested quality playlists resolve relative segment names against their own folder.
        playlist_dir = asset_path.rsplit("/", 1)[0] if "/" in asset_path else ""
        lines: list[str] = []
        for line in body.decode("utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                candidate = stripped
                if playlist_dir and "/" not in candidate and not candidate.startswith("."):
                    candidate = f"{playlist_dir}/{candidate}"
                if published_hls_object_key(playlist_file, candidate):
                    line = base + candidate
            lines.append(line)
        return Response(
            content="\n".join(lines) + "\n",
            media_type="application/vnd.apple.mpegurl",
            headers={"Cache-Control": "no-store"},
        )
    return await run_in_threadpool(media_response, object_key, request.headers.get("range"), request.method == "HEAD")


@app.api_route("/v1/stories/{story_id}/poster", methods=["GET", "HEAD"])
async def story_poster(
    story_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Response:
    poster_file = await published_story_poster_file(session, story_id)
    if not poster_file:
        raise HTTPException(status_code=404, detail="Approved story thumbnail is not available")
    return await run_in_threadpool(media_response, poster_file, None, request.method == "HEAD")


@app.get("/v1/stories/{story_id}/captions")
async def story_captions(
    story_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    caption_state = await published_story_caption_state(session, story_id)
    if caption_state is None:
        raise HTTPException(status_code=404, detail="Approved story captions are not available")
    return caption_state


@app.get("/health")
def health() -> dict:
    return {"service": "asante-api", "status": "ok"}


@app.get("/health/ready")
async def readiness(session: AsyncSession = Depends(get_session)) -> dict:
    try:
        await session.execute(text("SELECT 1 FROM asante.stories LIMIT 1"))
        await session.execute(text("SELECT 1 FROM asante.accounts LIMIT 1"))
        if not await run_in_threadpool(lambda: storage_client().bucket_exists(media_bucket())):
            raise RuntimeError("Missing bucket")
    except Exception as error:
        raise HTTPException(503, "Asante database or media storage is unavailable") from error
    return {"service": "asante-api", "status": "ready", "database": "ok", "mediaStorage": "ok"}


@app.get("/v1/landmarks/nearby")
async def nearby_landmarks(
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
    radius_m: float = Query(default=50_000, gt=0, le=500_000),
    limit: int = Query(default=20, gt=0, le=100),
    session: AsyncSession = Depends(get_session),
) -> dict:
    items = await list_nearby_landmarks(session, latitude, longitude, radius_m, limit)
    return {"items": items}


@app.get("/v1/stories/nearby")
async def nearby_stories(
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
    radius_m: float = Query(default=50_000, gt=0, le=500_000),
    limit: int = Query(default=20, gt=0, le=100),
    session: AsyncSession = Depends(get_session),
) -> dict:
    return {"items": await list_published_stories(session, latitude, longitude, radius_m, limit)}


@app.post("/v1/story-projects/plan", dependencies=[Depends(mutation)])
def plan_story(request: PlanRequest) -> dict:
    from .ai.workers import run_planner

    plan = run_planner(
        {
            "topic": request.topic,
            "place_name": request.place_name,
            "language": request.language,
            "media_format": request.media_format,
            "audience": request.audience,
        }
    )
    return {
        "project_id": f"project_{uuid4().hex[:12]}",
        "trace_id": f"trace_{uuid4().hex[:12]}",
        "topic": plan.get("topic") or request.topic,
        "place_name": plan.get("place_name") or request.place_name,
        "language": plan.get("language") or request.language,
        "media_format": plan.get("media_format") or request.media_format,
        "audience": plan.get("audience") or request.audience,
        "worker_steps": plan.get("worker_steps") or [],
        "questions": plan.get("questions") or [],
        "outline": plan.get("outline") or [],
        "checklist": plan.get("checklist") or [],
        "unknowns": plan.get("unknowns") or [],
        "human_gate": "A human reviewer must approve publication. Asante workers cannot publish.",
        "aiUsed": bool(plan.get("aiUsed")),
    }


