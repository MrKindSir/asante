"""Realtime project collaboration chat for owners and invited members."""
from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import ACCOUNT_COOKIE, mutation, require_account, token_hash
from .database import get_session, session_factory
from .models import (
    AccountRecord,
    AccountSession,
    ContributorRecord,
    PlanCollaboratorRecord,
    PlanShareRecord,
    ProjectMessageRecord,
    ProjectRecord,
)

router = APIRouter(prefix="/v1")

_rooms: dict[str, set[WebSocket]] = defaultdict(set)
_lock = asyncio.Lock()


def now() -> datetime:
    return datetime.now(timezone.utc)


class MessageInput(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


def public_message(row: ProjectMessageRecord) -> dict[str, Any]:
    return {
        "id": row.id,
        "projectId": row.project_id,
        "accountId": row.account_id,
        "authorName": row.author_name,
        "body": row.body,
        "createdAt": row.created_at.isoformat(),
    }


async def project_access(
    session: AsyncSession,
    account: AccountRecord,
    project_id: str,
) -> tuple[ProjectRecord, str]:
    project = await session.get(ProjectRecord, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    if project.contributor_id == account.contributor_id:
        return project, "owner"
    share = await session.scalar(select(PlanShareRecord).where(PlanShareRecord.project_id == project_id))
    if not share:
        raise HTTPException(403, "You do not have access to this project chat")
    member = await session.scalar(
        select(PlanCollaboratorRecord).where(
            PlanCollaboratorRecord.share_id == share.id,
            PlanCollaboratorRecord.account_id == account.id,
        )
    )
    if not member:
        raise HTTPException(403, "You do not have access to this project chat")
    return project, member.role


async def _broadcast(project_id: str, payload: dict[str, Any]) -> None:
    async with _lock:
        sockets = list(_rooms.get(project_id) or [])
    dead: list[WebSocket] = []
    for socket in sockets:
        try:
            await socket.send_json(payload)
        except Exception:
            dead.append(socket)
    if dead:
        async with _lock:
            for socket in dead:
                _rooms[project_id].discard(socket)


async def _account_from_cookie(token: str | None, session: AsyncSession) -> AccountRecord | None:
    if not token:
        return None
    record = await session.get(AccountSession, token_hash(token))
    if not record or record.expires_at <= now():
        return None
    return await session.get(AccountRecord, record.account_id)


@router.get("/workspace/projects/{project_id}/messages")
async def list_messages(
    project_id: str,
    account: AccountRecord = Depends(require_account),
    session: AsyncSession = Depends(get_session),
) -> dict:
    await project_access(session, account, project_id)
    rows = (
        await session.scalars(
            select(ProjectMessageRecord)
            .where(ProjectMessageRecord.project_id == project_id)
            .order_by(ProjectMessageRecord.created_at.asc())
            .limit(200)
        )
    ).all()
    return {"messages": [public_message(row) for row in rows]}


@router.post("/workspace/projects/{project_id}/messages", dependencies=[Depends(mutation)])
async def post_message(
    project_id: str,
    body: MessageInput,
    account: AccountRecord = Depends(require_account),
    session: AsyncSession = Depends(get_session),
) -> dict:
    await project_access(session, account, project_id)
    contributor = await session.get(ContributorRecord, account.contributor_id) if account.contributor_id else None
    author = ""
    if contributor and isinstance(contributor.profile, dict):
        author = str(contributor.profile.get("name") or "").strip()
    if not author:
        author = account.email.split("@")[0]
    text = body.body.strip()
    if not text:
        raise HTTPException(422, "Message cannot be empty")
    row = ProjectMessageRecord(
        id=uuid4().hex,
        project_id=project_id,
        account_id=account.id,
        author_name=author[:120],
        body=text[:4000],
        created_at=now(),
    )
    session.add(row)
    await session.commit()
    payload = {"type": "message", "message": public_message(row)}
    await _broadcast(project_id, payload)
    return payload["message"]


@router.websocket("/workspace/projects/{project_id}/collab/ws")
async def collab_ws(websocket: WebSocket, project_id: str) -> None:
    async with session_factory()() as session:
        account = await _account_from_cookie(websocket.cookies.get(ACCOUNT_COOKIE), session)
        if not account:
            await websocket.close(code=4401)
            return
        try:
            await project_access(session, account, project_id)
        except HTTPException:
            await websocket.close(code=4403)
            return
    await websocket.accept()
    async with _lock:
        _rooms[project_id].add(websocket)
    try:
        await websocket.send_json({"type": "ready", "projectId": project_id})
        while True:
            data = await websocket.receive_json()
            # Clients should POST to create durable messages; ignore chat payloads here.
            if isinstance(data, dict) and data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        async with _lock:
            _rooms[project_id].discard(websocket)
