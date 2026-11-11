import json
import os
import unittest
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BASE_URL = os.environ.get("ASANTE_BASE_URL", "http://localhost")


def get_json(path: str) -> tuple[int, dict]:
    with urlopen(f"{BASE_URL}{path}", timeout=3) as response:
        return response.status, json.load(response)


class LiveApiRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            status_code, _ = get_json("/asante/api/health")
        except Exception as error:  # pragma: no cover - skip behavior only applies without a running stack
            if os.environ.get("ASANTE_REQUIRE_SERVICES") == "1":
                raise AssertionError(f"Asante API must be running: {error}") from error
            raise unittest.SkipTest(f"Asante API is not running: {error}")
        if status_code != 200:
            raise unittest.SkipTest("Asante API health check did not return 200")

    def test_health_query(self):
        status_code, body = get_json("/asante/api/health")

        self.assertEqual(status_code, 200)
        self.assertEqual(body["status"], "ok")

    def test_database_and_storage_are_ready(self):
        status_code, body = get_json("/asante/api/health/ready")
        self.assertEqual(status_code, 200)
        self.assertEqual(body["database"], "ok")
        self.assertEqual(body["mediaStorage"], "ok")

    def test_landmark_query_returns_fixture_results(self):
        query = urlencode({"latitude": -26.2041, "longitude": 28.0473, "radius_m": 10000})
        status_code, body = get_json(f"/asante/api/v1/landmarks/nearby?{query}")

        self.assertEqual(status_code, 200)
        self.assertGreaterEqual(len(body["items"]), 1)
        self.assertEqual(body["items"], sorted(body["items"], key=lambda item: item["distance_m"]))

    def test_story_query_returns_published_only(self):
        query = urlencode({"latitude": -26.2041, "longitude": 28.0473, "radius_m": 10000})
        status_code, body = get_json(f"/asante/api/v1/stories/nearby?{query}")

        self.assertEqual(status_code, 200)
        self.assertTrue(all(item["status"] == "published" for item in body["items"]))

    def test_global_story_catalog_and_audio_range_work_from_distant_location(self):
        _, catalog = get_json("/asante/api/v1/stories")
        _, distant = get_json("/asante/api/v1/stories?latitude=-33.8688&longitude=151.2093")
        self.assertEqual({item["id"] for item in catalog["items"]}, {item["id"] for item in distant["items"]})
        demo = next(item for item in distant["items"] if item["is_demo"])
        self.assertGreater(demo["distance_m"], 1000000)
        request = Request(BASE_URL + demo["media_url"], headers={"Range": "bytes=0-99"})
        with urlopen(request, timeout=5) as response:
            self.assertEqual(response.status, 206)
            self.assertEqual(len(response.read()), 100)
            self.assertEqual(response.headers["Content-Type"], "audio/mpeg")


if __name__ == "__main__":
    unittest.main()
