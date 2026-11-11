# Local infrastructure

Codex development inspection uses an optional `codex-mcp` service in the `codex` profile. It is launched on demand over stdio, has no public port or Docker socket, and receives only dedicated reader credentials. Setup, permission verification and execution-check scripts are documented in [CODEX_MCP.md](../documentation/ai/references/CODEX_MCP.md). It is not an Asante runtime dependency.

The current Docker setup provides the local database, MinIO storage, and Nginx proxy foundation for Asante.

## Services

- PostgreSQL 16 with PostGIS for story locations and geospatial queries.
- PostGIS is enabled for geospatial queries. Semantic retrieval will be added only after we choose and validate the vector-search approach.
- MinIO for local S3-compatible audio and video storage.
- The Asante API for health checks, nearby landmark/story queries, Research-room planner/researcher workers, uploads and human-gated submissions.

The Asante map does not need its own container for the first prototype. MapLibre GL JS runs inside the Asante website, uses browser geolocation, and reads map tiles from a configured provider. Self-hosting map tiles is deferred.

MinIO is available at `http://localhost:9000` for the S3 API and `http://localhost:9001` for the local console. The default credentials are for local development only.

In standalone mode, the public Asante URLs are:

- `http://localhost/asante/` for the map
- `http://localhost/asante/portal/` for the contributor portal
- `http://localhost/asante/review/` for the Asante approval dashboard
- `http://localhost/asante/api/health` for the Asante API health check

The Asante proxy routes these paths to the internal Asante website, dashboard and API containers. Its internal path routing stays enabled in either port mode. A separate AI-service / talk-gateway container is not part of the current Compose stack.

For a laptop that uses another local reverse proxy on port `80`, set `ASANTE_HTTP_PORT=8082` in the ignored Asante `.env` and configure that local proxy to forward `/asante` to `host.docker.internal:8082`, preserving the request path. Asante continues serving `/asante/`, `/asante/portal/`, `/asante/review/` and `/asante/api/` behind that upstream. Set `ASANTE_HTTP_PORT=80` when running Asante's proxy directly for a standalone or live demo; only one local service can own host port `80` at a time.

## Start the database

```bash
cp infrastructure/.env.example infrastructure/.env
docker compose --env-file infrastructure/.env -f infrastructure/docker-compose.yml up -d
```

Check the service:

```bash
docker compose --env-file infrastructure/.env -f infrastructure/docker-compose.yml ps
```

Connect with:

```text
postgresql://asante:asante_local_dev_only@localhost:5432/asante
```

The password in `.env.example` is for local development only. Do not use it in a shared or deployed environment. The database data is stored in the named Docker volume `asante_postgres_data`.

## Stop the database

```bash
docker compose --env-file infrastructure/.env -f infrastructure/docker-compose.yml down
```

The named volume is retained when the stack is stopped. Removing the volume is destructive and should only be done deliberately.

## Asante API data connections

The API connects to PostgreSQL at the internal `postgres` service and MinIO at `minio:9000`, using server-side environment settings supplied by Compose. Local MinIO credentials are mapped from the existing Asante environment; no browser key is needed. The current demo bucket is `asante-media`. Use a dedicated scoped runtime credential before deployment.

Apply the migration and catalogue/media seeds from [BOOTSTRAP_PROMPT.md](../documentation/ai/exec-plans/BOOTSTRAP_PROMPT.md) after startup. The media seed preserves existing objects; the catalogue seed preserves existing records. `/asante/api/health/ready` checks both services. Website catalogue requests query PostgreSQL, and the public story media route resolves its private object key from PostgreSQL before streaming from MinIO.
