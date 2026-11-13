# Asante logs

Generated records live in subfolders only. Keep this root limited to this README.

| Folder | Contents |
| --- | --- |
| `codex/` | Codex execution summaries |
| `tests/unit/` | Unit test reports |
| `tests/functional/` | Functional test reports |
| `tests/integration/` | Integration test reports |
| `tests/e2e/` | End-to-end test reports |
| `ops/` | Short operator notes (not bulky run dumps) |

## Live debugging (uploads, portal, API)

Do **not** dump GUI vs shell upload traces into this tree. Prefer the live container logs, which already show the request path:

```bash
# Asante website (Next.js) — incoming page/API-proxy style requests
ssh hubtweak-vps1 'docker logs -f --tail 200 asante-asante-1'

# Asante API — auth, workspace, uploads, workers, submissions
ssh hubtweak-vps1 'docker logs -f --tail 200 asante-api-1'

# Durable media jobs (transcribe / translate / HLS / analyze)
ssh hubtweak-vps1 'docker logs -f --tail 200 asante-job-worker-1'
```

Website lines are prefixed `[asante] METHOD /path`. Compare a browser portal upload against a shell/`curl` upload by watching `asante-asante-1` and `asante-api-1` at the same time.
