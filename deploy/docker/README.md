# Linux Docker Deployment

This deployment path is intended to run from WSL/Linux.

## One-command deploy

From Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\deploy_wsl_docker.ps1
```

The default mode starts only `telegram-server` and keeps the current local-test
SQLite backend:

- database: `/data/runtime.sqlite`
- attachments: `/data/attachments`
- TCP port: `8787`

To also start the PostgreSQL development service for the future repository
boundary:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\deploy_wsl_docker.ps1 -Mode postgres
```

This starts an additional PostgreSQL-backed server on port `8788`. The default
SQLite server on port `8787` remains available for local testing.

## Proxy

The compose file forwards `HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY` and lowercase
variants into build args and the container environment. Docker image pulls use
the Docker daemon proxy, so WSL may also need:

```bash
mkdir -p /etc/systemd/system/docker.service.d
cat >/etc/systemd/system/docker.service.d/http-proxy.conf <<'EOF'
[Service]
Environment=HTTP_PROXY=http://10.20.11.30:10809
Environment=HTTPS_PROXY=http://10.20.11.30:10809
Environment=NO_PROXY=127.0.0.1,localhost,10.20.11.0/24,10.20.11.*
EOF
systemctl daemon-reload
systemctl restart docker
```

## Manual commands

```bash
cd /mnt/d/code_codex/telegram
docker compose -f deploy/docker/docker-compose.yml up --build -d telegram-server
docker compose -f deploy/docker/docker-compose.yml --profile postgres up -d postgres telegram-server-postgres
docker compose -f deploy/docker/docker-compose.yml ps
```

Smoke test from the repo root:

```powershell
python scripts\validate_docker_deploy.py
python scripts\validate_docker_deploy.py --port 8788 --device dev_docker_pg_smoke
```

Stop:

```bash
docker compose -f deploy/docker/docker-compose.yml --profile postgres down
```

---

## Production deploy (M115 — `production` profile)

The `production` profile brings up the full release stack:

- **`telegram-server-prod`** — PostgreSQL-backed Python server. TCP control
  plane on `8787`, M110 web bridge on `8080`, M92 observability sidecar on
  `9100`. `restart: always`. Healthcheck hits `/healthz` on the sidecar.
- **`postgres`** — Postgres 16. Healthcheck via `pg_isready`. `restart: always`
  (when `TELEGRAM_RESTART_POLICY=always`).
- **`nginx-web`** — TLS termination + WS upgrade reverse proxy. Listens on
  `80` (redirect to 443) and `443` (TLS). Routes `/ws` to the bridge,
  `/healthz` to the observability sidecar, and serves `/` + `/app.js` as
  static assets.
- **`prometheus`** (optional, `monitoring` profile) — scrapes
  `telegram-server-prod:9100/metrics` every 15s. Listens on `9090`.

### One-shot bring-up

```bash
cp deploy/docker/production.env.example deploy/docker/.env
$EDITOR deploy/docker/.env       # set PG password + any procured PA-008/009/011 values
docker compose -f deploy/docker/docker-compose.yml \
    --env-file deploy/docker/.env \
    --profile production --profile monitoring \
    up --build -d
```

Browser opens `https://<host>/` (will be a self-signed cert warning until you
swap in a real cert pair into `deploy/tls/certs/`).

### Pending Action injection points

| PA | What | Where to wire it |
|---|---|---|
| **PA-005** | Authenticode + Apple developer cert | Outside this stack — used during Windows installer + iOS build, not at server runtime. |
| **PA-008** | FCM service-account JSON | Place file under `deploy/secrets/fcm.json`, mount into `telegram-server-prod` via a `volumes:` entry, set `TELEGRAM_FCM_CREDENTIALS=/run/secrets/fcm.json` in `.env`. |
| **PA-009** | Twilio / Aliyun SMS token | `TELEGRAM_SMS_PROVIDER=twilio` + `TELEGRAM_SMS_AUTH_TOKEN=<token>` in `.env`. |
| **PA-010** | macOS host for iOS / macOS build | Outside this stack. |
| **PA-011** | Redis endpoint + token | `TELEGRAM_REDIS_URL=https://<endpoint>` + `TELEGRAM_REDIS_TOKEN=<token>` in `.env`. |

### TLS cert swap

`deploy/tls/certs/server.{crt,key}` ships as a self-signed dev pair. For
real TLS replace those two files with your issued cert + key (Let's Encrypt
certbot, ACM-issued, commercial CA — anything PEM works). Restart `nginx-web`:

```bash
docker compose -f deploy/docker/docker-compose.yml --profile production restart nginx-web
```

### Day-2 ops

```bash
# Rolling restart server only (Postgres + nginx stay up)
docker compose -f deploy/docker/docker-compose.yml --profile production up -d --no-deps --build telegram-server-prod

# Tail server logs
docker compose -f deploy/docker/docker-compose.yml --profile production logs -f telegram-server-prod

# Backup Postgres volume
docker run --rm -v telegram-platform_telegram_postgres_data:/data -v "$(pwd)/backups:/backups" \
    postgres:16-alpine pg_dump -h postgres -U telegram telegram > backups/telegram-$(date +%F).sql

# Stop everything
docker compose -f deploy/docker/docker-compose.yml --profile production --profile monitoring down
```

### Local development still works the same way

The new profile does not change the existing entry points — keep using
`python -m server.main --tcp-server --web-port 8080` for fast local
iteration. The `production` profile only ships when you explicitly opt in
via `--profile production`.
