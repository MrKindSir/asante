#!/usr/bin/env bash
# Deploy Asante live Ollama/Whisper tools to Modal.
# Does not change localhost AI. Requires Modal credentials in the environment
# (or an already-activated modal profile). Never commit token values.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

if [[ -z "${ASANTE_MODAL_SHARED_SECRET:-}" ]]; then
  ASANTE_MODAL_SHARED_SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
  echo "Generated ASANTE_MODAL_SHARED_SECRET (save this for live VPS .env)."
fi

echo "Creating/updating Modal secret asante-modal-auth..."
python3 -m modal secret create asante-modal-auth \
  "ASANTE_MODAL_SHARED_SECRET=${ASANTE_MODAL_SHARED_SECRET}" \
  --force

echo "Deploying Asante Modal Ollama app..."
python3 -m modal deploy app/services/ai/modal/asante_ollama_app.py

cat <<EOF

Next (live VPS Asante only — not HubTweak):
  ASANTE_AI_BACKEND=modal
  ASANTE_MODAL_BASE_URL=<printed https://...modal.run URL from deploy>
  ASANTE_MODAL_SHARED_SECRET=${ASANTE_MODAL_SHARED_SECRET}
  ASANTE_MODAL_WHISPER_MODEL=tiny
  ASANTE_OLLAMA_MODEL=llama3.2:3b
Leave ASANTE_AI_BACKEND empty on localhost.
EOF
