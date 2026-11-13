#!/usr/bin/env python3
"""Enqueue capped draft media jobs for projects that already have verified uploads.

Run inside the API container with PYTHONPATH including asante_api, for example:
  python /workspace/scripts/asante/backfill_draft_media_jobs.py
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select

from asante_api.database import session_factory
from asante_api.models import ProcessingJobRecord, ProjectRecord, UploadRecord
from asante_api.ai.jobs import enqueue_project_media_jobs


async def main() -> int:
    created_total = 0
    async with session_factory()() as session:
        projects = (await session.scalars(select(ProjectRecord).order_by(ProjectRecord.id))).all()
        for project in projects:
            upload_id = (project.content or {}).get("uploadId")
            if not upload_id:
                continue
            existing = (
                await session.scalars(
                    select(ProcessingJobRecord.id).where(ProcessingJobRecord.project_id == project.id)
                )
            ).all()
            if existing:
                continue
            upload = await session.get(UploadRecord, upload_id)
            if not upload or upload.status != "verified" or upload.purpose != "media":
                continue
            jobs = await enqueue_project_media_jobs(session, project=project, upload=upload)
            created_total += len(jobs)
            print(f"{project.id}\t{(project.content or {}).get('title')}\t{[job.job_type for job in jobs]}")
        await session.commit()
    print(f"created_jobs={created_total}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
