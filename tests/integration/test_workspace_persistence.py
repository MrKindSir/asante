"""Real PostGIS/MinIO workspace, upload, review and restart checks."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4
from io import BytesIO
from zipfile import ZipFile

import psycopg
from sqlalchemy import select
from fastapi.testclient import TestClient
from asante_api.main import app
from asante_api.storage import storage_client
from asante_api.database import dispose_database_engine, session_factory
from asante_api.models import ProcessingJobRecord
from asante_api.ai.jobs import claim_next_job, process_job
from app.db.seed_accounts import seed_accounts, TEST_ACCOUNTS


class WorkspacePersistenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Earlier route tests may initialize a lazy engine before this database is selected.
        asyncio.run(dispose_database_engine())
        cls.database = "asante_test_" + uuid4().hex[:20]
        cls.bucket = "asante-test-" + uuid4().hex
        cls.db_args = dict(host=os.environ.get("ASANTE_POSTGRES_HOST", "postgres"), user=os.environ["ASANTE_POSTGRES_USER"], password=os.environ["ASANTE_POSTGRES_PASSWORD"], port=int(os.environ.get("ASANTE_POSTGRES_INTERNAL_PORT", "5432")))
        cls.admin = psycopg.connect(**cls.db_args, dbname="postgres", autocommit=True)
        cls.admin.execute(f'CREATE DATABASE "{cls.database}"')
        cls.addClassCleanup(cls.cleanup_database)
        cls.env = patch.dict(os.environ, {"ASANTE_POSTGRES_DB": cls.database, "ASANTE_MINIO_BUCKET": cls.bucket, "ASANTE_ENV": "development", "ASANTE_REVIEWER_KEY": "integration-reviewer-key"})
        cls.env.start()
        cls.addClassCleanup(cls.env.stop)
        cls.addClassCleanup(lambda: asyncio.run(dispose_database_engine()))
        # Integration fixtures must never send mail using the developer's SMTP settings.
        cls.smtp = patch("asante_api.notify._smtp_settings", return_value=None)
        cls.smtp.start()
        cls.addClassCleanup(cls.smtp.stop)
        subprocess.run([sys.executable, "-m", "alembic", "-c", "app/db/alembic.ini", "upgrade", "head"], check=True, capture_output=True)
        cls.storage = storage_client()
        cls.storage.make_bucket(cls.bucket)
        cls.addClassCleanup(cls.cleanup_bucket)
        cls.passwords = {item[0]: "Asante-integration-" + item[0] + "-password" for item in TEST_ACCOUNTS}
        asyncio.run(seed_accounts(cls.passwords))

    @classmethod
    def cleanup_database(cls):
        cls.admin.execute(f'DROP DATABASE IF EXISTS "{cls.database}" WITH (FORCE)')
        cls.admin.close()

    @classmethod
    def cleanup_bucket(cls):
        for item in cls.storage.list_objects(cls.bucket, recursive=True):
            cls.storage.remove_object(cls.bucket, item.object_name)
        cls.storage.remove_bucket(cls.bucket)

    def register_contributor(self, client, name, email):
        response = client.post("/asante/api/v1/auth/register", headers={"X-Asante-Request": "1"}, json={"name": name, "email": email, "password": "Asante integration contributor password", "consent": True, "import_device": True})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def switch_cookie(self, client, token):
        client.cookies.clear()
        client.cookies.set("asante_account", token, path="/asante/api")

    def test_researcher_worker_persists_sources_and_owner_isolation(self):
        headers = {"X-Asante-Request": "1", "Origin": "http://testserver"}
        prefix = "/asante/api/v1"
        source = {
            "title": "Community record",
            "url": "https://example.com/history",
            "excerpt": "Candidate evidence for comparison",
            "collector": "web search",
            "status": "retrieved",
        }

        async def fake_collect(query, extra_urls=None):
            del query, extra_urls
            return [source], ["Collected 1 usable sources across web, news and social collectors."]

        with TestClient(app, root_path="/asante/api") as client, patch.dict(os.environ, {"ASANTE_AI_PROVIDER": "fake"}), patch(
            "asante_api.ai.workers.collect_evidence", new=AsyncMock(side_effect=fake_collect)
        ):
            client.post(prefix + "/workspace/session", headers=headers, json={})
            self.register_contributor(client, "Research contributor", "research-" + uuid4().hex + "@example.test")
            project = client.post(
                prefix + "/workspace/projects",
                headers=headers,
                json={"id": str(uuid4()), "title": "Soweto community memories", "claim": "When did gatherings begin?", "place": "Soweto Towers"},
            ).json()
            path = prefix + "/workspace/projects/" + project["id"] + "/workers"
            first = client.post(path, headers=headers, json={"workerType": "researcher", "expectedVersion": project["version"]})
            self.assertEqual(first.status_code, 200, first.text)
            result = first.json()
            self.assertEqual(result["status"], "succeeded")
            self.assertTrue(result["research"]["sources"])
            self.assertEqual(result["research"]["sources"][0]["url"], source["url"])
            history = client.get(path).json()["items"]
            self.assertEqual(len(history), 1)
            restored = client.get(prefix + "/workspace").json()["projects"][0]
            self.assertEqual(restored["research"]["sources"][0]["url"], source["url"])
            retry = client.post(path, headers=headers, json={"workerType": "researcher", "expectedVersion": result["projectVersion"]})
            self.assertEqual(retry.status_code, 200, retry.text)
            self.assertNotEqual(retry.json()["runId"], result["runId"])
            self.assertEqual(len(client.get(path).json()["items"]), 2)
            token = client.cookies.get("asante_account")
            client.cookies.clear()
            client.post(prefix + "/workspace/session", headers=headers, json={})
            self.register_contributor(client, "Other researcher", "research-other-" + uuid4().hex + "@example.test")
            self.assertEqual(client.get(path).status_code, 404)
        with TestClient(app, root_path="/asante/api") as restarted:
            restarted.cookies.set("asante_account", token, path="/asante/api")
            response = restarted.get(path)
            self.assertEqual(response.status_code, 200, response.text)
            persisted = response.json()["items"]
            self.assertEqual(len(persisted), 2)
            self.assertEqual([run["status"] for run in persisted], ["succeeded", "succeeded"])

    def test_running_worker_deduplicates_and_does_not_attach_to_a_new_revision(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Event
        from asante_api.ai.workers import fixture_plan
        prefix = "/asante/api/v1"
        headers = {"X-Asante-Request": "1"}
        started, release = Event(), Event()
        def blocked_planner(brief):
            started.set()
            if not release.wait(10):
                raise RuntimeError("Fixture was not released")
            return fixture_plan(brief)
        with TestClient(app, root_path="/asante/api") as client, patch("asante_api.workers_api.run_planner", side_effect=blocked_planner) as planner:
            client.post(prefix + "/workspace/session", headers=headers, json={})
            self.register_contributor(client, "Concurrent brief", "concurrent-" + uuid4().hex + "@example.test")
            project = client.post(prefix + "/workspace/projects", headers=headers, json={"id": uuid4().hex, "title": "Oral history", "claim": "When?", "researchBrief": {"questions": "Who attended?"}}).json()
            path = prefix + "/workspace/projects/" + project["id"] + "/workers"
            with ThreadPoolExecutor() as executor:
                pending = executor.submit(client.post, path, headers=headers, json={"workerType": "planner", "expectedVersion": project["version"]})
                try:
                    self.assertTrue(started.wait(5))
                    restored = next(item for item in client.get(prefix + "/workspace").json()["projects"] if item["id"] == project["id"])
                    self.assertEqual(restored["researchFlow"]["status"], "running")
                    live_history = client.get(path).json()["items"]
                    self.assertTrue(live_history[0]["activity"])
                    self.assertEqual(live_history[0]["activity"][0]["kind"], "delegation")
                    duplicate = client.post(path, headers=headers, json={"workerType": "planner", "expectedVersion": project["version"]})
                    self.assertEqual(duplicate.status_code, 409)
                    changed = client.post(prefix + "/workspace/projects", headers=headers, json={**project, "claim": "A changed story question"})
                    self.assertEqual(changed.status_code, 200)
                finally:
                    release.set()
                result = pending.result(timeout=10)
            self.assertEqual(result.json()["status"], "cancelled")
            self.assertEqual(planner.call_count, 1)
            restored = next(item for item in client.get(prefix + "/workspace").json()["projects"] if item["id"] == project["id"])
            self.assertEqual(restored["claim"], "A changed story question")
            self.assertFalse(restored.get("plan"))
            self.assertEqual(restored["researchFlow"]["status"], "saved")

    def test_saved_research_brief_versions_failure_retry_and_report(self):
        from asante_api.models import WorkerRunRecord
        from asante_api.ai.workers import fixture_plan
        prefix = "/asante/api/v1"
        headers = {"X-Asante-Request": "1"}
        answers = {"knownMaterial": "My grandmother's oral history", "questions": "When did gatherings begin?",
                   "context": "Soweto, 1976, family names", "priorities": "Compare dates", "uncertainties": "The exact year"}
        source = {"title": "Fixture archive", "url": "https://example.com/archive", "excerpt": "Candidate evidence", "status": "retrieved"}
        with TestClient(app, root_path="/asante/api") as client, patch("asante_api.workers_api.run_planner", side_effect=fixture_plan) as planner, patch(
            "asante_api.workers_api.run_researcher", new=AsyncMock(side_effect=[RuntimeError("fixture failure"), {"sources": [source], "summary": "Candidate evidence"}])
        ) as researcher:
            client.post(prefix + "/workspace/session", headers=headers, json={})
            self.register_contributor(client, "Brief contributor", "brief-" + uuid4().hex + "@example.test")
            project = client.post(prefix + "/workspace/projects", headers=headers, json={"id": uuid4().hex, "title": "Soweto oral history", "claim": "When did gatherings begin?"}).json()
            self.assertIsNone(project.get("researchBrief"))
            saved = client.post(prefix + "/workspace/projects", headers=headers, json={**project, "researchBrief": answers}).json()
            self.assertEqual(saved["researchBrief"], answers)
            self.assertEqual(saved["researchFlow"]["status"], "saved")
            path = prefix + "/workspace/projects/" + saved["id"] + "/workers"
            plan = client.post(path, headers=headers, json={"workerType": "planner", "expectedVersion": saved["version"]}).json()
            self.assertEqual(plan["status"], "succeeded")
            self.assertEqual(planner.call_args.args[0]["researchBrief"], answers)
            self.assertEqual(planner.call_args.args[0]["projectVersion"], saved["version"])
            duplicate = client.post(path, headers=headers, json={"workerType": "planner", "expectedVersion": saved["version"]})
            self.assertEqual(duplicate.status_code, 409)
            self.assertEqual(planner.call_count, 1)
            failed = client.post(path, headers=headers, json={"workerType": "researcher", "expectedVersion": plan["projectVersion"]})
            self.assertEqual(failed.status_code, 502)
            restored = next(item for item in client.get(prefix + "/workspace").json()["projects"] if item["id"] == saved["id"])
            self.assertEqual(restored["researchBrief"], answers)
            self.assertEqual(restored["researchFlow"]["status"], "failed")
            self.assertFalse(restored.get("planDocument"))
            result = client.post(path, headers=headers, json={"workerType": "researcher", "expectedVersion": restored["version"]}).json()
            self.assertEqual(result["status"], "succeeded")
            self.assertEqual(result["researchFlow"]["status"], "completed")
            self.assertEqual(result["planDocument"]["sources"][0]["url"], source["url"])
            self.assertEqual(researcher.call_args.args[0]["researchBrief"], answers)
            self.assertEqual(researcher.call_args.args[0]["planQuestions"], plan["plan"]["questions"])
            activity = client.get(path).json()["items"]
            self.assertTrue(any(event["kind"] == "handoff" for run in activity for event in run["activity"]))
            self.assertTrue(any(event["kind"] == "failed" for run in activity for event in run["activity"]))
            self.assertTrue(all(run["input"]["researchBrief"] == answers for run in activity))
            self.assertEqual(researcher.call_args.args[0]["projectVersion"], plan["projectVersion"])
            async def snapshots():
                async with session_factory()() as session:
                    return (await session.scalars(select(WorkerRunRecord).where(WorkerRunRecord.project_id == saved["id"]))).all()
            # Inspect durable inputs independently from provider mocks.
            for run in asyncio.run(snapshots()):
                self.assertEqual(run.input_payload["researchBrief"], answers)
            restored = next(item for item in client.get(prefix + "/workspace").json()["projects"] if item["id"] == saved["id"])
            changed = client.post(prefix + "/workspace/projects", headers=headers, json={**restored, "researchBrief": {**answers, "questions": "Who attended?"}}).json()
            self.assertEqual(changed["researchFlow"]["status"], "saved")
            self.assertEqual(changed["planDocument"], restored["planDocument"])
            invalid = client.post(prefix + "/workspace/projects", headers=headers, json={**changed, "researchBrief": {**answers, "questions": " "}})
            self.assertEqual(invalid.status_code, 200)
            self.assertEqual(invalid.json()["researchFlow"]["status"], "incomplete")
            self.assertEqual(client.post(path, headers=headers, json={"workerType": "planner", "expectedVersion": invalid.json()["version"]}).status_code, 422)

    def test_plan_document_share_export_and_collaborator_roles(self):
        prefix = "/asante/api/v1"
        headers = {"X-Asante-Request": "1", "Origin": "http://testserver"}
        with TestClient(app, root_path="/asante/api") as owner:
            owner.post(prefix + "/workspace/session", headers=headers, json={})
            self.register_contributor(owner, "Report owner", "report-owner-" + uuid4().hex + "@example.test")
            project = owner.post(prefix + "/workspace/projects", headers=headers, json={
                "id": uuid4().hex,
                "title": "Community river memory",
                "place": "Soweto Towers",
                "claim": "When did the gatherings begin?",
                "plan": {"outline": ["Introduce the river", "Compare memories"], "human_gate": "A human reviewer must approve publication."},
                "research": {"sources": [{"title": "Local archive", "url": "https://example.test/archive", "excerpt": "Candidate reference"}]},
            }).json()
            path = prefix + "/workspace/projects/" + project["id"] + "/plan-document"
            built = owner.get(path)
            self.assertEqual(built.status_code, 200, built.text)
            document = built.json()["document"]
            self.assertEqual(document["sections"][0]["title"], "Story outline")
            self.assertEqual(document["sources"][0]["title"], "Local archive")
            document["title"] = "Edited community field report"
            saved = owner.put(path, headers=headers, json={"expectedVersion": project["version"], "document": document})
            self.assertEqual(saved.status_code, 200, saved.text)
            self.assertEqual(saved.json()["document"]["title"], "Edited community field report")
            pdf = owner.get(path + "/export?format=pdf")
            text_export = owner.get(path + "/export?format=text")
            json_export = owner.get(path + "/export?format=json")
            self.assertEqual(pdf.status_code, 200)
            self.assertTrue(pdf.content.startswith(b"%PDF-"))
            self.assertIn("text/plain", text_export.headers["content-type"])
            self.assertIn("Edited community field report", text_export.text)
            self.assertEqual(json_export.json()["title"], "Edited community field report")

            shared = owner.post(prefix + "/workspace/projects/" + project["id"] + "/plan-share", headers=headers)
            self.assertEqual(shared.status_code, 200, shared.text)
            token = shared.json()["token"]
            share_path = prefix + "/plans/share/" + token
            anonymous = TestClient(app, root_path="/asante/api")
            self.assertEqual(anonymous.get(share_path).json()["canEdit"], False)
            invite_path = prefix + "/workspace/projects/" + project["id"] + "/plan-share/collaborators"
            invited = owner.post(invite_path, headers=headers, json={"email": "thabo@asante.test", "role": "viewer"})
            self.assertEqual(invited.status_code, 200, invited.text)
            viewer = TestClient(app, root_path="/asante/api")
            viewer.post(prefix + "/auth/login", headers=headers, json={"email": "thabo@asante.test", "password": self.passwords["thabo"]})
            self.assertEqual(viewer.get(share_path).json()["canEdit"], False)
            denied = viewer.put(share_path, headers=headers, json={"expectedVersion": saved.json()["version"], "document": document})
            self.assertEqual(denied.status_code, 403)
            updated_role = owner.post(invite_path, headers=headers, json={"email": "thabo@asante.test", "role": "editor"})
            self.assertEqual(updated_role.status_code, 200, updated_role.text)
            self.assertEqual(viewer.get(share_path).json()["canEdit"], True)
            document["summary"] = "An invited editor added this note."
            editor_save = viewer.put(share_path, headers=headers, json={"expectedVersion": saved.json()["version"], "document": document})
            self.assertEqual(editor_save.status_code, 200, editor_save.text)
            self.assertIn("An invited editor", anonymous.get(share_path).json()["document"]["summary"])

    def test_accounts_login_logout_revocation_expiry_and_roles(self):
        prefix = "/asante/api/v1"
        headers = {"X-Asante-Request": "1", "Origin": "http://testserver"}
        credentials = {"email": " NOMSA@ASANTE.TEST ", "password": self.passwords["nomsa"]}
        with TestClient(app, root_path="/asante/api") as client:
            wrong = client.post(prefix + "/auth/login", headers=headers, json={**credentials, "password": "Incorrect password for testing"})
            unknown = client.post(prefix + "/auth/login", headers=headers, json={"email": "unknown@example.test", "password": "Incorrect password for testing"})
            self.assertEqual(wrong.status_code, 401)
            self.assertEqual(wrong.json(), unknown.json())
            self.assertEqual(client.post(prefix + "/auth/login", json=credentials).status_code, 403)
            logged_in = client.post(prefix + "/auth/login", headers=headers, json=credentials)
            self.assertEqual(logged_in.status_code, 200, logged_in.text)
            self.assertIn("HttpOnly", logged_in.headers["set-cookie"])
            self.assertIn("SameSite=strict", logged_in.headers["set-cookie"])
            first = client.cookies.get("asante_account")
            self.assertEqual(client.get(prefix + "/review/queue").status_code, 403)
            self.assertEqual(client.get(prefix + "/review/queue", headers={"X-Asante-Reviewer-Key": "integration-reviewer-key"}).status_code, 403)
            self.assertEqual(client.post(prefix + "/auth/login", headers=headers, json=credentials).status_code, 200)
            second = client.cookies.get("asante_account")
            self.assertNotEqual(first, second)
            self.switch_cookie(client, first)
            self.assertEqual(client.get(prefix + "/auth/me").status_code, 401)
            self.switch_cookie(client, second)
            self.assertEqual(client.get(prefix + "/auth/me").json()["email"], "nomsa@asante.test")
            denied = client.post(prefix + "/auth/logout", headers={"X-Asante-Request": "1", "Origin": "https://attacker.example"})
            self.assertEqual(denied.status_code, 403)
            self.assertEqual(client.post(prefix + "/auth/logout", headers=headers).status_code, 200)
            self.switch_cookie(client, second)
            self.assertEqual(client.get(prefix + "/auth/me").status_code, 401)
            client.cookies.clear()
            self.assertEqual(client.post(prefix + "/auth/login", headers=headers, json={"email": "reviewer@asante.test", "password": self.passwords["reviewer"]}).status_code, 200)
            self.assertEqual(client.get(prefix + "/review/queue").status_code, 200)
            ensured = client.post(prefix + "/review/queue/ensure-jobs", headers=headers)
            self.assertEqual(ensured.status_code, 200, ensured.text)
            self.assertIn("pendingPackets", ensured.json())
            self.assertIn("queuedJobs", ensured.json())
            self.assertEqual(client.post(prefix + "/workspace/projects", headers=headers, json={"id": str(uuid4()), "title": "Reviewer cannot contribute"}).status_code, 403)
            active_token = client.cookies.get("asante_account")
            with psycopg.connect(**self.db_args, dbname=self.database) as connection:
                connection.execute("UPDATE asante.account_sessions SET expires_at=now()-interval '1 second' WHERE token_hash=%s", (hashlib.sha256(active_token.encode()).hexdigest(),))
            self.assertEqual(client.get(prefix + "/review/queue").status_code, 401)

    def test_account_profile_story_links_and_seed_preserve_existing_data(self):
        from app.db.seed import seed_public_catalogue
        asyncio.run(seed_public_catalogue())
        asyncio.run(seed_accounts(self.passwords))
        prefix = "/asante/api/v1"
        headers = {"X-Asante-Request": "1"}
        with TestClient(app, root_path="/asante/api") as client:
            stories = client.get(prefix + "/stories").json()["items"]
            self.assertEqual(len(stories), 4)
            self.assertEqual(len({story["contributor_id"] for story in stories}), 4)
            for story in stories:
                public = client.get(prefix + "/profiles/" + story["contributor_id"])
                self.assertEqual(public.status_code, 200)
                data = public.json()
                self.assertEqual(data["name"], story["contributor_name"])
                self.assertEqual([item["id"] for item in data["stories"]], [story["id"]])
                for private_field in ("email", "password_hash", "preferences", "projects", "object_key"):
                    self.assertNotIn(private_field, json.dumps(data))
            self.assertEqual(client.get(prefix + "/profiles/unknown").status_code, 404)
            login = client.post(prefix + "/auth/login", headers=headers, json={"email": "nomsa@asante.test", "password": self.passwords["nomsa"]})
            self.assertEqual(login.status_code, 200, login.text)
            workspace = client.get(prefix + "/workspace").json()
            self.assertEqual(workspace["publishedStories"][0]["id"], "story-001")
            draft = workspace["projects"][0]
            self.assertEqual(client.post(prefix + "/workspace/projects", headers=headers, json={**draft, "title": "Do not overwrite my edited test draft"}).status_code, 200)
            self.assertEqual(client.post(prefix + "/workspace/profile", headers=headers, json={**workspace["profile"], "email": "another@example.test"}).status_code, 422)
        with psycopg.connect(**self.db_args, dbname=self.database) as connection:
            before = connection.execute("SELECT password_hash FROM asante.accounts WHERE email='nomsa@asante.test'").fetchone()[0]
        asyncio.run(seed_accounts(self.passwords))
        with psycopg.connect(**self.db_args, dbname=self.database) as connection:
            after = connection.execute("SELECT password_hash FROM asante.accounts WHERE email='nomsa@asante.test'").fetchone()[0]
            self.assertEqual(before, after)
        with TestClient(app, root_path="/asante/api") as restarted:
            self.assertEqual(restarted.post(prefix + "/auth/login", headers=headers, json={"email": "nomsa@asante.test", "password": self.passwords["nomsa"]}).status_code, 200)
            self.assertEqual(restarted.get(prefix + "/workspace").json()["projects"][0]["title"], "Do not overwrite my edited test draft")

    def test_registration_links_explicit_device_workspace_without_role_escalation(self):
        prefix = "/asante/api/v1"
        headers = {"X-Asante-Request": "1"}
        with TestClient(app, root_path="/asante/api") as client:
            client.post(prefix + "/workspace/session", headers=headers)
            device_token = client.cookies.get("asante_workspace")
            email = "registration-" + uuid4().hex + "@example.test"
            body = {"name": "New contributor", "email": email, "password": "A unique Asante test password", "consent": True, "import_device": True}
            self.assertEqual(client.post(prefix + "/auth/register", headers=headers, json={**body, "role": "reviewer"}).status_code, 422)
            created = client.post(prefix + "/auth/register", headers=headers, json=body)
            self.assertEqual(created.status_code, 201, created.text)
            self.assertEqual(created.json()["role"], "contributor")
            profile_id = created.json()["profileId"]
            client.post(prefix + "/auth/logout", headers=headers)
            client.cookies.clear()
            client.cookies.set("asante_workspace", device_token, path="/asante/api")
            self.assertEqual(client.get(prefix + "/workspace").status_code, 401)
            self.assertEqual(client.post(prefix + "/auth/register", headers=headers, json=body).status_code, 409)
            client.cookies.clear()
            restored = client.post(prefix + "/auth/login", headers=headers, json={"email": email, "password": body["password"]})
            self.assertEqual(restored.json()["profileId"], profile_id)
            self.assertEqual(client.get(prefix + "/review/queue").status_code, 403)

    def test_login_rate_limit_persists_in_database(self):
        prefix = "/asante/api/v1"
        headers = {"X-Asante-Request": "1"}
        with TestClient(app, root_path="/asante/api") as client:
            body = {"email": "limited-" + uuid4().hex + "@example.test", "password": "Wrong Asante test password"}
            for _ in range(10):
                self.assertEqual(client.post(prefix + "/auth/login", headers=headers, json=body).status_code, 401)
            response = client.post(prefix + "/auth/login", headers=headers, json=body)
            self.assertEqual(response.status_code, 429)
            self.assertIn("Retry-After", response.headers)

    def test_workspace_upload_review_and_restart_are_persistent_and_isolated(self):
        prefix = "/asante/api/v1"
        headers = {"X-Asante-Request": "1", "Origin": "http://testserver"}
        review = {**headers, "X-Asante-Reviewer-Key": "integration-reviewer-key"}
        profile = {"name": "Test contributor", "email": "integration@example.test", "bio": "Original profile", "language": "en"}
        project = {"id": str(uuid4()), "title": "Persistent story", "place": "Constitution Hill", "language": "en", "format": "audio", "transcript": "Keep my original words", "version": 0}
        raw = {"local:asante.profile.v1": json.dumps(profile), "local:asante.projects.v1": json.dumps([project]), "local:asante.guide.v2": '{"version":2,"step":5}'}
        fixture = Path("/workspace/media/asante-playback-demo.mp3").read_bytes()
        temporary_before = set(Path("/tmp").glob("asante-upload-*"))
        with TestClient(app, root_path="/asante/api") as client:
            def post(path, data):
                return client.post(prefix + path, headers=headers, json=data)
            self.assertEqual(post("/workspace/session", {}).status_code, 200)
            self.register_contributor(client, profile["name"], profile["email"])
            self.assertEqual(post("/workspace/profile", profile).status_code, 200)
            token = client.cookies.get("asante_account")
            imported = post("/workspace/import", {"profile": profile, "projects": [project], "browser_data": raw, "consent": True})
            self.assertEqual(imported.status_code, 200, imported.text)
            self.assertEqual(post("/workspace/import", {"profile": profile, "projects": [project], "browser_data": raw, "consent": True}).status_code, 200)
            receipt = client.get(prefix + "/workspace/import-receipt/" + imported.json()["importChecksum"])
            self.assertTrue(receipt.json()["verified"])
            self.assertEqual(client.get(prefix + "/workspace/browser-backup").json(), raw)
            self.assertEqual(post("/workspace/preferences", {"key": "asante.onboarding.v2", "value": '{"version":2,"step":5}'}).status_code, 200)
            saved = client.get(prefix + "/workspace").json()["projects"][0]
            self.assertEqual(saved["version"], 1)
            self.assertEqual(post("/workspace/projects", {**saved, "title": "Changed story"}).status_code, 200)
            self.assertEqual(post("/workspace/projects", saved).status_code, 409)
            self.assertEqual(post("/workspace/import", {"profile": {**profile, "name": "Someone else"}, "browser_data": raw, "consent": True}).status_code, 409)
            self.assertEqual(post("/submissions", {"project_id": project["id"], "expected_version": 2, "consent_given": True}).status_code, 422)
            intent = post("/uploads", {"project_id": project["id"], "name": "original.mp3", "size": len(fixture), "content_type": "audio/mpeg", "consent_given": True}).json()
            uploaded = client.put(intent["uploadUrl"], headers=headers, content=fixture)
            self.assertEqual(uploaded.status_code, 200, uploaded.text)
            self.assertEqual(uploaded.json()["checksum"], hashlib.sha256(fixture).hexdigest())
            self.assertEqual(client.put(intent["uploadUrl"], headers=headers, content=fixture).status_code, 409)
            saved = client.get(prefix + "/workspace").json()["projects"][0]
            self.assertEqual(saved["media"]["size"], len(fixture))
            media_url = saved["media"]["url"]
            self.assertEqual(client.get(media_url, headers={"Range": "bytes=30-49"}).content, fixture[30:50])
            self.assertNotIn("object_key", json.dumps(saved))
            self.assertNotIn("originals/", json.dumps(saved))
            export_path = "/workspace/projects/" + project["id"] + "/download.zip"
            self.assertEqual(client.post(prefix + export_path, json={"expectedVersion": saved["version"]}).status_code, 403)
            self.assertEqual(post(export_path, {"expectedVersion": saved["version"] - 1}).status_code, 409)
            download = post(export_path, {"expectedVersion": saved["version"]})
            self.assertEqual(download.status_code, 200, download.text[:200] if download.status_code != 200 else "")
            self.assertEqual(download.headers["content-type"], "application/zip")
            self.assertEqual(download.headers["cache-control"], "no-store")
            self.assertIn(".zip", download.headers["content-disposition"])
            self.assertEqual(int(download.headers["content-length"]), len(download.content))
            with ZipFile(BytesIO(download.content)) as archive:
                self.assertIsNone(archive.testzip())
                self.assertEqual(archive.read("media/original.mp3"), fixture)
                self.assertEqual(archive.read("transcript.txt").decode().strip(), project["transcript"])
                self.assertEqual(json.loads(archive.read("project.json"))["version"], saved["version"])
                self.assertIn(profile["name"], archive.read("story-brief.txt").decode())
                self.assertNotIn("objectKey", archive.read("media/recording.json").decode())
            preview = client.get(prefix + "/submissions/preview/" + project["id"], params={"expected_version": saved["version"]})
            self.assertEqual(preview.status_code, 200, preview.text)
            packet = post("/submissions", {"project_id": project["id"], "expected_version": saved["version"], "consent_given": True, "preview_hash": preview.json()["preview_hash"]})
            self.assertEqual(packet.status_code, 201, packet.text)
            submission = packet.json()
            self.assertEqual(submission["revision_id"], preview.json()["revision_id"])
            self.assertEqual(submission["revision_version"], saved["version"])
            self.assertNotIn("project_revision", submission)
            self.assertNotIn("research", submission)
            repeated = post("/submissions", {"project_id": project["id"], "expected_version": saved["version"], "consent_given": True, "preview_hash": preview.json()["preview_hash"]})
            self.assertEqual(repeated.json()["submission_id"], submission["submission_id"])
            self.assertEqual(post("/workspace/projects", saved).status_code, 409)
            self.assertEqual(post("/workspace/projects/" + saved["id"] + "/workers", {"workerType": "planner", "expectedVersion": saved["version"]}).status_code, 409)
            self.assertEqual(post("/uploads", {"project_id": project["id"], "name": "replace.mp3", "size": len(fixture), "content_type": "audio/mpeg", "consent_given": True}).status_code, 409)
            decision_url = prefix + "/review/" + submission["submission_id"] + "/decision"
            decision = {"action": "request_changes", "reason": "Please clarify the source of this memory", "expected_version": 1}
            self.assertEqual(client.post(decision_url, headers=headers, json=decision).status_code, 403)
            self.assertEqual(client.get(submission["media_url"]).status_code, 403)
            client.cookies.clear()
            reviewer_login = post("/auth/login", {"email": "reviewer@asante.test", "password": self.passwords["reviewer"]})
            self.assertEqual(reviewer_login.status_code, 200, reviewer_login.text)
            reviewer_token = client.cookies.get("asante_account")
            approval = {"action": "approve", "reason": "Required assessment has not completed yet", "expected_version": 1}
            self.assertEqual(client.post(decision_url, headers=review, json=approval).status_code, 409)
            decided = client.post(decision_url, headers=review, json=decision)
            self.assertEqual(decided.status_code, 200, decided.text)
            self.assertEqual(client.post(decision_url, headers=review, json=decision).status_code, 409)
            self.assertEqual(client.post(prefix + "/review/session", headers=review).status_code, 200)
            self.assertEqual(client.get(submission["media_url"], headers={"Range": "bytes=0-9"}).content, fixture[:10])
            client.cookies.clear()
            self.assertEqual(post("/workspace/session", {}).status_code, 200)
            self.register_contributor(client, "Other contributor", "other-" + uuid4().hex + "@example.test")
            self.assertEqual(client.get(prefix + "/workspace").json()["projects"], [])
            self.assertEqual(client.get(media_url).status_code, 404)
            self.assertEqual(post("/workspace/projects", saved).status_code, 404)
            self.assertEqual(post(export_path, {"expectedVersion": saved["version"]}).status_code, 404)
            self.assertEqual(post("/submissions", {"project_id": project["id"], "expected_version": saved["version"], "consent_given": True, "preview_hash": "0" * 64}).status_code, 404)
        # A fresh lifespan disposes/recreates the DB engine just as a new API worker does.
        with TestClient(app, root_path="/asante/api") as restarted:
            restarted.cookies.set("asante_account", token, path="/asante/api")
            restored = restarted.get(prefix + "/workspace").json()
            self.assertEqual(restored["profile"], profile)
            self.assertEqual(restored["preferences"]["asante.onboarding.v2"], '{"version":2,"step":5}')
            self.assertEqual(restored["projects"][0]["transcript"], project["transcript"])
            self.switch_cookie(restarted, reviewer_token)
            queue = restarted.get(prefix + "/review/queue", headers=review).json()["items"]
            restored_submission = next(item for item in queue if item["submission_id"] == submission["submission_id"])
            self.assertEqual(restored_submission["status"], "changes_requested")
            self.assertEqual(restored_submission["decisions"][0]["reason"], decision["reason"])
            self.switch_cookie(restarted, token)
            self.assertEqual(restarted.get(media_url).content, fixture)
        self.assertEqual(set(Path("/tmp").glob("asante-upload-*")), temporary_before)

    def test_video_upload_submit_and_worker_attach_review_drafts(self):
        prefix = "/asante/api/v1"
        headers = {"X-Asante-Request": "1", "Origin": "http://testserver"}
        review = {**headers}
        fixture = Path("tests/fixtures/media/sample_video.mp4").read_bytes()
        project_id = str(uuid4())
        email = "video-flow-" + uuid4().hex + "@example.test"
        with TestClient(app, root_path="/asante/api") as client:
            client.post(prefix + "/workspace/session", headers=headers)
            self.register_contributor(client, "Video flow contributor", email)
            created = client.post(prefix + "/workspace/projects", headers=headers, json={
                "id": project_id, "title": "Short video processing story", "place": "Constitution Hill",
                "language": "en", "format": "video", "transcript": "Original contributor notes stay separate.",
                "claim": "Describe only what the clip visibly shows.",
            })
            self.assertEqual(created.status_code, 200, created.text)
            intent = client.post(prefix + "/uploads", headers=headers, json={
                "project_id": project_id, "name": "sample_video.mp4", "size": len(fixture),
                "content_type": "video/mp4", "consent_given": True,
            }).json()
            uploaded = client.put(intent["uploadUrl"], headers=headers, content=fixture)
            self.assertEqual(uploaded.status_code, 200, uploaded.text)
            derivatives = uploaded.json()["mediaDerivatives"]
            self.assertIn("audio_track", derivatives)
            self.assertIn("poster", derivatives)
            self.assertLessEqual(len(derivatives["keyframes"]), 4)
            self.assertNotIn("objectKey", json.dumps(derivatives))
            from reportlab.pdfgen.canvas import Canvas
            supporting_pdf = BytesIO()
            pdf = Canvas(supporting_pdf)
            pdf.drawString(72, 720, "Fixture archive: the bridge opened in 1960.")
            pdf.save()
            pdf_bytes = supporting_pdf.getvalue()
            pdf_intent = client.post(prefix + "/uploads", headers=headers, json={
                "project_id": project_id, "name": "supporting-evidence.pdf", "size": len(pdf_bytes),
                "content_type": "application/pdf", "purpose": "supporting_document", "consent_given": True,
            }).json()
            self.assertEqual(client.put(pdf_intent["uploadUrl"], headers=headers, content=pdf_bytes).status_code, 200)
            saved = next(item for item in client.get(prefix + "/workspace").json()["projects"] if item["id"] == project_id)
            preview = client.get(prefix + "/submissions/preview/" + project_id, params={"expected_version": saved["version"]})
            self.assertEqual(preview.status_code, 200, preview.text)
            submission = client.post(prefix + "/submissions", headers=headers, json={
                "project_id": project_id, "expected_version": saved["version"], "consent_given": True, "preview_hash": preview.json()["preview_hash"],
            })
            self.assertEqual(submission.status_code, 201, submission.text)
            packet = submission.json()
            self.assertEqual({job["jobType"] for job in packet["jobs"]}, {"assessment", "transcribe", "translate", "analyze"})
            self.assertEqual({job["status"] for job in packet["jobs"]}, {"queued"})
            self.assertTrue(packet["original_media"]["checksum"])
            self.assertEqual(len(packet["media_derivatives"]), len(derivatives["keyframes"]) + 2)

            async def claim_first_job():
                async with session_factory()() as session:
                    selected_job = await claim_next_job(session, "dependency-test-worker")
                    self.assertEqual(selected_job.job_type, "transcribe")
                    selected_job.status = "queued"
                    selected_job.lease_owner = ""
                    selected_job.lease_expires_at = None
                    await session.commit()
            asyncio.run(claim_first_job())

            with patch("asante_api.ai.jobs._optional_whisper_transcribe", return_value={
                "text": "Synthetic fixture transcript.", "language": "en",
                "segments": [{"start": 0.0, "end": 1.0, "text": "Synthetic fixture transcript."}],
                "backend": "test-fixture", "model": "fixture",
            }), patch("asante_api.ai.jobs.ask_model_media", return_value={
                "observations": [{"timestamp": 0.5, "observation": "A green geometric scene is visible."}],
            }), patch.dict(os.environ, {"ASANTE_AI_PROVIDER": "fake"}):
                async def process_queued():
                    async with session_factory()() as session:
                        queued = (await session.scalars(
                            select(ProcessingJobRecord)
                            .where(ProcessingJobRecord.submission_id == packet["submission_id"])
                        )).all()
                        queued.sort(key=lambda job: {"transcribe": 10, "translate": 20, "analyze": 30, "assessment": 40}[job.job_type])
                        for job in queued:
                            job.status = "running"
                            job.attempt = 1
                            job.lease_owner = "video-test-worker"
                            from datetime import datetime, timedelta, timezone
                            job.lease_expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
                            await process_job(session, job)
                        await session.commit()

                asyncio.run(process_queued())

            client.cookies.clear()
            login = client.post(prefix + "/auth/login", headers=headers, json={
                "email": "reviewer@asante.test", "password": self.passwords["reviewer"],
            })
            self.assertEqual(login.status_code, 200, login.text)
            queue = client.get(prefix + "/review/queue", headers=review)
            self.assertEqual(queue.status_code, 200, queue.text)
            reviewed = next(item for item in queue.json()["items"] if item["submission_id"] == packet["submission_id"])
            self.assertEqual({job["status"] for job in reviewed["jobs"]}, {"succeeded"})
            self.assertEqual(reviewed["preview_hash"], packet["preview_hash"])
            self.assertNotIn("project_revision", reviewed)
            self.assertNotIn("research", reviewed)
            self.assertIn(reviewed["assessment"]["status"], {"complete", "partial", "unavailable"})
            self.assertIn(reviewed["assessment"]["claimEvidence"]["status"], {"complete", "incomplete", "timeout", "malformed", "provider_unavailable"})
            self.assertEqual(reviewed["assessment"]["schemaVersion"], "asante.assessment.v2")
            self.assertEqual(reviewed["assessment"]["promptVersion"], "submission-evidence.v2")
            self.assertTrue(any(item["evidenceId"] == "video_transcript_en" for item in reviewed["assessment"]["claimEvidence"]["evidence"]))
            self.assertTrue(any(item["evidenceId"] == "supporting_pdf" for item in reviewed["assessment"]["claimEvidence"]["evidence"]))
            self.assertIn("supporting_pdf", json.dumps(reviewed["assessment"]["claimEvidence"]))
            self.assertNotIn("research", json.dumps(reviewed["assessment"]))
            self.assertNotIn("source_url", json.dumps(reviewed))
            self.assertTrue(reviewed["review_policy"]["may_approve"])
            self.assertEqual(reviewed["transcriptDraft"]["status"], "draft")
            self.assertIn("Synthetic fixture transcript", reviewed["transcriptDraft"]["text"])
            self.assertEqual(reviewed["videoAnalysis"]["status"], "draft")
            self.assertLessEqual(reviewed["videoAnalysis"]["frame_count"], 4)
            self.assertIn("not heritage proof", reviewed["videoAnalysis"]["note"])
            self.assertEqual(client.get(reviewed["media_url"]).content, fixture)

    def test_upload_rejects_spoofed_truncated_oversized_expired_and_wrong_owner_files(self):
        prefix = "/asante/api/v1"
        headers = {"X-Asante-Request": "1"}
        with TestClient(app, root_path="/asante/api") as client:
            client.post(prefix + "/workspace/session", headers=headers)
            self.register_contributor(client, "Upload test", "test@example.test")
            project = client.post(prefix + "/workspace/projects", headers=headers, json={"id": str(uuid4()), "title": "Upload checks"}).json()
            def intent(size):
                return client.post(prefix + "/uploads", headers=headers, json={"project_id": project["id"], "name": "bad.mp3", "size": size, "content_type": "audio/mpeg", "consent_given": True}).json()
            spoof = intent(8)
            self.assertEqual(client.put(spoof["uploadUrl"], headers=headers, content=b"notaudio").status_code, 422)
            self.assertEqual(client.put(intent(9)["uploadUrl"], headers=headers, content=b"short").status_code, 422)
            self.assertEqual(client.put(intent(1)["uploadUrl"], headers=headers, content=b"long").status_code, 413)
            expired = intent(8)
            with psycopg.connect(**self.db_args, dbname=self.database) as connection:
                connection.execute("UPDATE asante.uploads SET expires_at = now() - interval '1 second' WHERE id = %s", (expired["id"],))
            self.assertEqual(client.put(expired["uploadUrl"], headers=headers, content=b"notaudio").status_code, 409)
            client.cookies.clear()
            client.post(prefix + "/workspace/session", headers=headers)
            self.register_contributor(client, "Other upload tester", "other-upload@example.test")
            self.assertEqual(client.put(spoof["uploadUrl"], headers=headers, content=b"notaudio").status_code, 404)
            self.assertFalse(any(item.object_name.startswith("originals/") for item in self.storage.list_objects(self.bucket, recursive=True)))

    def test_video_and_other_supported_audio_formats_upload_and_stream(self):
        prefix = "/asante/api/v1"
        headers = {"X-Asante-Request": "1"}
        with TestClient(app, root_path="/asante/api") as client, tempfile.TemporaryDirectory(prefix="asante-media-test-") as directory:
            client.post(prefix + "/workspace/session", headers=headers)
            self.register_contributor(client, "Media formats", "formats@example.test")
            for extension, content_type, source, codec in [
                ("wav", "audio/wav", "sine=frequency=440:duration=1", "pcm_s16le"),
                ("ogg", "audio/ogg", "sine=frequency=440:duration=1", "libvorbis"),
                ("mp4", "video/mp4", "color=c=green:s=160x90:d=1", "mpeg4"),
                ("webm", "video/webm", "color=c=green:s=160x90:d=1", "libvpx"),
            ]:
                with self.subTest(format=extension):
                    path = Path(directory) / ("recording." + extension)
                    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", source, "-c:a" if content_type.startswith("audio/") else "-c:v", codec, str(path)], check=True, capture_output=True, timeout=20)
                    content = path.read_bytes()
                    project = client.post(prefix + "/workspace/projects", headers=headers, json={"id": str(uuid4()), "title": "Format check " + extension}).json()
                    intent = client.post(prefix + "/uploads", headers=headers, json={"project_id": project["id"], "name": path.name, "size": len(content), "content_type": content_type, "consent_given": True}).json()
                    uploaded = client.put(intent["uploadUrl"], headers=headers, content=content)
                    self.assertEqual(uploaded.status_code, 200, uploaded.text)
                    media_url = prefix + "/uploads/" + intent["id"] + "/media"
                    response = client.get(media_url, headers={"Range": "bytes=0-49"})
                    self.assertEqual(response.status_code, 206)
                    self.assertEqual(response.content, content[:50])
                    self.assertEqual(response.headers["content-type"], content_type)
