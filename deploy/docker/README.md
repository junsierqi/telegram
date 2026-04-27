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
