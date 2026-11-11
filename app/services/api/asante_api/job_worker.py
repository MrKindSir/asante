"""Asante background worker: claim and run processing jobs until interrupted."""
from __future__ import annotations

import asyncio
import logging
import os
import signal
from uuid import uuid4

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from .ai.jobs import claim_next_job, process_job
from .database import database_url
from .models import ProcessingJobRecord

logger = logging.getLogger("asante.job_worker")
STOP = False


def _handle_stop(*_args: object) -> None:
    global STOP
    STOP = True


async def run_worker_loop() -> None:
    worker_id = (os.environ.get("ASANTE_JOB_WORKER_ID") or ("worker_" + uuid4().hex[:12])).strip()
    idle_seconds = float(os.environ.get("ASANTE_JOB_IDLE_SECONDS") or "2")
    engine = create_async_engine(database_url(), pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    logger.info("Asante job worker started as %s", worker_id)
    try:
        while not STOP:
            try:
                claimed_job_id: str | None = None
                async with factory() as session:
                    async with session.begin():
                        job = await claim_next_job(session, worker_id)
                        if job:
                            claimed_job_id = job.id
                if claimed_job_id:
                    async with factory() as session:
                        async with session.begin():
                            job = await session.get(ProcessingJobRecord, claimed_job_id, with_for_update=True)
                            if job and job.status == "running" and job.lease_owner == worker_id:
                                await process_job(session, job)
                                logger.info(
                                    "job %s type=%s status=%s progress=%s",
                                    job.id,
                                    job.job_type,
                                    job.status,
                                    job.progress,
                                )
                    continue
            except Exception:
                logger.exception("job worker loop error; backing off")
                await asyncio.sleep(max(idle_seconds, 5))
                continue
            await asyncio.sleep(idle_seconds)
    finally:
        await engine.dispose()
        logger.info("Asante job worker stopped")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)
    asyncio.run(run_worker_loop())


if __name__ == "__main__":
    main()
