"""Portable allowlisted execution checks and Codex MCP setup for Asante."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from queue import Queue, Empty
import secrets
import shutil
import subprocess
import sys
import time
from threading import Thread

def python_environment_error(version: tuple[int, ...], prefix: str, ci: bool) -> str | None:
    if version < (3, 11):
        return "Asante Codex scripts require Python 3.11+. Create and use the asante-codex Conda environment."
    if ci:
        return None
    if Path(prefix).name != "asante-codex":
        return "Use the project Conda environment: conda activate asante-codex (Python 3.12)."
    return None


runtime_error = python_environment_error(
    sys.version_info,
    sys.prefix,
    os.environ.get("CI", "").lower() == "true",
)
if runtime_error:
    raise SystemExit(runtime_error)

import tomllib  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.codex.settings import (  # noqa: E402
    COMPOSE, ROOT, SECRET_KEYS, SERVER_NAME, TOOLS, app_values, read_values,
)

SERVICES = {"website": "asante", "dashboard": "dashboard", "api": "api"}
TEST_CHECK_CATEGORIES = {
    "repository-contracts": ("unit", "functional"),
    "asante-check-1": ("unit",),
    "dashboard-check-1": ("unit",),
    "api-check-1": ("unit", "functional"),
    "api-check-2": ("integration",),
    "live-http-and-services": ("e2e", "integration"),
    "negative-permission-tests": ("integration",),
    "mcp-protocol-integration": ("integration",),
    "mcp-project-launcher": ("integration",),
}
JOBS = ("preflight", "contracts", "website", "dashboard", "api", "http", "all",
        "mcp-setup", "mcp-verify", "mcp-serve")


def compose(*args: str) -> list[str]:
    return [*COMPOSE, *args]


def tool_run(*args: str) -> list[str]:
    uid = getattr(os, "getuid", lambda: 0)()
    gid = getattr(os, "getgid", lambda: 0)()
    return compose("--profile", "codex", "run", "--rm", "--no-deps", "-T",
                   "--user", f"{uid}:{gid}", "codex-mcp", *args)


def service_checks(service: str) -> list[list[str]]:
    if service not in SERVICES.values():
        raise ValueError("Unknown Asante service")
    prefix = compose("run", "--rm", "--no-deps", "-T")
    if service == "api":
        return [
            [*prefix, service, "python", "-m", "unittest",
             "tests.unit.test_api", "tests.unit.test_story_packet", "tests.unit.test_plan_documents", "tests.unit.test_workers", "tests.unit.test_heritage_gate", "tests.unit.test_assessment", "tests.functional.test_api_routes", "-v"],
            [*prefix, service, "python", "-m", "unittest",
             "tests.integration.test_database_migrations", "tests.integration.test_workspace_persistence", "-v"],
        ]
    return [
        [*prefix, service, "npm", "test", "--", "--run"],
        [*prefix, service, "npx", "--no-install", "tsc", "--noEmit"],
        [*prefix, "-e", "NODE_ENV=production", service, "npm", "run", "build"],
    ]


class Runner:
    def __init__(self) -> None:
        self.results: list[dict] = []
        self.sensitive = [value for name, value in app_values().items() if "PASSWORD" in name]
        self.sensitive += [
            value for name, value in read_values(ROOT / ".env.codex", SECRET_KEYS).items()
            if "PASSWORD" in name or "SECRET" in name
        ]

    def redact(self, text: str) -> str:
        for value in self.sensitive:
            if value:
                text = text.replace(value, "[REDACTED]")
        return text

    def run(self, name: str, command: list[str], *, stdin: str | None = None,
            env: dict[str, str] | None = None, timeout: int = 600) -> str:
        started = time.monotonic()
        try:
            result = subprocess.run(
                command, cwd=ROOT, input=stdin, text=True, capture_output=True,
                env={**os.environ, **(env or {})}, timeout=timeout, check=False,
            )
            code = result.returncode
            output = result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            code, output = 124, "Execution check timed out."
        except FileNotFoundError:
            code, output = 127, "Required executable is unavailable."
        output = self.redact(output)
        self.results.append({
            "check": name, "command": command, "exitCode": code,
            "seconds": round(time.monotonic() - started, 2), "output": output[-30000:],
        })
        print(f"{'PASS' if code == 0 else 'FAIL'} {name}", flush=True)
        if output:
            print(output[-6000:], end="" if output.endswith("\n") else "\n", flush=True)
        if code:
            raise RuntimeError(f"Execution check failed: {name}")
        return result.stdout

    def report(self, success: bool, job: str) -> Path:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        directory = ROOT / "logs" / "codex"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / ("execution-" + stamp + ".json")
        payload = {
            "owner": "Codex", "project": "Asante", "job": job,
            "passed": success, "checks": self.results,
        }
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        categorized: dict[str, list[dict]] = {}
        for check in self.results:
            for category in TEST_CHECK_CATEGORIES.get(check["check"], ()):
                categorized.setdefault(category, []).append(check)
        for category, checks in categorized.items():
            test_directory = ROOT / "logs" / "tests" / category
            test_directory.mkdir(parents=True, exist_ok=True)
            test_payload = {
                "owner": "Asante and Codex test execution",
                "project": "Asante", "job": job, "category": category,
                "passed": all(check["exitCode"] == 0 for check in checks),
                "executionReport": str(path.relative_to(ROOT)),
                "checks": checks,
            }
            test_path = test_directory / ("test-run-" + stamp + ".json")
            test_path.write_text(json.dumps(test_payload, indent=2) + "\n", encoding="utf-8")
        return path


def preflight(runner: Runner) -> None:
    for name in ("AGENTS.md", "documentation/ai/exec-plans/PLANS.md", ".env"):
        if not (ROOT / name).is_file():
            raise RuntimeError("Required Asante setup file is missing: " + name)
    runner.run("compose-validation", compose("config", "--quiet"), timeout=30)
    runner.run("docker-ready", ["docker", "info", "--format", "{{.ServerVersion}}"], timeout=30)
    runner.run("services", compose("ps"), timeout=30)
    if (ROOT / ".git").exists():
        runner.run("git-working-tree", ["git", "status", "--short"], timeout=15)
    else:
        print("INFO Git is not initialized; no Git changes made.", flush=True)


def credentials() -> tuple[dict[str, str], bool]:
    path = ROOT / ".env.codex"
    if path.is_symlink():
        raise RuntimeError("Refusing a symlink for Codex credential storage")
    existing = path.exists()
    if existing:
        values = read_values(path, SECRET_KEYS)
        if SECRET_KEYS - values.keys():
            raise RuntimeError("Existing .env.codex is incomplete; preserve and repair it explicitly")
        os.chmod(path, 0o600)
        return values, True
    app = app_values()
    bucket = app["ASANTE_MINIO_BUCKETS"].split(",")[0].strip()
    if not bucket:
        raise RuntimeError("An Asante development media bucket is required")
    values = {
        "CODEX_ASANTE_POSTGRES_DB": app["ASANTE_POSTGRES_DB"],
        "CODEX_ASANTE_POSTGRES_PASSWORD": secrets.token_hex(32),
        "CODEX_ASANTE_MINIO_ACCESS_KEY": "codex-asante-reader",
        "CODEX_ASANTE_MINIO_SECRET_KEY": secrets.token_hex(32),
        "CODEX_ASANTE_MINIO_BUCKET": bucket,
    }
    content = "# Generated Codex-only read-only credentials. Never commit.\n"
    content += "".join(f"{key}={value}\n" for key, value in values.items())
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(content)
    return values, False


def append_config(path: Path, block: str, backup: Path) -> None:
    if path.is_symlink():
        raise RuntimeError("Refusing to edit a symlinked Codex configuration")
    original = path.read_text(encoding="utf-8") if path.exists() else ""
    proposed = original.rstrip() + "\n\n" + block + "\n"
    tomllib.loads(proposed)
    if path.exists():
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup)
        os.chmod(backup, 0o600)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(proposed, encoding="utf-8")


def install_project_config() -> None:
    project = ROOT / ".codex" / "config.toml"
    user_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    user = user_home / "config.toml"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = ROOT / ".codex-backup" / (stamp + "-asante-mcp")
    desired = {
        "command": sys.executable, "args": [str(ROOT / "scripts/codex/checks.py"), "mcp-serve"],
        "cwd": str(ROOT), "enabled": True,
        "enabled_tools": TOOLS, "startup_timeout_sec": 60, "tool_timeout_sec": 30,
    }
    existing = tomllib.loads(project.read_text()) if project.exists() else {}
    entry = existing.get("mcp_servers", {}).get(SERVER_NAME)
    if entry is not None and entry != desired:
        raise RuntimeError("Existing Asante MCP configuration differs; no unrelated configuration was overwritten")
    user_config = tomllib.loads(user.read_text()) if user.exists() else {}
    trust = user_config.get("projects", {}).get(str(ROOT), {})
    if trust and trust.get("trust_level") != "trusted":
        raise RuntimeError("Asante has an explicit untrusted setting; trust it in Codex before configuring")
    if not trust:
        block = "[projects." + json.dumps(str(ROOT)) + ']\ntrust_level = "trusted"'
        append_config(user, block, backup / "user-config.toml")
        print("Configured trust for this Asante repository only; previous user config backed up.")
    if entry is None:
        lines = ["[mcp_servers." + SERVER_NAME + "]"]
        lines.extend(key + " = " + json.dumps(value) for key, value in desired.items())
        append_config(project, "\n".join(lines), backup / "project-config.toml")
    print("Configured project Codex MCP; existing global documentation server retained.")


def mcp_setup(runner: Runner, no_config: bool) -> None:
    _, existing = credentials()
    runner.sensitive += [
        value for name, value in read_values(ROOT / ".env.codex", SECRET_KEYS).items()
        if "PASSWORD" in name or "SECRET" in name
    ]
    runner.run("build-codex-tools", compose("--profile", "codex", "build", "codex-mcp"))
    payload = {"action": "setup", "app": app_values(), "existingCredentials": existing}
    runner.run("provision-and-verify-readonly", tool_run(
        "python", "-m", "scripts.codex.provision",
    ), stdin=json.dumps(payload))
    if not no_config:
        install_project_config()
        runner.run("codex-mcp-registration", ["codex", "mcp", "list"], timeout=30)


def mcp_verify(runner: Runner) -> None:
    payload = {"action": "verify", "app": app_values()}
    runner.run("negative-permission-tests", tool_run(
        "python", "-m", "scripts.codex.provision",
    ), stdin=json.dumps(payload))
    runner.run("mcp-protocol-integration", tool_run(
        "python", "-m", "unittest", "tests.integration.test_codex_mcp", "-v",
    ))
    verify_launcher(runner)


def verify_launcher(runner: Runner) -> None:
    """Exercise the exact host → Docker → stdio path recorded in Codex config."""
    command = [sys.executable, str(ROOT / "scripts/codex/checks.py"), "mcp-serve"]
    started = time.monotonic()
    process = subprocess.Popen(
        command, cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, bufsize=1,
    )
    replies: Queue = Queue()
    diagnostics: list[str] = []
    def read_stdout() -> None:
        for line in process.stdout:
            replies.put(line)
        replies.put(None)
    def read_stderr() -> None:
        for line in process.stderr:
            diagnostics.append(line)
            if len(diagnostics) > 100:
                diagnostics.pop(0)
    Thread(target=read_stdout, daemon=True).start()
    Thread(target=read_stderr, daemon=True).start()
    def send(message: dict) -> None:
        process.stdin.write(json.dumps(message) + "\n")
        process.stdin.flush()
    def request(identifier: int, method: str, parameters: dict) -> dict:
        send({"jsonrpc": "2.0", "id": identifier, "method": method, "params": parameters})
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                line = replies.get(timeout=max(0.01, deadline - time.monotonic()))
            except Empty as error:
                raise RuntimeError("Codex MCP launcher response timed out") from error
            if line is None:
                raise RuntimeError("Codex MCP launcher exited before responding")
            response = json.loads(line)
            if response.get("id") == identifier:
                if "error" in response:
                    raise RuntimeError("Codex MCP launcher returned a protocol error")
                return response["result"]
        raise RuntimeError("Codex MCP launcher timed out")
    success = False
    try:
        request(1, "initialize", {
            "protocolVersion": "2025-03-26", "capabilities": {},
            "clientInfo": {"name": "codex-asante-execution-check", "version": "1.0"},
        })
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        listing = request(2, "tools/list", {})
        if {tool["name"] for tool in listing["tools"]} != set(TOOLS):
            raise RuntimeError("Unexpected tools in Codex project launcher")
        for identifier, name in [(3, TOOLS[0]), (4, "codex_asante_minio_status")]:
            result = request(identifier, "tools/call", {"name": name, "arguments": {}})
            if result.get("isError"):
                raise RuntimeError("Codex project launcher could not authenticate a read")
        success = True
        print("PASS mcp-project-launcher: initialized, exact read-only tools, PostgreSQL and MinIO reads")
    finally:
        process.stdin.close()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=5)
        runner.results.append({
            "check": "mcp-project-launcher", "command": command,
            "exitCode": 0 if success else 1,
            "seconds": round(time.monotonic() - started, 2),
            "output": "Authenticated read-only stdio handshake passed." if success
            else runner.redact("".join(diagnostics)[-4000:]),
        })


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job", choices=JOBS)
    parser.add_argument("--no-config", action="store_true", help="CI: do not edit local Codex settings")
    parser.add_argument("--skip-build", action="store_true", help="Use only when the affected images were just built")
    args = parser.parse_args()
    if args.job == "mcp-serve":
        # Raw stdin/stdout belong to the MCP protocol. No banners, reports or admin credentials.
        return subprocess.call(tool_run(), cwd=ROOT)
    runner = Runner()
    success = False
    try:
        if args.job in {"preflight", "all"}:
            preflight(runner)
        if args.job in {"contracts", "all"}:
            runner.run("repository-contracts", [
                sys.executable, "-m", "unittest", "tests.unit.test_repository_contract",
                "tests.functional.test_compose_contract", "tests.unit.test_codex_checks", "-v",
            ])
        for job, service in SERVICES.items():
            if args.job in {job, "all"}:
                if not args.skip_build:
                    runner.run("build-" + service, compose("build", service))
                for index, command in enumerate(service_checks(service), 1):
                    runner.run(f"{service}-check-{index}", command)
        if args.job in {"http", "all"}:
            port = app_values()["ASANTE_HTTP_PORT"]
            base = os.environ.get("ASANTE_BASE_URL", "http://localhost" + (":" + port if port != "80" else ""))
            runner.run("live-http-and-services", [
                sys.executable, "-m", "unittest", "tests.e2e.test_api_routes",
                "tests.e2e.test_web_routes", "tests.e2e.test_accounts", "tests.integration.test_running_services", "-v",
            ], env={"ASANTE_REQUIRE_SERVICES": "1", "ASANTE_BASE_URL": base})
        if args.job == "mcp-setup":
            mcp_setup(runner, args.no_config)
        elif args.job == "mcp-verify":
            mcp_verify(runner)
        success = True
        return 0
    except (RuntimeError, ValueError, OSError) as error:
        print(runner.redact(str(error)), file=sys.stderr)
        return 1
    finally:
        report = runner.report(success, args.job)
        print("Codex execution report: " + str(report))


if __name__ == "__main__":
    raise SystemExit(main())
