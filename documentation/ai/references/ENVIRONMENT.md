# Asante environment setup

## Environment variable ownership

- `ASANTE_*` variables belong to Asante.
- `ASANTE_AI_API_KEY`, `ASANTE_AI_BASE_URL`, `ASANTE_AI_MODEL`, and `ASANTE_AI_PROVIDER` configure Asante AI workers (Gemini or OpenAI-compatible). `OPENAI_API_KEY` remains a fallback.
- Codex configuration and Codex secrets remain outside the Asante application environment.
- The generated ignored root `.env.codex` holds only dedicated Codex read-only PostgreSQL/MinIO credentials. It is separate from the application `.env` and existing shell keys; see CODEX_MCP.md. Do not copy it into an application image or source it globally.

## macOS and Linux

For a shell session, load the Asante variables from `.zshrc` or `.bashrc`:

```bash
source ~/.zshrc
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
