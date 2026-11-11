"""Owner-scoped field-report documents, exports and token-based collaboration."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import secrets
from typing import Literal
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import mutation, optional_account, require_account, require_contributor
from .database import get_session
from .models import (
    AccountRecord,
    ContributorRecord,
    PlanCollaboratorRecord,
    PlanShareRecord,
    ProjectRecord,
    ProjectRevision,
    SubmissionPacket,
)
from .story_packet import plain, render_report_pdf
from .workspace import project_for

router = APIRouter(prefix="/v1")


def now() -> datetime:
    return datetime.now(timezone.utc)


class ReportSection(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=160)
    body: str = Field(default="", max_length=5000)
    bullets: list[str] = Field(default_factory=list, max_length=40)
    icon: str = Field(default="", max_length=12)


class ChartSeries(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    value: float = Field(ge=-1_000_000_000, le=1_000_000_000)


class ReportChart(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=160)
    unit: str = Field(default="", max_length=30)
    series: list[ChartSeries] = Field(default_factory=list, max_length=24)


class ReportTable(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=160)
    columns: list[str] = Field(default_factory=list, max_length=12)
    rows: list[list[str]] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_rows(self):
        if any(len(row) != len(self.columns) for row in self.rows):
            raise ValueError("Each field report table row must match its columns")
        return self


class ReportImage(BaseModel):
    url: HttpUrl
    caption: str = Field(default="", max_length=500)
    credit: str = Field(default="", max_length=300)
    sourceUrl: HttpUrl | None = None


class ReportSource(BaseModel):
    title: str = Field(default="", max_length=500)
    url: HttpUrl
    excerpt: str = Field(default="", max_length=8000)
    publisher: str = Field(default="", max_length=300)
    retrievedAt: str = Field(default="", max_length=64)
    status: str = Field(default="candidate", max_length=40)


class FieldReportDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=300)
    subtitle: str = Field(default="", max_length=300)
    landmark: str = Field(default="", max_length=200)
    summary: str = Field(default="", max_length=5000)
    sections: list[ReportSection] = Field(default_factory=list, max_length=30)
    charts: list[ReportChart] = Field(default_factory=list, max_length=10)
    tables: list[ReportTable] = Field(default_factory=list, max_length=10)
    images: list[ReportImage] = Field(default_factory=list, max_length=12)
    sources: list[ReportSource] = Field(default_factory=list, max_length=80)
    humanGate: str = Field(default="A human reviewer must approve publication.", max_length=500)

    @model_validator(mode="after")
    def validate_report(self):
        if len(json.dumps(self.model_dump(mode="json"), ensure_ascii=False)) > 160000:
            raise ValueError("Field report document is too large")
        if any(item.url.scheme != "https" or (item.sourceUrl and item.sourceUrl.scheme != "https") for item in self.images):
            raise ValueError("Related image references must use HTTPS")
        if any(source.url.scheme != "https" for source in self.sources):
            raise ValueError("Research references must use HTTPS")
        return self


class SaveReportInput(BaseModel):
    expectedVersion: int = Field(ge=1)
    document: FieldReportDocument


class CollaboratorInput(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    role: Literal["viewer", "editor"] = "viewer"


def build_field_report(content: dict, project_id: str) -> dict:
    plan = content.get("plan") or {}
    research = content.get("research") or {}
    report = research.get("report") or {}
    sections = []
    for key, title, icon in [
        ("outline", "Story outline", "◈"),
        ("questions", "Questions to explore", "?"),
        ("worker_steps", "Suggested next steps", "↗"),
        ("checklist", "Recording and review checklist", "✓"),
        ("unknowns", "What remains uncertain", "◇"),
    ]:
        values = plan.get(key) or []
        if values:
            sections.append({"id": key, "title": title, "body": "", "bullets": [str(value) for value in values], "icon": icon})
    research_bullets = [str(item.get("text") or "") for item in report.get("findings") or [] if item.get("text")]
    research_bullets.extend(str(note) for note in research.get("notes") or [])
    if research_bullets:
        sections.append({"id": "research-notes", "title": "Research notes", "body": "", "bullets": research_bullets[:40], "icon": "⌕"})
    questions = report.get("openQuestions") or []
    if questions:
        sections.append({"id": "human-questions", "title": "Questions for human review", "body": "", "bullets": [str(item) for item in questions[:40]], "icon": "◎"})
    def trusted_url(value: object) -> bool:
        parsed = urlparse(str(value or ""))
        return parsed.scheme == "https" and bool(parsed.netloc)

    images = [image for image in (research.get("images") or []) if isinstance(image, dict) and trusted_url(image.get("url"))]
    sources = [source for source in (research.get("sources") or []) if isinstance(source, dict) and trusted_url(source.get("url"))]
    return {
        "title": str(content.get("title") or "Untitled story"),
        "subtitle": str(plan.get("topic") or "Asante field report"),
        "landmark": str(content.get("place") or plan.get("place_name") or ""),
        "summary": str(report.get("summary") or research.get("summary") or content.get("claim") or "A working plan for a contributor-led story."),
        "sections": sections,
        "charts": [],
        "tables": [],
        "images": images,
        "sources": sources,
        "humanGate": str(plan.get("human_gate") or "A human reviewer must approve publication."),
    }


async def share_for_project(session: AsyncSession, project_id: str) -> PlanShareRecord | None:
    return await session.scalar(select(PlanShareRecord).where(PlanShareRecord.project_id == project_id))


async def project_role(session: AsyncSession, account: AccountRecord, project: ProjectRecord, share: PlanShareRecord | None) -> str | None:
    if account.contributor_id == project.contributor_id:
        return "owner"
    if not share:
        return None
    collaborator = await session.scalar(select(PlanCollaboratorRecord).where(
        PlanCollaboratorRecord.share_id == share.id,
        PlanCollaboratorRecord.account_id == account.id,
    ))
    return ("viewer" if collaborator.role == "reader" else "editor") if collaborator else None


async def require_project_editor(session: AsyncSession, account: AccountRecord, project: ProjectRecord, share: PlanShareRecord | None) -> str:
    role = await project_role(session, account, project, share)
    if role not in {"owner", "editor"}:
        raise HTTPException(403, "An editor role is required to change this plan")
    if await session.scalar(select(SubmissionPacket.id).where(SubmissionPacket.project_id == project.id)):
        raise HTTPException(409, "Submitted plans are frozen. Duplicate the story project to make changes.")
    return role


def report_response(document: dict, file_format: str) -> Response:
    filename = "asante-field-report"
    if file_format == "pdf":
        content = render_report_pdf(document)
        return Response(content, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{filename}.pdf"'})
    if file_format == "text":
        lines = ["ASANTE / FIELD REPORT", document.get("title", ""), document.get("subtitle", ""), document.get("landmark", ""), "", "EXECUTIVE SUMMARY", plain(document.get("summary"))]
        for section in document.get("sections") or []:
            lines.extend(["", str(section.get("title") or "").upper(), plain(section.get("body"))])
            lines.extend("• " + plain(item) for item in section.get("bullets") or [])
        for chart in document.get("charts") or []:
            lines.extend(["", str(chart.get("title") or "CHART")])
            lines.extend(f"{item.get('label')}: {item.get('value')} {chart.get('unit') or ''}".strip() for item in chart.get("series") or [])
        for table in document.get("tables") or []:
            lines.extend(["", str(table.get("title") or "TABLE"), " | ".join(table.get("columns") or [])])
            lines.extend(" | ".join(row) for row in table.get("rows") or [])
        for image in document.get("images") or []:
            lines.extend(["", f"Image: {image.get('caption') or ''}", f"Credit: {image.get('credit') or ''}", str(image.get("url") or "")])
        lines.extend(["", "REFERENCES / CANDIDATE SOURCES"])
        for index, source in enumerate(document.get("sources") or [], 1):
            lines.extend([f"[{index}] {source.get('title') or ''}", str(source.get("url") or ""), plain(source.get("excerpt"))])
        lines.extend(["", "HUMAN REVIEW GATE", str(document.get("humanGate") or "A human reviewer must approve publication.")])
        return Response("\n".join(line for line in lines if line is not None) + "\n", media_type="text/plain; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{filename}.txt"'})
    return Response(json.dumps(document, ensure_ascii=False, indent=2) + "\n", media_type="application/json", headers={"Content-Disposition": f'attachment; filename="{filename}.json"'})


@router.get("/workspace/projects/{project_id}/plan-document")
async def get_plan_document(project_id: str, account: AccountRecord = Depends(require_account), session: AsyncSession = Depends(get_session)) -> dict:
    if account.role != "contributor":
        raise HTTPException(403, "An Asante contributor account is required")
    project = await project_for(session, project_id, account.contributor_id)
    document = project.content.get("planDocument") or build_field_report(project.content, project.id)
    return {"document": document, "version": project.version}


@router.put("/workspace/projects/{project_id}/plan-document", dependencies=[Depends(mutation)])
async def save_plan_document(project_id: str, body: SaveReportInput, account: AccountRecord = Depends(require_account), session: AsyncSession = Depends(get_session)) -> dict:
    project = await session.get(ProjectRecord, project_id, with_for_update=True)
    if not project:
        raise HTTPException(404, "Project not found")
    share = await share_for_project(session, project.id)
    role = await require_project_editor(session, account, project, share)
    if project.version != body.expectedVersion:
        raise HTTPException(409, "The project changed before this report could be saved. Reload the current story plan.")
    content = dict(project.content)
    content["planDocument"] = body.document.model_dump(mode="json")
    project.version += 1
    project.content = content
    if share:
        share.document = content["planDocument"]
        share.title = body.document.title
        share.updated_at = now()
    session.add(ProjectRevision(id=uuid4().hex, project_id=project.id, version=project.version, content=content))
    await session.commit()
    return {"document": content["planDocument"], "version": project.version, "role": role}


@router.get("/workspace/projects/{project_id}/plan-document/export")
async def export_project_plan(project_id: str, format: Literal["pdf", "text", "json"] = Query("pdf"), account: AccountRecord = Depends(require_account), session: AsyncSession = Depends(get_session)) -> Response:
    project = await session.get(ProjectRecord, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    share = await share_for_project(session, project_id)
    if not await project_role(session, account, project, share):
        raise HTTPException(403, "You do not have access to this plan")
    document = project.content.get("planDocument") or build_field_report(project.content, project.id)
    return report_response(document, format)


@router.post("/workspace/projects/{project_id}/plan-share", dependencies=[Depends(mutation)])
async def create_plan_share(project_id: str, account: AccountRecord = Depends(require_contributor), session: AsyncSession = Depends(get_session)) -> dict:
    project = await project_for(session, project_id, account.contributor_id)
    if not project.content.get("plan"):
        raise HTTPException(409, "Prepare a story plan before sharing its field report")
    document = project.content.get("planDocument") or build_field_report(project.content, project.id)
    share = await share_for_project(session, project.id)
    if not share:
        share = PlanShareRecord(id=uuid4().hex, project_id=project.id, owner_id=account.contributor_id, token=secrets.token_urlsafe(32), title=document.get("title", "Field report"), document=document, created_at=now(), updated_at=now())
        session.add(share)
    else:
        share.title = document.get("title", "Field report")
        share.document = document
        share.updated_at = now()
    await session.commit()
    return {"token": share.token, "title": share.title, "document": share.document}


@router.get("/workspace/projects/{project_id}/plan-share")
async def get_plan_share(project_id: str, account: AccountRecord = Depends(require_contributor), session: AsyncSession = Depends(get_session)) -> dict:
    await project_for(session, project_id, account.contributor_id)
    share = await share_for_project(session, project_id)
    if not share:
        return {"share": None, "collaborators": []}
    collaborators = (await session.scalars(select(PlanCollaboratorRecord, AccountRecord).join(AccountRecord, AccountRecord.id == PlanCollaboratorRecord.account_id).where(PlanCollaboratorRecord.share_id == share.id))).all()
    return {"share": {"token": share.token, "title": share.title}, "collaborators": [{"email": account.email, "role": "viewer" if member.role == "reader" else "editor"} for member, account in collaborators]}


@router.post("/workspace/projects/{project_id}/plan-share/collaborators", dependencies=[Depends(mutation)])
async def invite_plan_collaborator(project_id: str, body: CollaboratorInput, account: AccountRecord = Depends(require_contributor), session: AsyncSession = Depends(get_session)) -> dict:
    await project_for(session, project_id, account.contributor_id)
    share = await share_for_project(session, project_id)
    if not share:
        raise HTTPException(404, "Create a share link before inviting collaborators")
    invite_email = body.email.strip().lower()
    invited = await session.scalar(select(AccountRecord).where(AccountRecord.email == invite_email))
    if not invited or invited.role != "contributor":
        raise HTTPException(404, "Invites are available for existing Asante contributor accounts")
    if invited.id == account.id:
        raise HTTPException(422, "You already own this field report")
    member = await session.scalar(select(PlanCollaboratorRecord).where(PlanCollaboratorRecord.share_id == share.id, PlanCollaboratorRecord.account_id == invited.id))
    role = "reader" if body.role == "viewer" else "editor"
    if member:
        member.role = role
    else:
        member = PlanCollaboratorRecord(id=uuid4().hex, share_id=share.id, account_id=invited.id, role=role, invited_by=account.id, created_at=now())
        session.add(member)
    await session.commit()
    return {"email": invited.email, "role": body.role}


@router.delete("/workspace/projects/{project_id}/plan-share/collaborators/{email}", dependencies=[Depends(mutation)])
async def remove_plan_collaborator(project_id: str, email: str, account: AccountRecord = Depends(require_contributor), session: AsyncSession = Depends(get_session)) -> dict:
    await project_for(session, project_id, account.contributor_id)
    share = await share_for_project(session, project_id)
    target = await session.scalar(select(AccountRecord).where(AccountRecord.email == email.lower()))
    if not share or not target:
        raise HTTPException(404, "Collaborator not found")
    member = await session.scalar(select(PlanCollaboratorRecord).where(PlanCollaboratorRecord.share_id == share.id, PlanCollaboratorRecord.account_id == target.id))
    if not member:
        raise HTTPException(404, "Collaborator not found")
    await session.delete(member)
    await session.commit()
    return {"removed": True}


@router.delete("/workspace/projects/{project_id}/plan-share", dependencies=[Depends(mutation)])
async def revoke_plan_share(project_id: str, account: AccountRecord = Depends(require_contributor), session: AsyncSession = Depends(get_session)) -> dict:
    await project_for(session, project_id, account.contributor_id)
    share = await share_for_project(session, project_id)
    if not share:
        return {"revoked": True}
    await session.delete(share)
    await session.commit()
    return {"revoked": True}


@router.get("/plans/share/{token}")
async def read_shared_plan(token: str, request: Request, session: AsyncSession = Depends(get_session)) -> dict:
    share = await session.scalar(select(PlanShareRecord).where(PlanShareRecord.token == token))
    if not share:
        raise HTTPException(404, "Shared field report not found")
    project = await session.get(ProjectRecord, share.project_id)
    if not project:
        raise HTTPException(404, "Shared field report not found")
    account = await optional_account(request, session)
    role = await project_role(session, account, project, share) if account else None
    return {"title": share.title, "document": share.document, "role": role or "viewer", "canEdit": role in {"owner", "editor"} and not bool(await session.scalar(select(SubmissionPacket.id).where(SubmissionPacket.project_id == project.id))), "version": project.version}


@router.put("/plans/share/{token}", dependencies=[Depends(mutation)])
async def save_shared_plan(token: str, body: SaveReportInput, account: AccountRecord = Depends(require_account), session: AsyncSession = Depends(get_session)) -> dict:
    share = await session.scalar(select(PlanShareRecord).where(PlanShareRecord.token == token))
    if not share:
        raise HTTPException(404, "Shared field report not found")
    project = await session.get(ProjectRecord, share.project_id, with_for_update=True)
    await require_project_editor(session, account, project, share)
    if project.version != body.expectedVersion:
        raise HTTPException(409, "The field report changed before your edit could be saved")
    content = dict(project.content)
    content["planDocument"] = body.document.model_dump(mode="json")
    project.content = content
    project.version += 1
    share.document = content["planDocument"]
    share.title = body.document.title
    share.updated_at = now()
    session.add(ProjectRevision(id=uuid4().hex, project_id=project.id, version=project.version, content=content))
    await session.commit()
    return {"document": share.document, "version": project.version}


@router.get("/plans/share/{token}/export")
async def export_shared_plan(token: str, format: Literal["pdf", "text", "json"] = Query("pdf"), session: AsyncSession = Depends(get_session)) -> Response:
    share = await session.scalar(select(PlanShareRecord).where(PlanShareRecord.token == token))
    if not share:
        raise HTTPException(404, "Shared field report not found")
    return report_response(share.document, format)
