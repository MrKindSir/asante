"""Non-GUI account checks through the real public Asante proxy URLs."""
import http.cookiejar
from io import BytesIO
import json
import os
from pathlib import Path
import unittest
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener
from zipfile import ZipFile

from app.db.seed_accounts import TEST_ACCOUNTS

BASE_URL = os.environ.get("ASANTE_BASE_URL", "http://localhost").rstrip("/")


class LiveAccountTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[2] / ".env.asante-test-accounts"
        if not path.exists():
            if os.environ.get("ASANTE_REQUIRE_SERVICES") == "1":
                raise AssertionError("Run python scripts/asante/accounts.py before live account checks")
            raise unittest.SkipTest("Local Asante test accounts have not been provisioned")
        cls.passwords = dict(line.split("=", 1) for line in path.read_text().splitlines() if line and not line.startswith("#"))

    def csrf_from(self, jar):
        for cookie in jar:
            if cookie.name == "asante_csrf":
                return cookie.value
        return None

    def request(self, opener, path, body=None, jar=None):
        headers = {"Content-Type": "application/json", "X-Asante-Request": "1", "Origin": BASE_URL}
        if jar is not None:
            csrf = self.csrf_from(jar)
            if csrf:
                headers["X-Asante-Csrf"] = csrf
        request = Request(
            BASE_URL + "/asante/api/v1" + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers=headers,
        )
        try:
            with opener.open(request, timeout=15) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            return error.code, json.load(error)

    def sign_in(self, slug):
        jar = http.cookiejar.CookieJar()
        opener = build_opener(HTTPCookieProcessor(jar))
        status, account = self.request(
            opener,
            "/auth/login",
            {"email": f"{slug}@asante.test", "password": self.passwords["ASANTE_TEST_" + slug.upper() + "_PASSWORD"]},
            jar=jar,
        )
        self.assertEqual(status, 200, f"Sign-in failed for local test account {slug}")
        return opener, jar, account

    def test_all_test_accounts_sign_in_restore_and_sign_out(self):
        for slug, _, _, role, story_slug in TEST_ACCOUNTS:
            with self.subTest(account=slug):
                opener, jar, account = self.sign_in(slug)
                self.assertEqual(account["role"], role)
                status, workspace = self.request(opener, "/workspace", jar=jar)
                self.assertEqual(status, 200)
                self.assertEqual(workspace["account"]["id"], account["id"])
                self.assertEqual(workspace["profile"]["email"], account["email"])
                if story_slug:
                    self.assertIn(story_slug, [story["id"] for story in workspace["publishedStories"]])
                    self.assertTrue(all(story["contributor_id"] == account["profileId"] for story in workspace["publishedStories"]))
                self.assertEqual(self.request(opener, "/review/queue", jar=jar)[0], 200 if role == "reviewer" else 403)
                self.assertEqual(self.request(opener, "/auth/logout", {}, jar=jar)[0], 200)
                self.assertEqual(self.request(opener, "/auth/me", jar=jar)[0], 401)

    def test_other_contributor_cannot_write_the_first_contributors_draft(self):
        nomsa, nomsa_jar, _ = self.sign_in("nomsa")
        _, workspace = self.request(nomsa, "/workspace", jar=nomsa_jar)
        draft = workspace["projects"][0]
        thabo, thabo_jar, _ = self.sign_in("thabo")
        self.assertEqual(self.request(thabo, "/workspace/projects", draft, jar=thabo_jar)[0], 404)
        self.request(nomsa, "/auth/logout", {}, jar=nomsa_jar)
        self.request(thabo, "/auth/logout", {}, jar=thabo_jar)

    def test_contributor_downloads_story_zip_through_the_public_proxy(self):
        opener, jar, _ = self.sign_in("nomsa")
        try:
            status, workspace = self.request(opener, "/workspace", jar=jar)
            self.assertEqual(status, 200)
            project = workspace["projects"][0]
            headers = {"Content-Type": "application/json", "X-Asante-Request": "1", "Origin": BASE_URL}
            csrf = self.csrf_from(jar)
            if csrf:
                headers["X-Asante-Csrf"] = csrf
            request = Request(
                BASE_URL + "/asante/api/v1/workspace/projects/" + project["id"] + "/download.zip",
                data=json.dumps({"expectedVersion": project["version"]}).encode(),
                headers=headers,
            )
            with opener.open(request, timeout=120) as response:
                self.assertEqual(response.headers["Content-Type"], "application/zip")
                self.assertIn(".zip", response.headers["Content-Disposition"])
                archive_bytes = response.read()
            with ZipFile(BytesIO(archive_bytes)) as archive:
                self.assertIsNone(archive.testzip())
                self.assertIn("README.txt", archive.namelist())
                self.assertTrue(archive.read("field-report.pdf").startswith(b"%PDF-"))
                packet = json.loads(archive.read("project.json"))
                self.assertEqual(packet["projectId"], project["id"])
                self.assertEqual(packet["title"], project["title"])
        finally:
            self.request(opener, "/auth/logout", {}, jar=jar)
