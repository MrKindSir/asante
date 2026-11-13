"""Opt-in browser fixture API. Uses disposable DB/storage, never the live workspace.

Run in a disposable Compose API container with port 8000 mapped to loopback.
Production startup never imports this test module or enables its providers.
"""
import asyncio
import os
from unittest.mock import patch

import uvicorn
from asante_api.main import app
from asante_api.ai.workers import fixture_plan
from asante_api.ai.activity import report_progress
from tests.integration.test_workspace_persistence import WorkspacePersistenceTests


async def fixture_research(brief):
    await report_progress("search", "Researcher → Deterministic fixture collector: retrieve synthetic test evidence. No live web research.", ["Fixture-only candidate collection"])
    await asyncio.sleep(2)
    if brief["researchBrief"]["uncertainties"] == "fixture-failure":
        raise RuntimeError("Deterministic browser fixture failure")
    return {"sources": [{"title": "Deterministic candidate archive", "url": "https://example.com/archive",
                         "excerpt": "Synthetic candidate evidence, for human interpretation.", "status": "retrieved"}],
            "summary": "Deterministic browser fixture: one candidate source.", "notes": ["Fixture evidence; no live research."], "aiUsed": False}


if __name__ == "__main__":
    if os.environ.get("ASANTE_BROWSER_FIXTURE") != "1":
        raise SystemExit("This disposable test API requires ASANTE_BROWSER_FIXTURE=1")
    WorkspacePersistenceTests.setUpClass()
    try:
        with patch("asante_api.workers_api.run_planner", side_effect=fixture_plan), patch(
            "asante_api.workers_api.run_researcher", side_effect=fixture_research,
        ):
            uvicorn.run(app, host="0.0.0.0", port=8000)
    finally:
        WorkspacePersistenceTests.doClassCleanups()
