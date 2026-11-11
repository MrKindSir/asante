import subprocess
import unittest


class RunningServiceTests(unittest.TestCase):
    def test_asante_infrastructure_services_are_running(self):
        result = subprocess.run(
            ["docker", "compose", "--env-file", ".env", "-f", "infrastructure/docker-compose.yml", "ps", "--format", "json"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("asante-postgres-1", result.stdout)
        self.assertIn("asante-minio-1", result.stdout)


if __name__ == "__main__":
    unittest.main()
