"""Real-world contributor flow against the running local Asante stack.

Mimics: sign in → create project → upload verified media → preview → submit,
plus isolation / auth vulnerability checks that must hold in production-like use.

Requires:
  - Compose stack reachable at ASANTE_BASE_URL (default http://localhost)
  - `.env.asante-test-accounts` from `python scripts/asante/accounts.py`
  - `tests/fixtures/media/sample_video.mp4`

Run:
  ASANTE_REQUIRE_SERVICES=1 python -m unittest tests.e2e.test_contributor_submit_flow -v
"""

from __future__ import annotations

import hashlib
import http.cookiejar
import json
import os
import unittest
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

ROOT = Path(__file__).resolve().parents[2]
BASE_URL = os.environ.get("ASANTE_BASE_URL", "http://localhost").rstrip("/")
API = BASE_URL + "/asante/api/v1"
FIXTURE = ROOT / "tests" / "fixtures" / "media" / "sample_video.mp4"


class ContributorSubmitFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        accounts = ROOT / ".env.asante-test-accounts"
        if not accounts.exists():
            if os.environ.get("ASANTE_REQUIRE_SERVICES") == "1":
                raise AssertionError("Provision accounts with: python scripts/asante/accounts.py")
            raise unittest.SkipTest("Local Asante test accounts have not been provisioned")
        if not FIXTURE.is_file():
            raise unittest.SkipTest(f"Missing fixture media: {FIXTURE}")
        cls.passwords = dict(
            line.split("=", 1)
            for line in accounts.read_text(encoding="utf-8").splitlines()
            if line and not line.startswith("#") and "=" in line
        )
        cls.fixture = FIXTURE.read_bytes()

    def opener(self):
        jar = http.cookiejar.CookieJar()
        return build_opener(HTTPCookieProcessor(jar)), jar

    def csrf_from(self, jar: http.cookiejar.CookieJar) -> str | None:
        for cookie in jar:
            if cookie.name == "asante_csrf":
                return cookie.value
        return None

    def request(self, opener, method: str, path: str, body=None, raw: bytes | None = None, content_type: str | None = None, jar: http.cookiejar.CookieJar | None = None):
        headers = {
            "X-Asante-Request": "1",
            "Origin": BASE_URL,
        }
        if jar is not None:
            csrf = self.csrf_from(jar)
            if csrf:
                headers["X-Asante-Csrf"] = csrf
        data = None
        if raw is not None:
            data = raw
            headers["Content-Type"] = content_type or "application/octet-stream"
        elif body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(API + path, data=data, headers=headers, method=method)
        try:
            with opener.open(request, timeout=120) as response:
                payload = response.read()
                if not payload:
                    return response.status, None
                ctype = response.headers.get("Content-Type", "")
                if "json" in ctype:
                    return response.status, json.loads(payload.decode("utf-8"))
                return response.status, payload
        except HTTPError as error:
            detail = error.read()
            try:
                parsed = json.loads(detail.decode("utf-8")) if detail else None
            except json.JSONDecodeError:
                parsed = detail.decode("utf-8", errors="replace") if detail else None
            return error.code, parsed

    def sign_in(self, slug: str):
        opener, jar = self.opener()
        status, account = self.request(
            opener,
            "POST",
            "/auth/login",
            {
                "email": f"{slug}@asante.test",
                "password": self.passwords[f"ASANTE_TEST_{slug.upper()}_PASSWORD"],
            },
            jar=jar,
        )
        self.assertEqual(status, 200, f"login failed for {slug}: {account}")
        self.assertTrue(self.csrf_from(jar), "login must set asante_csrf cookie")
        return opener, jar, account

    def test_login_create_project_upload_submit_and_isolation(self):
        nomsa, nomsa_jar, account = self.sign_in("nomsa")
        self.assertEqual(account["role"], "contributor")

        # Unauthenticated create must fail.
        anon, anon_jar = self.opener()
        self.assertEqual(
            self.request(anon, "POST", "/workspace/projects", {"id": uuid.uuid4().hex, "title": "Should fail"}, jar=anon_jar)[0],
            401,
        )

        project_id = uuid.uuid4().hex
        status, project = self.request(
            nomsa,
            "POST",
            "/workspace/projects",
            {
                "id": project_id,
                "title": "E2E flow story — Constitution Hill",
                "place": "Constitution Hill",
                "language": "en",
                "format": "video",
                "claim": "What does this short clip visibly show at a rights landmark?",
                "transcript": "TEST ONLY e2e contributor notes; not a heritage claim.",
            },
            jar=nomsa_jar,
        )
        self.assertEqual(status, 200, project)
        self.assertEqual(project["id"], project_id)
        self.assertGreaterEqual(int(project["version"]), 1)

        # Upload without consent must fail.
        denied = self.request(
            nomsa,
            "POST",
            "/uploads",
            {
                "project_id": project_id,
                "name": "sample_video.mp4",
                "size": len(self.fixture),
                "content_type": "video/mp4",
                "consent_given": False,
            },
            jar=nomsa_jar,
        )
        self.assertIn(denied[0], {400, 422}, denied)

        intent_status, intent = self.request(
            nomsa,
            "POST",
            "/uploads",
            {
                "project_id": project_id,
                "name": "sample_video.mp4",
                "size": len(self.fixture),
                "content_type": "video/mp4",
                "consent_given": True,
            },
            jar=nomsa_jar,
        )
        self.assertIn(intent_status, {200, 201}, intent)
        upload_url = intent["uploadUrl"]
        self.assertTrue(upload_url.startswith("/asante/api/") or upload_url.startswith("http"))
        put_path = upload_url.replace(BASE_URL, "") if upload_url.startswith("http") else upload_url
        put_api_path = put_path.replace("/asante/api/v1", "") if put_path.startswith("/asante/api/v1") else put_path
        put_status, uploaded = self.request(
            nomsa, "PUT", put_api_path, raw=self.fixture, content_type="video/mp4", jar=nomsa_jar
        )
        self.assertEqual(put_status, 200, uploaded)
        self.assertEqual(uploaded["checksum"], hashlib.sha256(self.fixture).hexdigest())
        self.assertIn("mediaDerivatives", uploaded)
        # Replay of the same upload intent must fail.
        self.assertEqual(
            self.request(nomsa, "PUT", put_api_path, raw=self.fixture, content_type="video/mp4", jar=nomsa_jar)[0],
            409,
        )

        # Another contributor must not upload into Nomsa's project.
        thabo, thabo_jar, _ = self.sign_in("thabo")
        foreign = self.request(
            thabo,
            "POST",
            "/uploads",
            {
                "project_id": project_id,
                "name": "steal.mp4",
                "size": len(self.fixture),
                "content_type": "video/mp4",
                "consent_given": True,
            },
            jar=thabo_jar,
        )
        self.assertIn(foreign[0], {403, 404}, foreign)

        status, workspace = self.request(nomsa, "GET", "/workspace", jar=nomsa_jar)
        self.assertEqual(status, 200, workspace)
        saved = next(item for item in workspace["projects"] if item["id"] == project_id)

        preview_status, preview = self.request(
            nomsa,
            "GET",
            f"/submissions/preview/{project_id}?expected_version={saved['version']}",
            jar=nomsa_jar,
        )
        self.assertEqual(preview_status, 200, preview)
        self.assertRegex(preview["preview_hash"], r"^[a-f0-9]{64}$")
        # Stale / forged preview hash must not submit.
        bad_hash = self.request(
            nomsa,
            "POST",
            "/submissions",
            {
                "project_id": project_id,
                "expected_version": saved["version"],
                "consent_given": True,
                "preview_hash": "0" * 64,
            },
            jar=nomsa_jar,
        )
        self.assertIn(bad_hash[0], {409, 422}, bad_hash)

        submit_status, packet = self.request(
            nomsa,
            "POST",
            "/submissions",
            {
                "project_id": project_id,
                "expected_version": saved["version"],
                "consent_given": True,
                "preview_hash": preview["preview_hash"],
            },
            jar=nomsa_jar,
        )
        self.assertEqual(submit_status, 201, packet)
        self.assertEqual(packet["status"], "pending_review")
        self.assertTrue(packet.get("submission_id") or packet.get("id"))
        submission_id = packet.get("submission_id") or packet.get("id")
        repeated = self.request(
            nomsa,
            "POST",
            "/submissions",
            {
                "project_id": project_id,
                "expected_version": saved["version"],
                "consent_given": True,
                "preview_hash": preview["preview_hash"],
            },
            jar=nomsa_jar,
        )
        self.assertIn(repeated[0], {200, 201, 409}, repeated)

        # Contributor must not open the reviewer queue.
        self.assertEqual(self.request(nomsa, "GET", "/review/queue", jar=nomsa_jar)[0], 403)
        # Other contributor must not read Nomsa's review packet media.
        if packet.get("media_url"):
            media_path = packet["media_url"].replace("/asante/api/v1", "")
            self.assertIn(self.request(thabo, "GET", media_path, jar=thabo_jar)[0], {401, 403, 404})

        # Reviewer can see the pending packet (no auto-publish).
        reviewer, reviewer_jar, reviewer_account = self.sign_in("reviewer")
        self.assertEqual(reviewer_account["role"], "reviewer")
        queue_status, queue = self.request(reviewer, "GET", "/review/queue", jar=reviewer_jar)
        self.assertEqual(queue_status, 200, queue)
        items = queue.get("items") or []
        match = next((item for item in items if item.get("submission_id") == submission_id), None)
        self.assertIsNotNone(match, f"submitted packet {submission_id} missing from reviewer queue")
        self.assertNotIn("research", json.dumps(match).lower())
        self.assertNotEqual(match.get("status"), "published")

        # Sign out must revoke session.
        self.assertEqual(self.request(nomsa, "POST", "/auth/logout", {}, jar=nomsa_jar)[0], 200)
        self.assertEqual(self.request(nomsa, "GET", "/auth/me", jar=nomsa_jar)[0], 401)


if __name__ == "__main__":
    unittest.main()
