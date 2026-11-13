"""Owner endpoints for Asante planner/researcher worker runs."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified
from starlette.concurrency import run_in_threadpool

from .ai.provider import provider_config
from .ai.activity import progress_sink
from .ai.workers import new_run_id, new_trace_id, run_planner, run_researcher
from .auth import mutation, require_contributor, require_reviewer
from .database import get_session, session_factory
from .models import AccountRecord, ProjectRecord, ProjectRevision, SubmissionPacket, WorkerRunRecord
from .research_brief import brief_complete, document_hash, research_input_hash

router = APIRouter(prefix="/v1")


def now() -> datetime:
    return datetime.now(timezone.utc)


class WorkerStart(BaseModel):
    workerType: Literal["planner", "researcher"]
    expectedVersion: int = Field(ge=1)


def public_run(record: WorkerRunRecord) -> dict:
    return {
        "runId": record.id,
        "traceId": record.trace_id,
        "projectId": record.project_id,
        "workerType": record.worker_type,
        "status": record.status,
        "result": record.result_payload,
        "safeError": record.safe_error or None,
        "providerModel": record.provider_model or None,
        "createdAt": record.created_at.isoformat(),
        "finishedAt": record.finished_at.isoformat() if record.finished_at else None,
        "activity": (record.result_payload or {}).get("activity", []),
        "input": {key: record.input_payload.get(key) for key in (
            "title", "place", "claim", "source", "researchBrief", "planQuestions", "projectVersion", "researchInputHash",
        )},
    }


@router.post("/workspace/projects/{project_id}/workers", dependencies=[Depends(mutation)])
async def start_worker(
    project_id: str,
    body: WorkerStart,
    account: AccountRecord = Depends(require_contributor),
    session: AsyncSession = Depends(get_session),
) -> dict:
    project = await session.scalar(select(ProjectRecord).where(ProjectRecord.id == project_id).with_for_update().execution_options(populate_existing=True))
    if project is None or project.contributor_id != account.contributor_id:
        raise HTTPException(404, "Story project not found")
    if await session.scalar(select(SubmissionPacket.id).where(SubmissionPacket.project_id == project.id)):
        raise HTTPException(409, "Submitted revisions are frozen. Duplicate this project to run another worker.")
    if project.version != body.expectedVersion:
        raise HTTPException(409, "This project changed. Reload before running a worker.")

    content = dict(project.content or {})
    if content.get("researchBrief") is not None and not brief_complete(content):
        raise HTTPException(422, "Complete and save the research brief first.")
    input_hash = research_input_hash(content)
    running = await session.scalar(select(WorkerRunRecord.id).where(
        WorkerRunRecord.project_id == project.id, WorkerRunRecord.status == "running",
    ))
    if running:
        raise HTTPException(409, "An Asante worker is already running for this story. Wait for its result.")
    brief = {
        "topic": content.get("title") or "",
        "title": content.get("title") or "",
        "place_name": content.get("place") or "",
        "place": content.get("place") or "",
        "language": content.get("language") or "en",
        "media_format": content.get("format") or "audio",
        "format": content.get("format") or "audio",
        "audience": content.get("audience") or "Community listeners",
        "claim": content.get("claim") or "",
        "source": content.get("source") or "",
        "transcript": (content.get("transcript") or "")[:2000],
        "researchBrief": content.get("researchBrief"),
        "researchInputHash": input_hash,
        "projectVersion": project.version,
        "planQuestions": (content.get("plan") or {}).get("questions", []) if body.workerType == "researcher" and ((content.get("plan") or {}).get("researchInputHash") == input_hash or not content.get("researchBrief")) else [],
    }
    if body.workerType == "planner" and len((brief["topic"] or "").strip()) < 3:
        raise HTTPException(422, "Add a story title before running the planner.")

    run = WorkerRunRecord(
        id=new_run_id(),
        trace_id=new_trace_id(),
        project_id=project.id,
        contributor_id=account.contributor_id,
        worker_type=body.workerType,
        status="running",
        input_payload=brief,
        result_payload={},
        safe_error="",
        provider_model=provider_config().get("model") or "",
        created_at=now(),
        finished_at=None,
    )
    session.add(run)
    content["researchFlow"] = {"status": "running", "workerType": body.workerType, "inputHash": input_hash, "runId": run.id}
    project.content = content
    await session.commit()

    events: list[dict] = []
    async def record_progress(kind: str, message: str, details: list[str]) -> None:
        if len(events) >= 80:
            return
        events.append({"id": f"{run.id}:{len(events)}", "at": now().isoformat(),
                       "actor": "Asante planner" if body.workerType == "planner" else "Asante researcher",
                       "kind": kind, "message": message[:800], "details": [str(item)[:2000] for item in details[:12]]})
        async with session_factory()() as progress_session:
            progress_run = await progress_session.get(WorkerRunRecord, run.id)
            if progress_run and progress_run.status == "running":
                progress_run.result_payload = {"activity": list(events)}
                await progress_session.commit()

    token = progress_sink.set(record_progress)
    try:
        await record_progress("delegation", f"Asante coordinator → {body.workerType}: work assigned from saved revision {body.expectedVersion}.", [])
        if body.workerType == "researcher" and brief["planQuestions"]:
            await record_progress("handoff", "Planner → Researcher: use these planning questions alongside the contributor's research brief.", brief["planQuestions"])
        await record_progress("working", "Preparing story questions and an outline." if body.workerType == "planner" else "Preparing a bounded evidence search from the saved brief.", [])
        if body.workerType == "planner":
            result = await run_in_threadpool(run_planner, brief)
        else:
            result = await run_researcher(brief)
        project = await session.scalar(select(ProjectRecord).where(ProjectRecord.id == project_id).with_for_update().execution_options(populate_existing=True))
        if project is None or project.version != body.expectedVersion or await session.scalar(select(SubmissionPacket.id).where(SubmissionPacket.project_id == project_id)):
            await record_progress("cancelled", "Results were not attached because the saved revision changed or was submitted.", [])
            run.result_payload = {**result, "activity": list(events)}
            run.status = "cancelled"
            run.safe_error = "Worker result was not attached because the project revision changed or was submitted while the worker ran."
            run.finished_at = now()
            if project and research_input_hash(project.content) == input_hash:
                project.content = {**project.content, "researchFlow": {"status": "failed", "inputHash": input_hash, "safeError": run.safe_error}}
            await session.commit()
            await session.refresh(run)
            return {**public_run(run), "projectVersion": project.version if project else None, "plan": None, "research": None, "suggestion": None}
        content = dict(project.content or {})
        if body.workerType == "planner":
            content["plan"] = {
                "project_id": project.id,
                "run_id": run.id,
                "trace_id": run.trace_id,
                "worker_steps": result.get("worker_steps") or [],
                "questions": result.get("questions") or [],
                "outline": result.get("outline") or [],
                "checklist": result.get("checklist") or [],
                "unknowns": result.get("unknowns") or [],
                "human_gate": result.get("human_gate") or "",
                "aiUsed": bool(result.get("aiUsed")),
                "researchInputHash": input_hash,
            }
            content["suggestion"] = "pending"
        else:
            if not result.get("sources"):
                raise ValueError("No candidate evidence was returned")
            content["research"] = {**result, "runId": run.id, "traceId": run.trace_id, "researchInputHash": input_hash}
        complete = bool(
            (content.get("plan") or {}).get("researchInputHash") == input_hash
            and (content.get("research") or {}).get("researchInputHash") == input_hash
            and (content.get("research") or {}).get("sources")
        )
        document = content.get("planDocument")
        if complete and (not document or document_hash(document) == content.get("generatedReportHash")):
            from .plan_documents import build_field_report
            content["planDocument"] = build_field_report(content, project.id)
            content["generatedReportHash"] = document_hash(content["planDocument"])
        content["researchFlow"] = {
            "status": "completed" if complete else "planned", "workerType": body.workerType,
            "inputHash": input_hash, "runId": run.id,
        }
        project.content = content
        flag_modified(project, "content")
        project.version = int(project.version) + 1
        session.add(ProjectRevision(id=uuid4().hex, project_id=project.id, version=project.version, content=content))
        await record_progress("completed", "Story plan saved; research can use the planning questions." if body.workerType == "planner" else f"Saved {len(result.get('sources') or [])} candidate sources for human interpretation.", result.get("questions") or result.get("notes") or [])
        if body.workerType == "planner":
            await record_progress("handoff", "Planner → Researcher: planning output is ready for the next research step.", result.get("questions") or [])
        run.result_payload = {**result, "activity": list(events)}
        run.status = "succeeded"
        run.provider_model = str(result.get("providerModel") or run.provider_model or "")
        run.finished_at = now()
    except Exception as error:
        await record_progress("failed", f"Worker failed: {error.__class__.__name__}. Saved answers are preserved; retry requires an explicit action.", [])
        run.result_payload = {"activity": list(events)}
        project = await session.scalar(select(ProjectRecord).where(ProjectRecord.id == project_id).with_for_update().execution_options(populate_existing=True))
        run.status = "failed"
        run.safe_error = f"Worker failed: {error.__class__.__name__}"
        run.finished_at = now()
        if project and project.version == body.expectedVersion:
            content = dict(project.content or {})
            content["researchFlow"] = {"status": "failed", "workerType": body.workerType, "inputHash": input_hash, "runId": run.id, "safeError": run.safe_error}
            project.content = content
        await session.commit()
        raise HTTPException(502, run.safe_error) from error
    finally:
        progress_sink.reset(token)

    await session.commit()
    await session.refresh(run)
    await session.refresh(project)
    return {
        **public_run(run),
        "projectVersion": project.version,
        "plan": content.get("plan"),
        "research": content.get("research"),
        "suggestion": content.get("suggestion"),
        "planDocument": content.get("planDocument"),
        "researchFlow": content.get("researchFlow"),
    }


@router.get("/workspace/projects/{project_id}/workers")
async def list_project_workers(
    project_id: str,
    account: AccountRecord = Depends(require_contributor),
    session: AsyncSession = Depends(get_session),
) -> dict:
    project = await session.get(ProjectRecord, project_id)
    if project is None or project.contributor_id != account.contributor_id:
        raise HTTPException(404, "Story project not found")
    rows = (
        await session.scalars(
            select(WorkerRunRecord)
            .where(WorkerRunRecord.project_id == project_id)
            .order_by(WorkerRunRecord.created_at.desc())
            .limit(50)
        )
    ).all()
    return {"items": [public_run(row) for row in rows]}


@router.get("/review/worker-runs")
async def review_worker_runs(
    account: AccountRecord = Depends(require_reviewer),
    session: AsyncSession = Depends(get_session),
) -> dict:
    del account
    rows = (await session.scalars(
        select(WorkerRunRecord)
        .where(WorkerRunRecord.worker_type.not_in(("planner", "researcher")))
        .order_by(WorkerRunRecord.created_at.desc())
        .limit(100)
    )).all()
    return {"items": [public_run(row) for row in rows]}
