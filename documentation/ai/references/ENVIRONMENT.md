# Asante environment setup

## Environment variable ownership

- `ASANTE_*` variables belong to Asante.
- `ASANTE_AI_API_KEY`, `ASANTE_AI_BASE_URL`, `ASANTE_AI_MODEL`, and `ASANTE_AI_PROVIDER` configure optional cloud AI workers (Gemini or OpenAI-compatible). `OPENAI_API_KEY` remains a fallback. On live with `ASANTE_AI_BACKEND=modal`, text/vision/transcription go through Modal instead of these cloud keys.
- Localhost Ollama: leave `ASANTE_AI_BACKEND` empty and set `ASANTE_OLLAMA_BASE_URL` / `ASANTE_OLLAMA_MODEL` (optional `ASANTE_OLLAMA_VISION_MODEL`).
- Live Modal: set `ASANTE_AI_BACKEND=modal`, `ASANTE_MODAL_BASE_URL` (deployed ASGI URL), and `ASANTE_MODAL_SHARED_SECRET` (same value as Modal secret `asante-modal-auth`). Set `ASANTE_MODAL_WHISPER_MODEL` to a Modal/Hugging Face model name such as `tiny`; do not reuse a localhost `ASANTE_WHISPER_MODEL` filesystem path. `ASANTE_MODAL_TRANSCRIBE_TIMEOUT` defaults to 240 seconds to allow GPU/model cold start. Deploy the app from `app/services/ai/modal/asante_ollama_app.py`.
- Modal **account** CLI token (`MODAL_TOKEN_ID` / `MODAL_TOKEN_SECRET`, profile e.g. `vmafunisa`) is for operator deploy (`modal deploy` / `modal token set`) only. Keep it in the **system shell env** (`~/.zshrc` / live `/root/.bashrc`) and `~/.modal.toml`. Never put it in the Asante git tree, `.env.example`, or a committed file. Do not inject it into the API/`job-worker` containers; those use `ASANTE_MODAL_SHARED_SECRET` against the deployed Modal HTTP app.
- Live caption spend caps: `ASANTE_LIVE_CAPTION_SECONDS` (default 45), `ASANTE_LIVE_TRANSLATE_MAX_CUES` (default 12), `ASANTE_LIVE_TRANSLATE_BATCH_SIZE` (default 3), `ASANTE_LIVE_TRANSLATE_DEADLINE_SECONDS` (default 45). Localhost uses `ASANTE_CAPTION_SECONDS` / `ASANTE_TRANSLATE_*` (defaults 180s / 100 cues) unless overridden. Implemented in `asante_api/ai/caption_limits.py`.
- After changing live AI/cap env values, recreate `api` and `job-worker` so both processes see the new settings.
- Codex configuration and Codex secrets remain outside the Asante application environment.
- The generated ignored root `.env.codex` holds only dedicated Codex read-only PostgreSQL/MinIO credentials. It is separate from the application `.env` and existing shell keys; see CODEX_MCP.md. Do not copy it into an application image or source it globally. Do not put Modal tokens or `ASANTE_MODAL_SHARED_SECRET` in git.

## macOS and Linux

Asante Compose **does not** read ports/passwords from a committed file or from hardcoded Compose defaults. Export them in the host shell profile, then start with `scripts/asante/compose.sh` (no `--env-file`).

- Localhost: `~/.zshrc` (and optionally `~/.zprofile`)
- Live: `/root/.bashrc` (and/or `/root/.profile`)
- Real Postgres/MinIO publish on `ASANTE_BIND_HOST` (use `127.0.0.1`)
- HTTP publish host is `ASANTE_BIND_HTTP_HOST`: localhost `127.0.0.1`; live HubTweak edge uses `http://172.17.0.1:18082` (or the live profile port), so live sets `ASANTE_BIND_HTTP_HOST=172.17.0.1` (not the public NIC). Drop eth0 access to the Asante HTTP publish port and private DB ports with iptables as a second layer.
- Scanner decoys are **not** part of Asante. They live in a separate HaMafunisa Honeypot project and must not be synced with the Asante repo.
- Cloudflare (optional): orange-cloud the **website** hostname for HTTP/S only. Do **not** put Postgres/MinIO/decoy TCP through normal Cloudflare proxy; that needs Spectrum (paid) and is unnecessary when DB is loopback-bound.

For a shell session:

```bash
source ~/.zshrc
./scripts/asante/compose.sh up -d
```

### Codex host scripts and checks

The Asante repository uses a small Conda environment for host-side Python scripts. It contains Python 3.12 only; the scripts use the standard library and Docker for service-specific dependencies. It is separate from both Anaconda `base` and the Asante API container. The API keeps its own pinned requirements in `app/services/api/requirements.txt` and runs on Python 3.12 inside Docker.

Create and activate the project environment once:

```bash
conda env create --file scripts/codex/environment.yml
conda activate asante-codex
python --version
```

The version should report Python 3.12. Run host checks with that activated `python`, for example `python scripts/codex/checks.py contracts`. If you don't want to activate a shell, use `conda run -n asante-codex python scripts/codex/checks.py contracts`. The runner rejects other local environments rather than silently switching to system Python or Anaconda `base`. GitHub Actions uses its pinned Python 3.12 runner instead.

The local development variables are documented in the Asante `.env.example`. If shell variables are unavailable, copy `.env.example` to `.env` and populate the required values.

## Windows PowerShell

From an initialized Conda PowerShell or Anaconda Prompt, create and activate the same project environment:

```powershell
conda env create --file scripts/codex/environment.yml
conda activate asante-codex
python --version
```

Use `python scripts/codex/checks.py <job>` while the environment is active, or `conda run -n asante-codex python scripts/codex/checks.py <job>` without activation.

Set variables for the current PowerShell session:

```powershell
$env:ASANTE_POSTGRES_DB = "asante"
$env:ASANTE_POSTGRES_USER = "asante"
$env:ASANTE_POSTGRES_PASSWORD = "asante_local_dev_only"
$env:ASANTE_POSTGRES_PORT = "5432"
$env:ASANTE_MINIO_ROOT_USER = "asante"
$env:ASANTE_MINIO_ROOT_PASSWORD = "asante_minio_local_dev_only"
$env:ASANTE_MINIO_API_PORT = "9000"
$env:ASANTE_MINIO_CONSOLE_PORT = "9001"
```

For a persistent user-level variable, use PowerShell's `[Environment]::SetEnvironmentVariable` with a value supplied by the developer. Do not commit credentials.

## `.env` fallback

The repository contains `.env.example` as the template and an ignored local `.env` fallback for the current developer environment. Never commit real API keys. CI and deployment environments should provide secrets through their secret store.

## Docker

Codex project inspection uses the optional `codex` Compose profile. The launcher runs a one-off container with only its reader credentials mounted; it does not start with the normal application stack. Host execution scripts need Python 3.11+ and Docker/Compose. Their launcher detects an available newer Python when the system `python3` is older.

Docker Compose reads `ASANTE_*` variables. Start the infrastructure with:

```bash
docker compose --env-file .env -f infrastructure/docker-compose.yml up -d
```

The local MinIO API is available at `http://localhost:9000` and its console is available at `http://localhost:9001`.
