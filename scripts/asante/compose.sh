#!/usr/bin/env bash
# Run Asante Compose using the current shell environment only (no --env-file).
# Required secrets/ports must already be exported from ~/.zshrc or the live profile.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

required=(
  ASANTE_BIND_HOST
  ASANTE_HTTP_PORT
  ASANTE_POSTGRES_DB
  ASANTE_POSTGRES_USER
  ASANTE_POSTGRES_PASSWORD
  ASANTE_POSTGRES_PORT
  ASANTE_MINIO_ROOT_USER
  ASANTE_MINIO_ROOT_PASSWORD
  ASANTE_MINIO_BUCKETS
  ASANTE_MINIO_API_PORT
  ASANTE_MINIO_CONSOLE_PORT
)

missing=()
for name in "${required[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    missing+=("$name")
  fi
done
if ((${#missing[@]})); then
  echo "Missing required environment values (set them in ~/.zshrc or the live shell profile):" >&2
  printf '  %s\n' "${missing[@]}" >&2
  exit 1
fi

exec docker compose -f infrastructure/docker-compose.yml "$@"
