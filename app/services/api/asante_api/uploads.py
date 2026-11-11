"""Expiring owner-scoped uploads with bounded temporary files and media probing."""
from __future__ import annotations

from datetime import timedelta
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, model_validator
from typing import Literal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool
from minio.error import S3Error
from urllib3.exceptions import HTTPError

from .database import get_session
from .media_process import MediaProcessError, process_upload_file
from .models import ContributorRecord, MediaDerivativeRecord, ProjectRevision, SubmissionPacket, UploadRecord
from .storage import media_bucket, media_response, storage_client
from .workspace import mutation, now, owner, project_for

router = APIRouter(prefix="/v1")
MAX_AUDIO_BYTES = 100 * 1024 * 1024
MAX_VIDEO_BYTES = 500 * 1024 * 1024
MAX_DOCUMENT_BYTES = 25 * 1024 * 1024


def max_upload_bytes(content_type: str) -> int:
    if content_type == "application/pdf":
        return MAX_DOCUMENT_BYTES
    return MAX_VIDEO_BYTES if content_type.startswith("video/") else MAX_AUDIO_BYTES


class UploadInput(BaseModel):
    project_id: str = Field(max_length=64)
    name: str = Field(min_length=1, max_length=300)
    size: int = Field(gt=0, le=MAX_VIDEO_BYTES)
    content_type: Literal["audio/mpeg", "audio/wav", "audio/x-wav", "audio/ogg", "video/mp4", "video/webm", "application/pdf"]
    purpose: Literal["media", "supporting_document"] = "media"
    consent_given: Literal[True]

    @model_validator(mode="after")
    def validate_size_for_media_type(self) -> "UploadInput":
        if self.purpose == "supporting_document" and self.content_type != "application/pdf":
            raise ValueError("Supporting documents must be PDF files")
        if self.purpose == "media" and self.content_type == "application/pdf":
            raise ValueError("PDF files must be uploaded as supporting documents")
        limit = max_upload_bytes(self.content_type)
        if self.size > limit:
            label = "25 MiB" if self.content_type == "application/pdf" else "500 MiB" if self.content_type.startswith("video/") else "100 MiB"
            raise ValueError(f"{self.content_type.split('/')[0].capitalize()} recordings must be {label} or smaller")
        return self


@router.post("/uploads", status_code=201, dependencies=[Depends(mutation)])
async def upload_intent(body: UploadInput, contributor: ContributorRecord = Depends(owner), session: AsyncSession = Depends(get_session)) -> dict:
    project = await project_for(session, body.project_id, contributor.id, lock=True)
    if await session.scalar(select(SubmissionPacket.id).where(SubmissionPacket.project_id == project.id)):
        raise HTTPException(409, "Submitted media is preserved. Duplicate the project first.")
    prefix = "supporting-documents" if body.purpose == "supporting_document" else "originals"
    upload = UploadRecord(id=uuid4().hex, project_id=project.id, contributor_id=contributor.id, object_key=f"{prefix}/{contributor.id}/{uuid4().hex}", name=body.name, content_type=body.content_type, size=body.size, checksum="", purpose=body.purpose, consent_scope="media_storage_and_review", consent_recorded_at=now(), status="pending", expires_at=now() + timedelta(minutes=5))
    session.add(upload)
    await session.commit()
    return {"id": upload.id, "uploadUrl": f"/asante/api/v1/uploads/{upload.id}/content", "expiresAt": upload.expires_at.isoformat()}


def inspect_media(path: str, expected_type: str) -> str:
    try:
        result = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=format_name,duration:stream=codec_type", "-of", "json", path], capture_output=True, timeout=20, check=False)
        if result.returncode:
            raise ValueError("Invalid media")
        info = json.loads(result.stdout)
        name = info["format"]["format_name"]
        duration = float(info["format"]["duration"])
        has_video = any(stream["codec_type"] == "video" for stream in info["streams"])
        if "mp3" in name:
            detected = "audio/mpeg"
        elif "wav" in name:
            detected = "audio/wav"
        elif "ogg" in name and not has_video:
            detected = "audio/ogg"
        elif "webm" in name and has_video:
            detected = "video/webm"
        elif "mp4" in name and has_video:
            detected = "video/mp4"
        else:
            raise ValueError("Unsupported media")
        if not 0 < duration <= 600 or detected != expected_type.replace("audio/x-wav", "audio/wav"):
            raise ValueError("Wrong media type or duration")
        return detected
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError, TypeError) as error:
        raise HTTPException(422, "Choose a valid supported recording of up to ten minutes matching its file type") from error


def inspect_pdf(path: str, expected_type: str) -> str:
    try:
        with open(path, "rb") as handle:
            header = handle.read(5)
        if expected_type != "application/pdf" or header != b"%PDF-":
            raise ValueError("Invalid PDF")
        return "application/pdf"
    except (OSError, ValueError) as error:
        raise HTTPException(422, "Choose a valid PDF supporting document") from error


