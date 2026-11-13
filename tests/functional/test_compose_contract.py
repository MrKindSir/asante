import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class ComposeContractTests(unittest.TestCase):
    def test_compose_declares_user_apps_and_infrastructure(self):
        compose = (ROOT / "infrastructure/docker-compose.yml").read_text()
        for service in ("api:", "job-worker:", "asante:", "dashboard:", "proxy:", "postgres:", "minio:"):
            self.assertIn(service, compose)
        self.assertIn('"-m", "asante_api.job_worker"', compose)
        self.assertIn("ASANTE_OLLAMA_BASE_URL", compose)
        self.assertIn("ASANTE_WHISPER_MODEL", compose)

    def test_compose_exposes_expected_ports(self):
        compose = (ROOT / "infrastructure/docker-compose.yml").read_text()
        for port in ('ASANTE_HTTP_PORT:-80', 'ASANTE_POSTGRES_PORT:-5432', 'ASANTE_MINIO_API_PORT:-9000'):
            self.assertIn(port, compose)
        self.assertNotIn('"3000:3000"', compose)
        self.assertNotIn('"3001:3001"', compose)

    def test_review_route_targets_internal_dashboard(self):
        proxy = (ROOT / "infrastructure/nginx/asante.conf").read_text()
        route = proxy.split("location /asante/review/ {", 1)[1].split("}", 1)[0]
        self.assertIn("proxy_pass http://$dashboard_upstream;", route)


if __name__ == "__main__":
    unittest.main()
