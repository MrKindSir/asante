import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class RepositoryContractTests(unittest.TestCase):
    def test_two_asante_websites_exist(self):
        self.assertTrue((ROOT / "app/websites/asante/package.json").exists())
        self.assertTrue((ROOT / "app/websites/dashboard/package.json").exists())

    def test_environment_template_contains_asante_variables(self):
        env = (ROOT / ".env.example").read_text()
        self.assertIn("ASANTE_POSTGRES_DB", env)
        self.assertIn("ASANTE_MINIO_ROOT_USER", env)


if __name__ == "__main__":
    unittest.main()
