"""Shared, dependency-free configuration for Codex development tools."""

from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ["docker", "compose", "--env-file", ".env", "-f", "infrastructure/docker-compose.yml"]
READER_ROLE = "codex_asante_reader"
INSPECTION_SCHEMA = "codex_asante_inspection"
SERVER_NAME = "codex_asante_readonly"
TOOLS = [
    "codex_asante_db_status",
    "codex_asante_db_tables",
    "codex_asante_db_table_info",
    "codex_asante_db_spatial_reference",
    "codex_asante_minio_status",
    "codex_asante_minio_objects",
    "codex_asante_minio_object_info",
]
APP_KEYS = {
    "ASANTE_POSTGRES_DB", "ASANTE_POSTGRES_USER", "ASANTE_POSTGRES_PASSWORD",
    "ASANTE_POSTGRES_PORT", "ASANTE_MINIO_ROOT_USER", "ASANTE_MINIO_ROOT_PASSWORD",
    "ASANTE_MINIO_BUCKETS", "ASANTE_HTTP_PORT",
}
SECRET_KEYS = {
    "CODEX_ASANTE_POSTGRES_DB", "CODEX_ASANTE_POSTGRES_PASSWORD",
    "CODEX_ASANTE_MINIO_ACCESS_KEY", "CODEX_ASANTE_MINIO_SECRET_KEY",
    "CODEX_ASANTE_MINIO_BUCKET",
}


def read_values(path: Path, allowed: set[str]) -> dict[str, str]:
    """Read literal dotenv values; never source or execute a shell file."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, separator, value = line.removeprefix("export ").partition("=")
        name = name.strip()
        if not separator or name not in allowed:
            continue
        value = value.strip()
        single_quoted = value.startswith("'")
        if value.startswith(("'", '"')):
            if len(value) < 2 or value[-1] != value[0]:
                raise ValueError("Unterminated value in environment file")
            value = value[1:-1]
        else:
            value = value.split(" #", 1)[0].rstrip()
        if not single_quoted and ("$" in value or "`" in value):
            raise ValueError("Codex configuration requires literal values, not shell expressions")
        values[name] = value
    return values


def app_values() -> dict[str, str]:
    values = {
        "ASANTE_POSTGRES_DB": "asante", "ASANTE_POSTGRES_USER": "asante",
        "ASANTE_POSTGRES_PASSWORD": "asante_local_dev_only",
        "ASANTE_MINIO_ROOT_USER": "asante",
        "ASANTE_MINIO_ROOT_PASSWORD": "asante_minio_local_dev_only",
        "ASANTE_MINIO_BUCKETS": "asante-media", "ASANTE_HTTP_PORT": "80",
    }
    values.update(read_values(ROOT / ".env", APP_KEYS))
    values.update({key: os.environ[key] for key in APP_KEYS if key in os.environ})
    return values


def reader_values() -> dict[str, str]:
    path = Path(os.environ.get("CODEX_ASANTE_ENV_FILE", "/run/secrets/codex-asante.env"))
    values = read_values(path, SECRET_KEYS)
    if SECRET_KEYS - values.keys():
        raise RuntimeError("Codex read-only credentials are missing. Run the documented mcp-setup command.")
    return values


def safe_identifier(value: str) -> str:
    if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]{0,62}", value):
        raise ValueError("Invalid database identifier")
    return value


def safe_limit(value: int) -> int:
    if isinstance(value, bool) or not 1 <= value <= 25:
        raise ValueError("limit must be between 1 and 25")
    return value
