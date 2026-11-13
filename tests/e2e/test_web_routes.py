import unittest
import os
from urllib.error import URLError
from urllib.request import urlopen


BASE_URL = os.environ.get("ASANTE_BASE_URL", "http://localhost")


def route_is_ready(url: str) -> bool:
    try:
        with urlopen(url, timeout=2) as response:
            return response.status == 200
    except (URLError, TimeoutError):
        return False


class WebRouteTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("ASANTE_REQUIRE_SERVICES") == "1" or route_is_ready(f"{BASE_URL}/asante/"), "Asante website is not running")
    def test_asante_website_route(self):
        self.assertTrue(route_is_ready(f"{BASE_URL}/asante/"))

    @unittest.skipUnless(os.environ.get("ASANTE_REQUIRE_SERVICES") == "1" or route_is_ready(f"{BASE_URL}/asante/review/"), "Asante dashboard is not running")
    def test_asante_dashboard_route(self):
        self.assertTrue(route_is_ready(f"{BASE_URL}/asante/review/"))

    @unittest.skipUnless(os.environ.get("ASANTE_REQUIRE_SERVICES") == "1" or route_is_ready(f"{BASE_URL}/asante/portal/"), "Asante portal is not running")
    def test_asante_portal_route(self):
        self.assertTrue(route_is_ready(f"{BASE_URL}/asante/portal/"))


if __name__ == "__main__":
    unittest.main()
