import unittest
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "app/services/api"))

try:
    from fastapi.testclient import TestClient
    from asante_api.main import app
except ModuleNotFoundError as error:  # pragma: no cover - environment-dependent skip
    raise unittest.SkipTest(f"Asante API dependencies are not installed: {error}")


class ApiRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        self.reviewer_env = patch.dict("os.environ", {"ASANTE_REVIEWER_KEY": "asante-test-key"})
        self.reviewer_env.start()
        self.addCleanup(self.reviewer_env.stop)

    def test_health_route(self):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["service"], "asante-api")

    def test_plan_route_returns_worker_contract(self):
        response = self.client.post(
            "/v1/story-projects/plan",
            json={
                "topic": "A river memory",
                "place_name": "Soweto",
                "language": "zu",
                "media_format": "audio",
                "audience": "local listeners",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["project_id"].startswith("project_"))
        self.assertIn("human reviewer", body["human_gate"].lower())
        self.assertTrue(body["worker_steps"])

    def test_private_workspace_requires_session(self):
        self.assertEqual(self.client.get("/v1/workspace").status_code, 401)
        self.assertEqual(self.client.post("/v1/workspace/session").status_code, 403)
        self.assertEqual(self.client.post("/v1/workspace/session", headers={"X-Asante-Request": "1", "Origin": "https://untrusted.example"}).status_code, 403)

    def test_review_queue_requires_access(self):
        self.assertEqual(self.client.get("/v1/review/queue").status_code, 401)
        self.assertEqual(self.client.get("/v1/review/queue", headers={"X-Asante-Reviewer-Key": "wrong"}).status_code, 401)


if __name__ == "__main__":
    unittest.main()
