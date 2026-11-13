"""Persistent, owner-scoped local contributor workspace and review API."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
from io import BytesIO
import json
import os
import secrets
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field, JsonValue, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool
from starlette.background import BackgroundTask
from starlette.responses import StreamingResponse

from .database import get_session
from .models import ContributorRecord, WorkspaceSession, ProjectRecord, ProjectRevision, UploadRecord, SubmissionPacket, DecisionRecord, AccountRecord, MediaDerivativeRecord
from .storage import media_response, storage_client, media_bucket
from .auth import _set_csrf_cookie, mutation, optional_account, public_account, require_contributor, require_reviewer, ACCOUNT_COOKIE
from .catalogue import list_published_stories, public_caption_tracks
from .research_brief import ResearchBrief, brief_complete, research_input_hash

router = APIRouter(prefix="/v1")
COOKIE = "asante_workspace"


def now() -> datetime:
    return datetime.now(timezone.utc)


async def device_owner(request: Request, session: AsyncSession = Depends(get_session)) -> ContributorRecord:
    account = await optional_account(request, session)
    if account:
        return await session.get(ContributorRecord, account.contributor_id)
    token = request.cookies.get(COOKIE, "")
    record = await session.get(WorkspaceSession, hashlib.sha256(token.encode()).hexdigest()) if token else None
    if record is None or record.expires_at <= now():
        raise HTTPException(401, "Open your Asante workspace first")
    if await session.scalar(select(AccountRecord.id).where(AccountRecord.contributor_id == record.contributor_id)):
        raise HTTPException(401, "Sign in to your Asante account")
    return await session.get(ContributorRecord, record.contributor_id)


async def owner(account: AccountRecord = Depends(require_contributor), session: AsyncSession = Depends(get_session)) -> ContributorRecord:
    return await session.get(ContributorRecord, account.contributor_id)


@router.post("/review/session", dependencies=[Depends(mutation)])
async def review_session(account: AccountRecord = Depends(require_reviewer)) -> dict:
    return public_account(account)


class ProfileInput(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=3, max_length=254)
    bio: str = Field(default="", max_length=5000)
    language: Literal["en", "zu", "st"] = "en"


class ProjectInput(BaseModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    title: str = Field(default="", max_length=200)
    place: Literal[
        "Constitution Hill", "Soweto Towers", "Mapungubwe Hill", "District Six",
        "Addis Ababa", "Kampala", "Cairo", "Lagos", "Accra",
    ] = "Constitution Hill"
    language: Literal["en", "zu", "st"] = "en"
    format: Literal["audio", "video"] = "audio"
    audience: str = Field(default="Community listeners", max_length=120)
    transcript: str = Field(default="", max_length=20000)
    claim: str = Field(default="", max_length=5000)
    source: str = Field(default="", max_length=2000)
    consent: bool = False
    plan: dict[str, JsonValue] | None = None
    planDocument: dict[str, JsonValue] | None = None
    research: dict[str, JsonValue] | None = None
    researchBrief: ResearchBrief | None = None
    suggestion: Literal["pending", "accepted", "rejected"] = "pending"
    uploadId: str | None = Field(default=None, max_length=64)
    supportingDocumentUploadId: str | None = Field(default=None, max_length=64)
    version: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_source(self):
        if self.source and not self.source.startswith("https://"):
            raise ValueError("Source URL must use HTTPS")
        if len(json.dumps(self.plan)) > 40000:
            raise ValueError("Planning brief is too large")
        if len(json.dumps(self.planDocument)) > 160000:
            raise ValueError("Field report document is too large")
        if len(json.dumps(self.research)) > 120000:
            raise ValueError("Research packet is too large")
        return self


class ImportInput(BaseModel):
    profile: ProfileInput | None = None
    projects: list[ProjectInput] = Field(default_factory=list, max_length=100)
    preferences: dict[str, str] = Field(default_factory=dict)
    browser_data: dict[str, str] = Field(default_factory=dict)
    consent: Literal[True]

    @model_validator(mode="after")
    def validate_preferences(self):
        if len(json.dumps(self.preferences)) > 100000 or any(not key.startswith("asante.") for key in self.preferences):
            raise ValueError("Only Asante preferences can be imported")
        if len(json.dumps(self.browser_data)) > 2000000 or any(not key.startswith(("local:asante.", "session:asante.")) for key in self.browser_data):
            raise ValueError("Only Asante browser data can be backed up")
        return self


async def project_for(session: AsyncSession, project_id: str, contributor_id: str, lock: bool = False) -> ProjectRecord:
    query = select(ProjectRecord).where(ProjectRecord.id == project_id, ProjectRecord.contributor_id == contributor_id)
    if lock:
        query = query.with_for_update()
    project = await session.scalar(query)
    if not project:
        raise HTTPException(404, "Project not found")
    return project


class DownloadInput(BaseModel):
    expectedVersion: int = Field(ge=1)


@router.post("/workspace/projects/{project_id}/download.zip", dependencies=[Depends(mutation)])
async def download_project_pack(project_id: str, body: DownloadInput, contributor: ContributorRecord = Depends(owner), session: AsyncSession = Depends(get_session)) -> Response:
    project = await project_for(session, project_id, contributor.id)
    if project.version != body.expectedVersion:
        raise HTTPException(409, "The project changed. Refresh before downloading the pack.")
    content = project.content or {}
    profile = contributor.profile or {}
    upload = await session.get(UploadRecord, content.get("uploadId")) if content.get("uploadId") else None
    media_reference = None
    if upload:
        if upload.contributor_id != contributor.id or upload.project_id != project.id or upload.status != "verified":
            raise HTTPException(409, "Only verified project media can be included in the download pack.")
        media_reference = {"objectKey": upload.object_key, "name": upload.name, "type": upload.content_type, "size": upload.size, "checksum": upload.checksum}
    packet = {**content, "projectId": project.id, "version": project.version, "attribution": profile.get("name", ""), "contributor": {"name": profile.get("name", ""), "email": profile.get("email", "")}}
    from .story_packet import build_packet_archive
    archive = await run_in_threadpool(build_packet_archive, packet, content.get("planDocument"), media_reference)
    archive.seek(0, 2)
    size = archive.tell()
    archive.seek(0)
    return StreamingResponse(iter(lambda: archive.read(64 * 1024), b""), media_type="application/zip", headers={"Cache-Control": "no-store", "Content-Disposition": f'attachment; filename="asante-{project.id}-pack.zip"', "Content-Length": str(size)}, background=BackgroundTask(archive.close))


async def project_output(session: AsyncSession, project: ProjectRecord) -> dict:
    from .ai.jobs import list_jobs_for_project, public_job

    packet = await session.scalar(select(SubmissionPacket).where(SubmissionPacket.project_id == project.id))
    upload = await session.get(UploadRecord, project.content.get("uploadId")) if project.content.get("uploadId") else None
    document_upload = await session.get(UploadRecord, project.content.get("supportingDocumentUploadId")) if project.content.get("supportingDocumentUploadId") else None
    media = None
    if upload and upload.status == "verified" and upload.purpose == "media":
        media = {"id": upload.id, "name": upload.name, "size": upload.size, "type": upload.content_type, "checksum": upload.checksum, "url": f"/asante/api/v1/uploads/{upload.id}/media"}
    supporting_document = None
    if document_upload and document_upload.status == "verified" and document_upload.purpose == "supporting_document":
        supporting_document = {"id": document_upload.id, "name": document_upload.name, "size": document_upload.size, "type": document_upload.content_type, "checksum": document_upload.checksum, "url": f"/asante/api/v1/uploads/{document_upload.id}/media"}
    jobs = await list_jobs_for_project(session, project.id)
    media_job_types = {"transcribe", "translate", "analyze"}
    submission_media = [job for job in jobs if job.submission_id and job.job_type in media_job_types]
    draft_media = [job for job in jobs if job.submission_id is None and job.job_type in media_job_types]
    media_jobs = submission_media or draft_media
    transcript_job = next((job for job in media_jobs if job.job_type == "transcribe"), None)
    translate_job = next((job for job in media_jobs if job.job_type == "translate"), None)
    analysis_job = next((job for job in media_jobs if job.job_type == "analyze"), None)
    return {
        **project.content,
        "id": project.id,
        "version": project.version,
        "submissionId": packet.id if packet else None,
        "status": packet.status if packet else "draft",
        "media": media,
        "supportingDocument": supporting_document,
        "mediaJobs": [public_job(job) for job in media_jobs],
        "transcriptDraft": (transcript_job.result_payload or {}).get("transcriptDraft") if transcript_job else None,
        "translations": (translate_job.result_payload or {}).get("translations") if translate_job else None,
        "videoAnalysis": (analysis_job.result_payload or {}).get("videoAnalysis") if analysis_job else None,
    }


async def workspace_output(session: AsyncSession, contributor: ContributorRecord) -> dict:
    projects = (await session.scalars(select(ProjectRecord).where(ProjectRecord.contributor_id == contributor.id).order_by(ProjectRecord.id))).all()
    account = await session.scalar(select(AccountRecord).where(AccountRecord.contributor_id == contributor.id))
    published = await list_published_stories(session, contributor_id=contributor.id)
    return {"account": public_account(account) if account else None, "profile": contributor.profile or None, "projects": [await project_output(session, project) for project in projects], "preferences": contributor.preferences, "publishedStories": published}


@router.post("/workspace/session", dependencies=[Depends(mutation)])
async def open_workspace(request: Request, response: Response, session: AsyncSession = Depends(get_session)) -> dict:
    account = await optional_account(request, session)
    if account:
        token = request.cookies.get(ACCOUNT_COOKIE, "")
        if token:
            _set_csrf_cookie(request, response, token)
        return await workspace_output(session, await session.get(ContributorRecord, account.contributor_id))
    token = request.cookies.get(COOKIE, "")
    record = await session.get(WorkspaceSession, hashlib.sha256(token.encode()).hexdigest()) if token else None
    if record and record.expires_at > now() and not await session.scalar(select(AccountRecord.id).where(AccountRecord.contributor_id == record.contributor_id)):
        contributor = await session.get(ContributorRecord, record.contributor_id)
    else:
        contributor = ContributorRecord(id=uuid4().hex, profile={}, preferences={})
        session.add(contributor)
        await session.flush()
        token = secrets.token_urlsafe(48)
        session.add(WorkspaceSession(token_hash=hashlib.sha256(token.encode()).hexdigest(), contributor_id=contributor.id, expires_at=now() + timedelta(days=90)))
        await session.commit()
    response.set_cookie(COOKIE, token, httponly=True, secure=request.headers.get("x-forwarded-proto", request.url.scheme) == "https", samesite="strict", max_age=90 * 86400, path="/asante/api")
    _set_csrf_cookie(request, response, token)
    response.headers["Cache-Control"] = "no-store"
    return await workspace_output(session, contributor)


@router.get("/workspace")
async def get_workspace(response: Response, contributor: ContributorRecord = Depends(device_owner), session: AsyncSession = Depends(get_session)) -> dict:
    response.headers["Cache-Control"] = "no-store"
    return await workspace_output(session, contributor)


class PreferenceInput(BaseModel):
    key: str = Field(pattern=r"^asante\.(onboarding\.v2|portalGuide\.v1|portalResearchGuide\.v1|portalMediaGuide\.v1|portalSubmitGuide\.v1|playback\.[a-zA-Z0-9_-]{1,100}|lowData|liveLocation)$")
    value: str | None = Field(default=None, max_length=256)


@router.post("/workspace/preferences", dependencies=[Depends(mutation)])
async def save_preference(body: PreferenceInput, contributor: ContributorRecord = Depends(device_owner), session: AsyncSession = Depends(get_session)) -> dict:
    contributor = await session.scalar(select(ContributorRecord).where(ContributorRecord.id == contributor.id).with_for_update().execution_options(populate_existing=True))
    preferences = {**contributor.preferences}
    if body.value is None:
        preferences.pop(body.key, None)
    else:
        preferences[body.key] = body.value
    if len(json.dumps(preferences)) > 100000:
        raise HTTPException(422, "Preference storage limit reached")
    contributor.preferences = preferences
    await session.commit()
    return {"saved": True}


@router.post("/workspace/profile", dependencies=[Depends(mutation)])
async def save_profile(body: ProfileInput, contributor: ContributorRecord = Depends(owner), session: AsyncSession = Depends(get_session)) -> dict:
    account = await session.scalar(select(AccountRecord).where(AccountRecord.contributor_id == contributor.id))
    if account and body.email.strip().lower() != account.email:
        raise HTTPException(422, "Sign-in email cannot be changed through profile edits")
    contributor.profile = body.model_dump()
    await session.commit()
    return contributor.profile


@router.post("/workspace/projects", dependencies=[Depends(mutation)])
async def save_project(body: ProjectInput, contributor: ContributorRecord = Depends(owner), session: AsyncSession = Depends(get_session)) -> dict:
    # Serialize project creation/imports within a workspace, and use version checks for edits.
    await session.scalar(select(ContributorRecord).where(ContributorRecord.id == contributor.id).with_for_update())
    project = await session.get(ProjectRecord, body.id, with_for_update=True)
    if project and project.contributor_id != contributor.id:
        raise HTTPException(404, "Project not found")
    if (project.version if project else 0) != body.version:
        raise HTTPException(409, "This draft changed. Reload before saving; your text is still on screen.")
    if project and await session.scalar(select(SubmissionPacket.id).where(SubmissionPacket.project_id == project.id)):
        raise HTTPException(409, "Submitted revisions are preserved. Duplicate this project to edit.")
    if body.uploadId:
        upload = await session.get(UploadRecord, body.uploadId)
        if not upload or upload.purpose != "media" or upload.contributor_id != contributor.id or upload.project_id != body.id or upload.status != "verified":
            raise HTTPException(422, "Choose verified media for this project")
    if body.supportingDocumentUploadId:
        document = await session.get(UploadRecord, body.supportingDocumentUploadId)
        if not document or document.purpose != "supporting_document" or document.content_type != "application/pdf" or document.contributor_id != contributor.id or document.project_id != body.id or document.status != "verified":
            raise HTTPException(422, "Choose a verified PDF supporting document for this project")
    content = body.model_dump(exclude={"version", "id"})
    previous = project.content if project else {}
    if previous.get("generatedReportHash"):
        content["generatedReportHash"] = previous["generatedReportHash"]
    if research_input_hash(content) == research_input_hash(previous):
        # Run state is server-owned; ordinary saves cannot forge or erase it.
        if previous.get("researchFlow"):
            content["researchFlow"] = previous["researchFlow"]
    elif content.get("researchBrief") is not None:
        content["researchFlow"] = {"status": "saved" if brief_complete(content) else "incomplete", "inputHash": research_input_hash(content)}
    if project:
        project.version += 1
        project.content = content
    else:
        if not contributor.profile:
            raise HTTPException(422, "Save your contributor profile first")
        project = ProjectRecord(id=body.id, contributor_id=contributor.id, version=1, content=content)
        session.add(project)
    await session.flush()
    session.add(ProjectRevision(id=uuid4().hex, project_id=project.id, version=project.version, content=content))
    await session.commit()
    return await project_output(session, project)


@router.post("/workspace/import", dependencies=[Depends(mutation)])
async def import_workspace(body: ImportInput, contributor: ContributorRecord = Depends(owner), session: AsyncSession = Depends(get_session)) -> dict:
    await session.scalar(select(ContributorRecord).where(ContributorRecord.id == contributor.id).with_for_update())
    if contributor.profile and body.profile and contributor.profile != body.profile.model_dump():
        raise HTTPException(409, "The browser profile differs from this workspace. Resolve it before import.")
    if body.profile:
        contributor.profile = body.profile.model_dump()
    contributor.preferences = {**contributor.preferences, **body.preferences}
    for item in body.projects:
        # Old submission IDs and upload metadata are claims, never imported as approvals/assets.
        content = item.model_copy(update={"uploadId": None, "consent": False}).model_dump(exclude={"version", "id"})
        project = await session.get(ProjectRecord, item.id)
        if project:
            if project.contributor_id != contributor.id or project.content != content:
                raise HTTPException(409, "A browser draft conflicts with a saved project; browser data was retained")
            continue
        if not contributor.profile:
            raise HTTPException(422, "A contributor profile is required to import drafts")
        project = ProjectRecord(id=item.id, contributor_id=contributor.id, version=1, content=content)
        session.add(project)
        await session.flush()
        session.add(ProjectRevision(id=uuid4().hex, project_id=item.id, version=1, content=content))
    raw = json.dumps(body.browser_data, sort_keys=True, separators=(",", ":")).encode()
    checksum = hashlib.sha256(raw).hexdigest()
    key = f"imports/{contributor.id}/{checksum}.json"
    try:
        await run_in_threadpool(storage_client().put_object, media_bucket(), key, BytesIO(raw), len(raw), content_type="application/json")
    except Exception as error:
        raise HTTPException(503, "Browser backup could not be saved; keep browser data") from error
    contributor.preferences = {**contributor.preferences, "asante.import.checksum": checksum}
    await session.commit()
    return {**await workspace_output(session, contributor), "importChecksum": checksum}


@router.get("/workspace/import-receipt/{checksum}")
async def import_receipt(checksum: str, contributor: ContributorRecord = Depends(device_owner)) -> dict:
    if len(checksum) != 64 or checksum != contributor.preferences.get("asante.import.checksum"):
        raise HTTPException(404, "Import receipt not found")
    def verify() -> bool:
        body = storage_client().get_object(media_bucket(), f"imports/{contributor.id}/{checksum}.json")
        try:
            digest = hashlib.sha256()
            for chunk in body.stream(65536):
                digest.update(chunk)
            return secrets.compare_digest(digest.hexdigest(), checksum)
        finally:
            body.close()
            body.release_conn()
    try:
        verified = await run_in_threadpool(verify)
    except Exception as error:
        raise HTTPException(503, "Import backup could not be verified; keep browser data") from error
    if not verified:
        raise HTTPException(503, "Import backup did not match; keep browser data")
    return {"checksum": checksum, "verified": True}


@router.get("/workspace/browser-backup")
async def browser_backup(contributor: ContributorRecord = Depends(device_owner)) -> Response:
    checksum = contributor.preferences.get("asante.import.checksum")
    if not checksum:
        raise HTTPException(404, "No browser backup has been imported")
    response = await run_in_threadpool(media_response, f"imports/{contributor.id}/{checksum}.json", None)
    response.headers["Content-Disposition"] = 'attachment; filename="asante-browser-backup.json"'
    return response


class SubmissionInput(BaseModel):
    project_id: str = Field(max_length=64)
    expected_version: int = Field(ge=1)
    consent_given: Literal[True]
    preview_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


ASSESSMENT_VERSION = "asante.review-policy.v1"

_PRIVATE_REVIEW_KEYS = {"research", "researchBrief", "researchFlow", "source_url", "plan", "plan_document", "planDocument", "project_revision", "worker_run_ids", "worker_runs"}
_PRIVATE_REVIEW_FINDINGS = {"planner", "research", "worker_trace", "source_metadata", "worker_trace_linkage"}


def reviewer_packet(packet: dict) -> dict:
    """Return only contributor-submitted story evidence safe for reviewer display."""
    return {key: value for key, value in packet.items() if key not in _PRIVATE_REVIEW_KEYS}


def reviewer_assessment(result: dict) -> dict:
    """Strip private research source rows and citations from assessment output."""
    safe = {key: value for key, value in result.items() if key not in {"sources"}}
    claim_evidence = safe.get("claimEvidence")
    if isinstance(claim_evidence, dict):
        claim_evidence = {key: value for key, value in claim_evidence.items() if key != "sources"}
        claims = claim_evidence.get("claims")
        if isinstance(claims, list):
            claim_evidence["claims"] = [
                {key: value for key, value in claim.items() if key not in {"sourceIds", "excerpts"}}
                for claim in claims if isinstance(claim, dict)
            ]
        safe["claimEvidence"] = claim_evidence
    provenance = safe.get("provenance")
    if isinstance(provenance, dict) and isinstance(provenance.get("checks"), list):
        provenance["checks"] = [check for check in provenance["checks"] if isinstance(check, dict) and check.get("check") not in {"source_metadata", "worker_trace_linkage"}]
        safe["provenance"] = provenance
    return safe


def review_policy(packet: dict, jobs: list | None = None) -> dict:
    from .ai.workers import run_verifier

    jobs = jobs or []
    assessment = next((job for job in jobs if job.job_type == "assessment"), None)
    result = (assessment.result_payload or {}) if assessment else {}
    provenance = result.get("provenance") or {}
    claims = result.get("claimEvidence") or {}
    findings = []
    verifier = run_verifier(packet, worker_runs=packet.get("worker_runs") or [])
    for finding in verifier.get("findings", []):
        if finding.get("kind") in {"consent", "media"}:
            continue
        if finding.get("kind") in _PRIVATE_REVIEW_FINDINGS:
            continue
        findings.append({"check": finding.get("kind", "verifier"), "status": finding.get("status", "attention"), "detail": finding.get("message", "")})
    if not packet.get("consent_given") or not packet.get("consent_scope"):
        findings.append({"check": "Consent scope", "status": "blocked", "detail": "Recorded consent for storage and review is required."})
    if not packet.get("media_verified") or not packet.get("original_media", {}).get("checksum"):
        findings.append({"check": "Original media", "status": "blocked", "detail": "A server-verified original with checksum is required."})
    for check in provenance.get("checks", []):
        status = {"pass": "pass", "attention": "attention", "incomplete": "attention", "blocked": "blocked"}.get(check.get("status"), "attention")
        if check.get("check") not in {"consent", "media_integrity_reference"} and check.get("check") not in _PRIVATE_REVIEW_FINDINGS:
            findings.append({"check": check.get("check", "Provenance"), "status": status, "detail": check.get("detail", "")})
    if not assessment or assessment.status in {"queued", "running"}:
        findings.append({"check": "Submission assessment", "status": "blocked", "detail": "Required evidence assessment is pending."})
    elif assessment.status != "succeeded" or result.get("status") not in {"complete", "partial"}:
        findings.append({"check": "Submission assessment", "status": "attention", "detail": "Automated assessment is unavailable or incomplete; review the contributor evidence manually."})
    elif claims.get("status") != "complete":
        findings.append({"check": "Claim comparison", "status": "attention", "detail": "Claim comparison is incomplete; use human judgement and the contributor evidence."})
    else:
        findings.append({"check": "Claim comparison", "status": "attention", "detail": "Claim findings are decision support and require human judgment."})
    for job in jobs:
        if job.job_type in {"transcribe", "analyze"} and job.status in {"queued", "running", "failed"}:
            findings.append({"check": f"{job.job_type} draft", "status": "attention", "detail": f"Media job is {job.status}; inspect its explicit state."})
    blocked = any(item["status"] == "blocked" for item in findings)
    assessment_ref = f"{ASSESSMENT_VERSION};{getattr(assessment, 'id', 'unknown') if assessment else 'missing'};{result.get('schemaVersion', 'unavailable')};{str(result.get('inputHash') or 'no-hash')[:32]}"
    return {"version": ASSESSMENT_VERSION, "assessment_version": assessment_ref[:180], "findings": findings, "may_approve": not blocked, "status": "blocked" if blocked else "human_review", "requires_human_review": True}


def _snapshot_hash(snapshot: dict) -> str:
    stable = {key: value for key, value in snapshot.items() if key not in {"created_at", "trace_id"}}
    raw = json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


async def build_submission_snapshot(session: AsyncSession, project: ProjectRecord, contributor: ContributorRecord, revision: ProjectRevision, upload: UploadRecord) -> dict:
    content = revision.content
    coordinates = {
        "Constitution Hill": (-26.1883, 28.0368), "Soweto Towers": (-26.2344, 27.9091),
        "Mapungubwe Hill": (-22.1920, 29.4311), "District Six": (-33.9273, 18.4242),
        "Addis Ababa": (9.0320, 38.7469), "Kampala": (0.3476, 32.5825),
        "Cairo": (30.0444, 31.2357), "Lagos": (6.5244, 3.3792), "Accra": (5.6037, -0.1870),
    }
    latitude, longitude = coordinates[content["place"]]
    derivatives = (await session.scalars(select(MediaDerivativeRecord).where(MediaDerivativeRecord.upload_id == upload.id, MediaDerivativeRecord.status == "ready").order_by(MediaDerivativeRecord.kind, MediaDerivativeRecord.id))).all()
    supporting_document = await session.get(UploadRecord, content.get("supportingDocumentUploadId")) if content.get("supportingDocumentUploadId") else None
    if supporting_document and (supporting_document.contributor_id != contributor.id or supporting_document.project_id != project.id or supporting_document.purpose != "supporting_document" or supporting_document.content_type != "application/pdf" or supporting_document.status != "verified"):
        raise HTTPException(422, "The supporting PDF is not a verified document for this project")
    snapshot = {
        "title": content.get("title", ""), "contributor_name": contributor.profile.get("name", ""),
        "contributor_id": contributor.id, "language": content.get("language", "en"), "media_format": content.get("format", "audio"),
        "audience": content.get("audience", ""), "place": content.get("place", ""), "latitude": latitude, "longitude": longitude,
        "consent_given": True, "consent_scope": upload.consent_scope, "consent_recorded_at": upload.consent_recorded_at.isoformat() if upload.consent_recorded_at else None,
        "summary": content.get("transcript", ""), "claim": content.get("claim", ""), "source_url": content.get("source", ""),
        "suggestion": content.get("suggestion", "pending"),
        "revision_id": revision.id, "revision_version": revision.version,
        "media_name": upload.name, "media_size": upload.size, "media_checksum": upload.checksum, "media_verified": upload.status == "verified",
        "original_media": {"uploadId": upload.id, "name": upload.name, "contentType": upload.content_type, "size": upload.size, "checksum": upload.checksum},
        "media_derivatives": [{"id": item.id, "kind": item.kind, "contentType": item.content_type, "meta": item.meta or {}} for item in derivatives],
        "supporting_document": {"uploadId": supporting_document.id, "name": supporting_document.name, "contentType": supporting_document.content_type, "size": supporting_document.size, "checksum": supporting_document.checksum} if supporting_document else None,
        "trace_id": "trace_" + uuid4().hex, "created_at": now().isoformat(), "human_gate": "required_before_publication",
    }
    snapshot["preview_hash"] = _snapshot_hash(snapshot)
    return snapshot


@router.get("/submissions/preview/{project_id}")
async def submission_preview(project_id: str, expected_version: int, contributor: ContributorRecord = Depends(owner), session: AsyncSession = Depends(get_session)) -> dict:
    project = await project_for(session, project_id, contributor.id)
    if project.version != expected_version:
        raise HTTPException(409, "Refresh your draft before previewing submission")
    content = project.content
    if not contributor.profile:
        raise HTTPException(422, "Save your contributor profile first")
    upload = await session.get(UploadRecord, content.get("uploadId")) if content.get("uploadId") else None
    if not upload or upload.status != "verified" or upload.project_id != project.id or upload.contributor_id != contributor.id:
        raise HTTPException(422, "Upload and verify your media before previewing submission")
    revision = await session.scalar(select(ProjectRevision).where(ProjectRevision.project_id == project.id, ProjectRevision.version == expected_version))
    if not revision:
        raise HTTPException(409, "Saved revision is unavailable")
    snapshot = await build_submission_snapshot(session, project, contributor, revision, upload)
    return {"packet": snapshot, "preview_hash": snapshot["preview_hash"], "revision_id": revision.id, "revision_version": revision.version}


async def packet_output(session: AsyncSession, packet: SubmissionPacket) -> dict:
    decisions = (await session.scalars(select(DecisionRecord).where(DecisionRecord.submission_id == packet.id).order_by(DecisionRecord.created_at, DecisionRecord.id))).all()
    from .ai.jobs import list_jobs_for_submission, public_job

    jobs = await list_jobs_for_submission(session, packet.id)
    visible_packet = reviewer_packet(packet.packet)
    policy = review_policy(visible_packet, jobs)
    assessment_job = next((job for job in jobs if job.job_type == "assessment"), None)
    assessment = reviewer_assessment((assessment_job.result_payload or {})) if assessment_job and assessment_job.result_payload else None
    transcript_job = next((job for job in jobs if job.job_type == "transcribe"), None)
    translation_job = next((job for job in jobs if job.job_type == "translate"), None)
    analysis_job = next((job for job in jobs if job.job_type == "analyze"), None)
    transcript_draft = (transcript_job.result_payload or {}).get("transcriptDraft") if transcript_job else None
    source_track = {"language": transcript_draft.get("language") or packet.packet.get("language") or "en", "label": "Original · AI transcript draft", "cues": transcript_draft.get("segments") or []} if isinstance(transcript_draft, dict) and transcript_draft.get("status") == "draft" else None
    translated_tracks = ((translation_job.result_payload or {}).get("captionTracks") or []) if translation_job else []
    caption_tracks = public_caption_tracks(([source_track] if source_track else []) + translated_tracks)
    safe_jobs = []
    for job in jobs:
        public = public_job(job)
        if job.job_type == "assessment":
            public["result"] = reviewer_assessment(public.get("result") or {})
        safe_jobs.append(public)
    publication = packet.packet or {}
    return {**visible_packet, "contributor_id": packet.contributor_id, "contributor_profile_url": f"/asante/profiles/{packet.contributor_id}/", "submission_id": packet.id, "status": packet.status, "version": packet.version, "published_story_id": publication.get("publishedStoryId"), "published_slug": publication.get("publishedSlug"), "published_at": publication.get("publishedAt"), "findings": policy["findings"], "review_policy": policy, "assessment": assessment, "transcriptDraft": (transcript_job.result_payload or {}).get("transcriptDraft") if transcript_job else None, "videoAnalysis": (analysis_job.result_payload or {}).get("videoAnalysis") if analysis_job else None, "decisions": [{"action": item.action, "reason": item.reason, "at": item.created_at.isoformat(), "reviewerId": item.reviewer_id, "assessmentVersion": item.assessment_version} for item in decisions], "media_url": f"/asante/api/v1/review/{packet.id}/media" if packet.upload_id else None, "supporting_document_url": f"/asante/api/v1/review/{packet.id}/supporting-document" if packet.packet.get("supporting_document") else None, "jobs": safe_jobs, "captionTracks": caption_tracks, "translations": ((translation_job.result_payload or {}).get("translations") or {}) if translation_job else {}}


@router.post("/submissions", status_code=201, dependencies=[Depends(mutation)])
async def submit_project(body: SubmissionInput, contributor: ContributorRecord = Depends(owner), session: AsyncSession = Depends(get_session)) -> dict:
    from .ai.jobs import enqueue_submission_jobs

    project = await project_for(session, body.project_id, contributor.id, lock=True)
    existing = await session.scalar(select(SubmissionPacket).where(SubmissionPacket.project_id == project.id))
    if existing:
        await enqueue_submission_jobs(session, existing)
        await session.commit()
        return await packet_output(session, existing)
    if project.version != body.expected_version:
        raise HTTPException(409, "Refresh your draft before submitting")
    content = project.content
    if len(content["title"].strip()) < 3 or not contributor.profile:
        raise HTTPException(422, "A title and contributor profile are required")
    upload = await session.get(UploadRecord, content.get("uploadId")) if content.get("uploadId") else None
    if not upload or upload.status != "verified" or upload.project_id != project.id or upload.contributor_id != contributor.id:
        raise HTTPException(422, "Upload and verify your media before submitting")
    try:
        stored = await run_in_threadpool(storage_client().stat_object, media_bucket(), upload.object_key)
        if stored.size != upload.size:
            raise ValueError("Stored original size changed")
    except Exception as error:
        raise HTTPException(503, "The stored original could not be checked; retry before submitting") from error
    revision = await session.scalar(select(ProjectRevision).where(ProjectRevision.project_id == project.id, ProjectRevision.version == project.version))
    if not revision:
        raise HTTPException(409, "Saved revision is unavailable")
    snapshot = await build_submission_snapshot(session, project, contributor, revision, upload)
    if not secrets.compare_digest(body.preview_hash, snapshot["preview_hash"]):
        raise HTTPException(409, "The submission packet changed after preview. Review the latest snapshot.")
    snapshot["submission_consent_recorded_at"] = now().isoformat()
    packet = SubmissionPacket(id="submission_" + uuid4().hex, project_id=project.id, revision_id=revision.id, contributor_id=contributor.id, upload_id=upload.id, packet=snapshot, status="pending_review", version=1)
    session.add(packet)
    await session.flush()
    await enqueue_submission_jobs(session, packet)
    await session.commit()
    return await packet_output(session, packet)


@router.get("/review/queue")
async def review_queue(account: AccountRecord = Depends(require_reviewer), session: AsyncSession = Depends(get_session)) -> dict:
    packets = (await session.scalars(select(SubmissionPacket).order_by(SubmissionPacket.id))).all()
    return {"items": [await packet_output(session, packet) for packet in packets]}


@router.post("/review/queue/ensure-jobs", dependencies=[Depends(mutation)])
async def ensure_review_jobs(account: AccountRecord = Depends(require_reviewer), session: AsyncSession = Depends(get_session)) -> dict:
    from .ai.jobs import enqueue_submission_jobs

    packets = (await session.scalars(select(SubmissionPacket).where(SubmissionPacket.status == "pending_review"))).all()
    queued_jobs = 0
    for packet in packets:
        jobs = await enqueue_submission_jobs(session, packet)
        queued_jobs += sum(1 for job in jobs if job.status == "queued")
    await session.commit()
    return {"pendingPackets": len(packets), "queuedJobs": queued_jobs}


class DecisionInput(BaseModel):
    action: Literal["approve", "request_changes", "reject", "escalate"]
    reason: str = Field(min_length=10, max_length=2000)
    expected_version: int = Field(ge=1)


@router.post("/review/{submission_id}/decision", dependencies=[Depends(mutation)])
async def decide(submission_id: str, body: DecisionInput, account: AccountRecord = Depends(require_reviewer), session: AsyncSession = Depends(get_session)) -> dict:
    packet = await session.get(SubmissionPacket, submission_id, with_for_update=True)
    if not packet:
        raise HTTPException(404, "Submission not found")
    if packet.version != body.expected_version or packet.status in {"approved", "rejected"}:
        raise HTTPException(409, "The review changed. Refresh the queue before deciding.")
    if len(body.reason.strip()) < 10:
        raise HTTPException(422, "A meaningful reason is required")
    from .ai.jobs import list_jobs_for_submission
    jobs = await list_jobs_for_submission(session, packet.id)
    policy = review_policy(reviewer_packet(packet.packet), jobs)
    if body.action == "approve" and not policy["may_approve"]:
        raise HTTPException(409, "Resolve blocking findings before approval")
    packet.status = {"approve": "approved", "request_changes": "changes_requested", "reject": "rejected", "escalate": "escalated"}[body.action]
    packet.version += 1
    session.add(DecisionRecord(id=uuid4().hex, submission_id=packet.id, action=body.action, reason=body.reason.strip(), created_at=now(), reviewer_id=account.id, assessment_version=policy["assessment_version"]))
    if body.action == "approve":
        from .publish import publish_approved_submission

        await publish_approved_submission(session, packet)
    await session.commit()
    return await packet_output(session, packet)


@router.api_route("/review/{submission_id}/media", methods=["GET", "HEAD"])
async def review_media(submission_id: str, request: Request, account: AccountRecord = Depends(require_reviewer), session: AsyncSession = Depends(get_session)) -> Response:
    packet = await session.get(SubmissionPacket, submission_id)
    upload = await session.get(UploadRecord, packet.upload_id) if packet and packet.upload_id else None
    if not upload or upload.purpose != "media" or upload.status != "verified":
        raise HTTPException(404, "Media not found")
    return await run_in_threadpool(media_response, upload.object_key, request.headers.get("range"), request.method == "HEAD")


@router.api_route("/review/{submission_id}/supporting-document", methods=["GET", "HEAD"])
async def review_supporting_document(submission_id: str, request: Request, account: AccountRecord = Depends(require_reviewer), session: AsyncSession = Depends(get_session)) -> Response:
    packet = await session.get(SubmissionPacket, submission_id)
    document = await session.get(UploadRecord, (packet.packet or {}).get("supporting_document", {}).get("uploadId")) if packet else None
    if not document or document.purpose != "supporting_document" or document.content_type != "application/pdf" or document.status != "verified":
        raise HTTPException(404, "Supporting document not found")
    return await run_in_threadpool(media_response, document.object_key, request.headers.get("range"), request.method == "HEAD")
