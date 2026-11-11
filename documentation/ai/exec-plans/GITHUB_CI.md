# GitHub CI and local deployment

## What GitHub CI does

The workflow now invokes the shared `scripts/codex/checks.py` jobs for preflight, contracts, isolated website/API tests, TypeScript, production builds and strict HTTP checks. It provisions CI-only read-only PostgreSQL/MinIO identities with `mcp-setup --no-config`, verifies the actual MCP protocol and write denials, and uploads redacted `logs/codex/` execution summaries plus category-specific `logs/tests/` evidence. No local Codex configuration or model SDK/paid AI call is needed on the runner.

GitHub CI is temporarily manual-only (`workflow_dispatch` in `.github/workflows/ci.yml`) while the visual redesign lands. Re-enable `push` to `main` and `pull_request` triggers when that work is ready to validate remotely. When enabled, the workflow:

1. Checks out Asante.
2. Sets up Python.
3. Creates a CI `.env` from `.env.example` without real secrets.
4. Validates Docker Compose.
5. Runs repository unit, functional, integration, and route tests.
6. Builds the Asante API, website, and dashboard images.
7. Starts PostgreSQL, MinIO, the Asante API, the Asante websites, and the Nginx proxy.
8. Checks the public Asante URLs and API health route.
9. Runs the API, website, and dashboard tests inside their containers.
10. Tears down the stack, including CI volumes.

## GitHub setup

1. Create the GitHub repository and push the Asante `main` branch.
2. GitHub automatically discovers `.github/workflows/ci.yml`.
3. Open the repository's **Actions** tab and confirm the workflow runs.
4. In **Settings → Branches**, add a branch protection rule for `main`.
5. Require pull requests and require the `validate` status check before merging.
6. Keep `contents: read` as the default workflow permission unless a later deployment job needs more.

### GitLab-to-GitHub translation

- `.gitlab-ci.yml` becomes one or more YAML files under `.github/workflows/`.
- A GitLab stage/job becomes a GitHub Actions job or step.
- GitLab CI variables become **Settings → Secrets and variables → Actions** values.
- Merge-request pipelines become the `pull_request` trigger; branch pipelines become `push` triggers.
- Protected branches become GitHub branch protection rules, with the `validate` check required before merge.

The current CI workflow does not need external API keys because it uses fixtures and local infrastructure. It generates CI-only local account passwords and verifies sign-in, owner isolation and sign-out through the public proxy URLs. Add GitHub Actions secrets only when an Asante integration test or deployment requires them. Never commit `.env` or real keys.

## Local running

The contributor portal and internal dashboard use local email/password accounts. After migrations and catalogue seeding, run `python scripts/asante/accounts.py` from the activated `asante-codex` environment. It creates four contributor accounts (demo, nomsa, thabo, amina at `asante.test`) and `reviewer@asante.test`; passwords are generated into ignored `.env.asante-test-accounts`, never committed or printed into CI logs. Rerunning preserves them. Use a contributor at `/asante/portal/` and the reviewer at `/asante/review/`. The former shared reviewer key no longer grants access. Use separate normal/incognito windows for simultaneous role testing.

From the Asante repository root:

```bash
docker compose --env-file .env -f infrastructure/docker-compose.yml up -d --build
```

Useful checks:

```bash
docker compose --env-file .env -f infrastructure/docker-compose.yml ps
docker compose --env-file .env -f infrastructure/docker-compose.yml logs -f proxy asante dashboard
docker compose --env-file .env -f infrastructure/docker-compose.yml down
```

Use these URLs:

- `http://localhost/asante/` map
- `http://localhost/asante/portal/` contributor portal
- `http://localhost/asante/review/` Asante approval dashboard

The Asante Nginx proxy forwards requests to the internal website containers. Its `/asante`, `/asante/portal`, `/asante/review` and `/asante/api` path routing remains enabled in both modes; the internal website ports are not user-facing.

### Local reverse-proxy mode

When another local reverse proxy owns laptop port `80`, set `ASANTE_HTTP_PORT=8082` in the ignored Asante `.env`. Add a custom location at `/asante` on the `localhost` proxy host: forward with HTTP to `host.docker.internal` on port `8082`, preserve the original request URI, and enable websocket forwarding. Keep its existing root and other custom locations unchanged. Use `http://localhost/asante/`, `http://localhost/asante/portal/`, and `http://localhost/asante/review/` as the clean URLs. Port `8082` is only the host-side upstream for Asante's own proxy; the app's clean paths stay enabled.

### Standalone and live-demo mode

Set `ASANTE_HTTP_PORT=80` in `.env` and start Asante's proxy directly on port `80`. Ensure the local reverse proxy is stopped or assigned a different host port first. To switch back to laptop reverse-proxy mode, change the ignored local value to `8082` and restart only the Asante `proxy` service. Do not change the public `.env.example` default; it remains suitable for standalone/demo use.

After starting the stack, apply the migration and catalogue/media seed commands in BOOTSTRAP_PROMPT.md. The sample playback MP3 remains a versioned asset and `python -m app.db.seed_media` copies it into private MinIO without overwriting existing media. The API resolves normal same-origin playback URLs through PostgreSQL and streams MinIO bytes. Contributor uploads now use expiring owner-scoped API intents with server verification and private MinIO storage. Profiles/drafts and submission/review records persist in PostgreSQL. Verify `/asante/api/health/ready` before testing playback.

## Deployment boundary

CI and deployment are separate concerns. The current workflow proves that Asante builds and runs on a clean GitHub runner. A deployment job should be added only after choosing a target such as a VPS, a container platform, or a cloud service. That job will need a deployment environment, secrets, a registry strategy, health checks, rollback behavior, and HTTPS configuration.
