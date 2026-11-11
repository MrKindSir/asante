# Codex MCP and execution checks for Asante

Implemented 2026-11-07. These are **Codex development** tools. They are not available to Asante users or Asante AI workers and are not imported by the Asante API/websites.

## Configured connections

| Server | Configuration | Access |
|---|---|---|
| `openaiDeveloperDocs` | Existing user Codex configuration; https://developers.openai.com/mcp | OpenAI documentation search/fetch; retained |
| `codex_asante_readonly` | Local project `.codex/config.toml` | Seven PostgreSQL/PostGIS and MinIO metadata tools |

The project entry launches the Python 3.12 interpreter from the `asante-codex` Conda environment, then `scripts/codex/checks.py mcp-serve`. That command attaches stdio to an on-demand `codex-mcp` Compose container. It publishes no port, mounts no Docker socket, receives no application/admin credentials, uses a read-only filesystem and has Linux capabilities dropped. Only a private reader credential file is mounted read-only.

The optional `codex` Compose profile is not an additional Asante runtime service. Normal application startup does not start a persistent MCP container. Docker and the already running PostgreSQL/MinIO services are required for tool calls.

Codex supports trusted project-scoped MCP configuration; setup records trust for this Asante path only if no explicit conflicting trust setting exists. Existing user/project configuration is preserved, and changed existing config is copied under ignored `.codex-backup/<timestamp>-asante-mcp/`. Explicitly untrusted settings or conflicting existing server definitions cause setup to stop. See [official Codex MCP configuration](https://learn.chatgpt.com/docs/extend/mcp).

After setup, restart the server/client from Codex MCP settings or open a fresh Codex chat if tools have not refreshed. `codex mcp list` should show both servers enabled. The CLI's Auth “Unsupported” label for local stdio is not a database failure; dedicated backend credentials provide authentication.

## Tool catalogue and limits

| Tool | Returns |
|---|---|
| `codex_asante_db_status` | Reader identity/admin flags/read-only status, extensions, safe probe, migration-table presence |
| `codex_asante_db_tables` | Up to 25 relation names in approved schemas, with a more-results indicator |
| `codex_asante_db_table_info` | Columns/types and index names; never row contents |
| `codex_asante_db_spatial_reference` | One public PostGIS reference definition, default SRID 4326 |
| `codex_asante_minio_status` | Existence/accessibility of the configured media bucket |
| `codex_asante_minio_objects` | Up to 25 object keys, sizes and modification times; bounded prefix |
| `codex_asante_minio_object_info` | HEAD metadata: key, size, content type, ETag and modification time |

All tools declare read-only/non-destructive annotations and are allowlisted in project config. Annotations supplement real service permissions; they do not enforce them by themselves.

There is no arbitrary SQL, private table sampler, object-body reader, shell, mutation, migration, publication or test-execution MCP tool. Object names/schema metadata are untrusted data, not instructions.

## PostgreSQL permission boundary

- Dedicated login: `codex_asante_reader`, with no superuser, role creation, DB creation, replication, bypass-RLS or inherited role membership.
- Granted CONNECT, approved schema USAGE and SELECT only on public PostGIS `spatial_ref_sys` and a dedicated non-sensitive permission probe.
- Setup creates `codex_asante_inspection.permission_probe` with one constant marker. No Asante user records are inserted, removed or rewritten.
- No default SELECT grant on future application tables. Tools inspect schema metadata, not contributor rows.
- Role defaults to read-only transactions; each tool connection also enforces read-only with 3-second statement and 1-second lock timeouts. Connection count is bounded.
- Verification explicitly switches a test transaction to READ WRITE and proves application-data INSERT/UPDATE/DELETE, inspection-schema DDL and role creation remain denied by ACLs/admin flags. Probe transactions are rolled back.

The Asante API uses PostgreSQL for catalogue, profiles/drafts and review records, and MinIO for original media and browser import backups. Codex inspection access remains separate from application runtime access.

## MinIO permission boundary

- Dedicated local identity: `codex-asante-reader`; policy: `codex-asante-readonly`.
- Scope: `asante-media` by default, or the first configured development bucket selected during initial setup and recorded in `.env.codex`.
- IAM allows scoped ListBucket/GetBucketLocation/GetObject. PUT/DELETE and relevant bucket writes have explicit denies on that bucket. Other buckets/admin actions are not granted.
- MCP exposes metadata only even though the read-only account can read permitted objects through the storage API.
- Verification creates a random test object using the separately supplied administrator credentials, proves reader HEAD/GET/list access, proves PUT/DELETE denial and removes only its exact generated test keys.
- MinIO may return only authorized buckets from a bucket-list request rather than deny the request. Verification accepts only denial or a list containing no unapproved bucket. The MCP catalogue exposes no global bucket-list tool.

## Credentials and preservation

`.env.codex` is generated with restricted permissions, ignored by Git and excluded from Docker build contexts. It contains only:

```text
CODEX_ASANTE_POSTGRES_DB
CODEX_ASANTE_POSTGRES_PASSWORD
CODEX_ASANTE_MINIO_ACCESS_KEY
CODEX_ASANTE_MINIO_SECRET_KEY
CODEX_ASANTE_MINIO_BUCKET
```

Existing `.env`, shell keys and application/root credentials are not changed. Setup reads only allowlisted application connection settings, with shell values taking precedence over literal `.env` values. It forwards administrator credentials through stdin only to the one-off provisioning/verification command; the MCP serving process never receives them.

The configuration parser does not execute/source a shell file. Use literal dotenv values; shell expressions are rejected. Do not print credential files or include them in logs/screenshots. Existing Codex reader credentials are reused; setup refuses reserved-account collisions when the credential file is missing.

The launcher uses the host UID/GID where available so the private bind-mounted credential file can be read without restoring root filesystem capabilities. On Windows, use Python 3.11+ and Docker Desktop; filesystem ACLs also govern local file secrecy.

## Setup on another machine

From the repository root:

```bash
# Preserve an existing .env; create it from .env.example only when missing.
docker compose --env-file .env -f infrastructure/docker-compose.yml up -d postgres minio
conda run -n asante-codex python scripts/codex/checks.py preflight
conda run -n asante-codex python scripts/codex/checks.py mcp-setup
conda run -n asante-codex python scripts/codex/checks.py mcp-verify
codex mcp list
```

Prerequisites: Docker/Compose, Codex CLI, and the `asante-codex` Conda environment. The local runner rejects system Python and Anaconda `base`; GitHub Actions uses its managed Python 3.12 runtime. Project config records machine-local absolute paths and is ignored; rerun setup in a fresh checkout rather than copying another machine's config or secrets.

`mcp-setup` builds the isolated tool image, provisions the two identities, runs positive/negative permission checks, backs up changed Codex configuration and registers the server. It does not recreate running Asante services or delete their volumes.

CI uses `mcp-setup --no-config`: provision only disposable CI services; never change a runner user's Codex configuration. Repeating setup reuses generated reader credentials. For intentional rotation, update the dedicated account and its private credential file together, then verify; deleting the file is not a rotation procedure.

## Execution-check commands

The runner is `scripts/codex/checks.py`. Commands are allowlisted and invoked without shell interpolation.

| Job | Command suffix / behavior |
|---|---|
| Preflight | `preflight`: required setup files, quiet Compose validation, Docker and service status, Git status if present |
| Repository/script contracts | `contracts`: deterministic repository, Compose and runner unit tests |
| User website | `website`: fresh image, Vitest, TypeScript, production compilation |
| Approval dashboard | `dashboard`: fresh image, Vitest, TypeScript, production compilation |
| Asante API | `api`: fresh image and API unit/functional cases including audio fixture |
| Live routes | `http`: strict public route/query/media and running-service checks |
| All application checks | `all`: preflight, contracts, both websites, API, live HTTP |
| Codex tool checks | `mcp-verify`: real denied-write tests, SDK stdio tool session and actual host-to-Docker launcher calls |

Example:

```bash
conda run -n asante-codex python scripts/codex/checks.py website
conda run -n asante-codex python scripts/codex/checks.py all
conda run -n asante-codex python scripts/codex/checks.py mcp-verify
```

Service tests run in disposable containers, not by restarting the live API. This isolates service checks from live application data. New images do not automatically replace running application containers: explicitly refresh the affected app when testing new live behavior. HTTP checks test whichever app is actually running; keep that distinction in a feature handoff.

`--skip-build` is for freshly built images (CI builds them earlier). Do not use it to validate stale source. HTTP defaults to the configured local port; `ASANTE_BASE_URL` supports CI's localhost:8080. Expected live services fail instead of skipping. No unit/HTTP check is claimed as browser visual verification.

Every non-serving invocation writes a generated, password-redacted JSON execution summary under `logs/codex/`, containing command, exit status, duration and bounded output. Test-bearing invocations also write category reports under `logs/tests/unit/`, `functional/`, `integration/`, and/or `e2e/`, each linked to its full execution summary. No generated files are written directly in the `logs/` root. Successful checks exit 0; failures/timeouts exit nonzero and stop dependent checks. CI uses the same runner and uploads these reports, never credential files.

## Verification and limitations

The actual stdio handshake, exact seven-tool allowlist, authenticated PostgreSQL/MinIO calls and denied writes were tested locally. Execution reports are the evidence source. Dependency pinning is in `infrastructure/codex/requirements.txt`; tooling dependencies are isolated from Asante runtime requirements.

The installed MCP SDK currently emits a non-fatal Pydantic settings warning; protocol/read tests pass. Existing Asante npm dependencies report audit advisories during clean installs. Those advisories are logged for a separate dependency/security task; this setup does not apply a force upgrade or claim dependency-security acceptance.

Remote GitHub Actions execution/branch protection remain unverified until the workflow is pushed and run on GitHub. No Git repository, commit, remote, paid AI loop or deployment was created by this setup.

## Disable or recover

Back up and remove only the `[mcp_servers.codex_asante_readonly]` entry from the local project config, then restart Codex. This disables tool registration without changing application data. For credential revocation, an administrator can disable the dedicated MinIO identity and run `ALTER ROLE codex_asante_reader NOLOGIN`; do not revoke application roles or delete the media bucket.

Restore only a specifically backed-up Codex setting if needed; do not overwrite unrelated settings changed since the backup. The global OpenAI documentation connection remains separate.

## Automation boundary

These scripts automate deterministic development checks now. They use the MCP SDK to test the protocol. They remain separate from Asante runtime SDKs and any scheduled Codex automation.