@router.put("/uploads/{upload_id}/content", dependencies=[Depends(mutation)])
async def upload_content(upload_id: str, request: Request, contributor: ContributorRecord = Depends(owner), session: AsyncSession = Depends(get_session)) -> dict:
    upload = await session.get(UploadRecord, upload_id, with_for_update=True)
    if not upload or upload.contributor_id != contributor.id:
        raise HTTPException(404, "Upload not found")
    if upload.status != "pending" or upload.expires_at <= now():
        raise HTTPException(409, "Upload expired or already completed; request a new upload")
    project = await project_for(session, upload.project_id, contributor.id, lock=True)
    if await session.scalar(select(SubmissionPacket.id).where(SubmissionPacket.project_id == project.id)):
        raise HTTPException(409, "Submitted media cannot be replaced")
    total = 0
    digest = hashlib.sha256()
    # ffprobe needs a seekable path. This OS temporary file is always unlinked;
    # originals are never retained in an application/container media directory.
    with tempfile.NamedTemporaryFile(prefix="asante-upload-") as temporary:
        async for chunk in request.stream():
            total += len(chunk)
            limit = max_upload_bytes(upload.content_type)
            if total > min(upload.size, limit):
                label = "25 MiB" if upload.content_type == "application/pdf" else "500 MiB" if upload.content_type.startswith("video/") else "100 MiB"
                raise HTTPException(413, f"Recording exceeds its declared size or {label}")
            digest.update(chunk)
            await run_in_threadpool(temporary.write, chunk)
        if total != upload.size:
            raise HTTPException(422, "Recording is incomplete; upload the whole file")
        temporary.flush()
        detected = await run_in_threadpool(inspect_pdf if upload.purpose == "supporting_document" else inspect_media, temporary.name, upload.content_type)
        client = storage_client()
        try:
            await run_in_threadpool(client.fput_object, media_bucket(), upload.object_key, temporary.name, content_type=detected)
        except (S3Error, HTTPError) as error:
            raise HTTPException(503, "Media storage is unavailable; retry this upload") from error
        derivatives_summary: dict = {}
        if upload.purpose == "media":
            try:
                with tempfile.TemporaryDirectory(prefix="asante-upload-derivatives-") as derivative_dir:
                    processed = await run_in_threadpool(process_upload_file, temporary.name, derivative_dir, upload.id)
                    for item in processed["derivatives"]:
                        kind = str(item["kind"])
                        suffix = Path(item["path"]).suffix or ".bin"
                        object_key = f"derivatives/{upload.id}/{kind}-{uuid4().hex}{suffix}"
                        derivative_id = uuid4().hex
                        await run_in_threadpool(client.fput_object, media_bucket(), object_key, item["path"], content_type=item["contentType"])
                        meta = {key: value for key, value in item.items() if key != "path"}
                        session.add(
                            MediaDerivativeRecord(
                                id=derivative_id,
                                upload_id=upload.id,
                                kind=kind if kind in {"audio_track", "poster", "keyframe"} else "keyframe",
                                object_key=object_key,
                                content_type=item["contentType"],
                                status="ready",
                                meta=meta,
                            )
                        )
                        if kind == "audio_track":
                            derivatives_summary["audio_track"] = {"id": derivative_id, "contentType": item["contentType"], "duration": item.get("duration")}
                        elif kind == "poster":
                            derivatives_summary["poster"] = {"id": derivative_id, "contentType": item["contentType"], "timestamp": item.get("timestamp")}
                        elif kind == "keyframe":
                            derivatives_summary.setdefault("keyframes", []).append({"id": derivative_id, "timestamp": item.get("timestamp"), "index": item.get("index")})
                    derivatives_summary["probe"] = processed.get("probe") or {}
            except (MediaProcessError, OSError, S3Error, HTTPError, subprocess.TimeoutExpired) as error:
                raise HTTPException(422, f"Media verified but derivative processing failed: {error.__class__.__name__}") from error
    upload.content_type = detected
    upload.checksum = digest.hexdigest()
    upload.status = "verified"
    project.content = {
        **project.content,
        **({"supportingDocumentUploadId": upload.id} if upload.purpose == "supporting_document" else {
            "uploadId": upload.id,
            "format": "video" if detected.startswith("video/") else "audio",
            "mediaDerivatives": derivatives_summary,
        }),
    }
    project.version += 1
    session.add(ProjectRevision(id=uuid4().hex, project_id=project.id, version=project.version, content=project.content))
    media_jobs: list[dict] = []
    if upload.purpose == "media":
        from .ai.jobs import enqueue_project_media_jobs, public_job

        queued = await enqueue_project_media_jobs(session, project=project, upload=upload)
        media_jobs = [public_job(job) for job in queued]
    await session.commit()
    return {"id": upload.id, "status": "verified", "purpose": upload.purpose, "size": total, "checksum": upload.checksum, "mediaDerivatives": derivatives_summary, "mediaJobs": media_jobs}


@router.api_route("/uploads/{upload_id}/media", methods=["GET", "HEAD"])
async def private_media(upload_id: str, request: Request, contributor: ContributorRecord = Depends(owner), session: AsyncSession = Depends(get_session)) -> Response:
    upload = await session.get(UploadRecord, upload_id)
    if not upload or upload.contributor_id != contributor.id or upload.status != "verified":
        raise HTTPException(404, "Media not found")
    return await run_in_threadpool(media_response, upload.object_key, request.headers.get("range"), request.method == "HEAD")
