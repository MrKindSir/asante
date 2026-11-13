#!/usr/bin/env bash
# Build production TestData packages locally, stream to the VPS over SSH (no git),
# upload to MinIO, update story rows, then force caption backfill.
#
# Usage (from repo root, SSH alias hubtweak-vps1):
#   bash scripts/asante/push_live_production_media.sh
#   bash scripts/asante/push_live_production_media.sh /Users/vavu/Downloads/TestData/production

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SOURCE="${1:-${ASANTE_TESTDATA_PRODUCTION:-$HOME/Downloads/TestData/production}}"
PACKAGE_ROOT="${ASANTE_MEDIA_PACKAGE_ROOT:-$ROOT/.tmp/live_media_packages}"
REMOTE_HOST="${ASANTE_LIVE_SSH:-hubtweak-vps1}"
REMOTE_REPO="${ASANTE_LIVE_REPO:-/root/Asante}"
REMOTE_PACKAGES="${ASANTE_LIVE_PACKAGE_ROOT:-/tmp/asante-live-media}"
API_CONTAINER="${ASANTE_LIVE_API_CONTAINER:-asante-api-1}"
TGZ="${PACKAGE_ROOT}.tgz"

if [[ ! -d "$SOURCE" ]]; then
  echo "Missing production clips: $SOURCE" >&2
  exit 1
fi

echo "==> Building packages from $SOURCE"
python3 "$ROOT/scripts/asante/sync_live_production_media.py" \
  --source "$SOURCE" \
  --package-root "$PACKAGE_ROOT" \
  --build

echo "==> Packing $PACKAGE_ROOT"
tar -C "$PACKAGE_ROOT" -czf "$TGZ" .

echo "==> Streaming packages + scripts to $REMOTE_HOST over SSH (no git)"
ssh -o BatchMode=yes "$REMOTE_HOST" "rm -rf '$REMOTE_PACKAGES' && mkdir -p '$REMOTE_PACKAGES' '$REMOTE_REPO/scripts/asante' '$REMOTE_REPO/app/services/api/asante_api/ai'"
ssh -o BatchMode=yes "$REMOTE_HOST" "cat > /tmp/asante-live-media.tgz" < "$TGZ"
ssh -o BatchMode=yes "$REMOTE_HOST" "tar -C '$REMOTE_PACKAGES' -xzf /tmp/asante-live-media.tgz"
ssh -o BatchMode=yes "$REMOTE_HOST" "cat > '$REMOTE_REPO/scripts/asante/sync_live_production_media.py'" < "$ROOT/scripts/asante/sync_live_production_media.py"
ssh -o BatchMode=yes "$REMOTE_HOST" "cat > '$REMOTE_REPO/app/services/api/asante_api/ai/backfill_published_captions.py'" < "$ROOT/app/services/api/asante_api/ai/backfill_published_captions.py"

echo "==> Injecting into running API container $API_CONTAINER"
ssh -o BatchMode=yes "$REMOTE_HOST" "set -e
  docker cp '$REMOTE_PACKAGES' '$API_CONTAINER:/tmp/asante-live-media'
  docker cp '$REMOTE_REPO/scripts/asante/sync_live_production_media.py' '$API_CONTAINER:/tmp/sync_live_production_media.py'
  docker cp '$REMOTE_REPO/app/services/api/asante_api/ai/backfill_published_captions.py' '$API_CONTAINER:/workspace/asante_api/ai/backfill_published_captions.py'
"

echo "==> Uploading to MinIO and updating story rows"
ssh -o BatchMode=yes "$REMOTE_HOST" "cd '$REMOTE_REPO' && \
  docker compose --env-file .env -f infrastructure/docker-compose.yml exec -T \
    -e PYTHONPATH=/workspace \
    -e ASANTE_MEDIA_PACKAGE_ROOT=/tmp/asante-live-media \
    api python /tmp/sync_live_production_media.py --apply --prune-old-prefixes --verify"

SLUGS="testdata-ethiopia,testdata-idi-amin,testdata-africa-civilizations,testdata-snake-wedding,testdata-folktale,story-001,story-002,story-003,story-demo"
echo "==> Force caption / translation backfill for: $SLUGS"
ssh -o BatchMode=yes "$REMOTE_HOST" "cd '$REMOTE_REPO' && \
  docker compose --env-file .env -f infrastructure/docker-compose.yml exec -T \
    -e PYTHONPATH=/workspace \
    -e PYTHONUNBUFFERED=1 \
    api python -m asante_api.ai.backfill_published_captions --force --slugs '$SLUGS'"

echo "==> Smoke HLS + media endpoints"
ssh -o BatchMode=yes "$REMOTE_HOST" 'set -e
  for slug in testdata-idi-amin story-002 story-001 story-demo; do
    id=$(docker exec asante-postgres-1 psql -U asante -d asante -Atc "SELECT id FROM asante.stories WHERE slug='"'"'"$slug"'"'"'")
    code=$(curl -skS -o /tmp/hls-$slug.out -w "%{http_code}" --resolve asante.terminalcursor.com:443:127.0.0.1 \
      "https://asante.terminalcursor.com/asante/api/v1/stories/$id/hls/index.m3u8" || true)
    media=$(curl -skS -o /dev/null -w "%{http_code}" --resolve asante.terminalcursor.com:443:127.0.0.1 \
      "https://asante.terminalcursor.com/asante/api/v1/stories/$id/media" || true)
    echo "$slug id=$id hls=$code media=$media"
  done
  docker exec asante-postgres-1 psql -U asante -d asante -c \
    "SELECT slug, media_format, media_file, left(media_file,60) AS media, length(transcript) AS transcript_chars, jsonb_array_length(COALESCE(caption_tracks->'"'"'tracks'"'"', '"'"'[]'"'"'::jsonb)) AS tracks FROM asante.stories WHERE active ORDER BY slug;"
'

echo "==> Done"
