"""Create/reuse ignored local credentials, then provision explicit test accounts."""
from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from app.db.seed_accounts import TEST_ACCOUNTS


def main() -> None:
    path = ROOT / ".env.asante-test-accounts"
    if path.exists():
        values = dict(line.split("=", 1) for line in path.read_text().splitlines() if line and not line.startswith("#"))
    else:
        values = {"ASANTE_TEST_" + item[0].upper() + "_PASSWORD": secrets.token_urlsafe(20) for item in TEST_ACCOUNTS}
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as output:
            output.write("# Local Asante test passwords. Never commit or include in Docker images.\n")
            output.write("\n".join(key + "=" + value for key, value in values.items()) + "\n")
    passwords = {item[0]: values["ASANTE_TEST_" + item[0].upper() + "_PASSWORD"] for item in TEST_ACCOUNTS}
    completed = subprocess.run(["docker", "compose", "--env-file", ".env", "-f", "infrastructure/docker-compose.yml", "exec", "-T", "api", "python", "-m", "app.db.seed_accounts"], cwd=ROOT, input=json.dumps(passwords), text=True, capture_output=True, check=False)
    if completed.returncode:
        # Seed errors contain no supplied passwords; never print subprocess input.
        raise SystemExit(completed.stderr or "Asante account provisioning failed")
    print(completed.stdout.strip())
    print(f"Local credentials: {path}")
    for slug, name, _, role, _ in TEST_ACCOUNTS:
        print(f"{name}: {slug}@asante.test ({role})")


if __name__ == "__main__":
    main()
