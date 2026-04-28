# TLS Deployment Notes

The Python TCP control plane supports native TLS when both PEM files are
provided:

```powershell
python -m server.main --tcp-server `
  --tls-cert-file .\deploy\tls\certs\server.crt `
  --tls-key-file .\deploy\tls\certs\server.key
```

Equivalent environment variables:

```powershell
$env:TELEGRAM_TLS_CERT_FILE="C:\path\server.crt"
$env:TELEGRAM_TLS_KEY_FILE="C:\path\server.key"
python -m server.main --tcp-server
```

## Current Client Compatibility

The current C++ desktop clients use the plaintext `TcpLineClient` transport.
For production-like testing today, use one of these paths:

- Run the server in plaintext behind a reverse proxy that terminates TLS and
  forwards local plaintext to `127.0.0.1:8787`.
- Use native TLS for Python or external clients that can open a TLS socket.

Direct C++ desktop-to-native-TLS support is still a follow-up transport slice.
That work should add a TLS-capable client transport behind the existing
`ControlPlaneClient` boundary so UI code remains unchanged.

Current C++ builds expose that boundary through `ControlPlaneClient::connect_tls`
and the `--tls` / `--tls-insecure` client flags. On Windows this path uses
Schannel. In the current local validation environment the C++ code compiles,
but the direct TLS runtime smoke is blocked by Schannel credential acquisition
(`SEC_E_NO_CREDENTIALS`), so the Docker proxy smoke remains the verified TLS
client path until the Windows TLS backend is completed or replaced.

## Docker TLS Termination Profile

The Docker compose file includes an `nginx` TLS termination profile:

```bash
mkdir -p deploy/tls/certs
python scripts/generate_tls_dev_cert.py --out-dir deploy/tls/certs --overwrite
docker compose -f deploy/docker/docker-compose.yml --profile tls up -d telegram-server telegram-tls-proxy
```

The proxy listens on host port `8443` and forwards to the plaintext control
plane service at `telegram-server:8787` using nginx `stream` TLS termination.

For the PostgreSQL-backed profile, run the companion proxy:

```bash
docker compose -f deploy/docker/docker-compose.yml --profile postgres --profile tls up -d postgres telegram-server-postgres telegram-tls-proxy-postgres
```

The PostgreSQL proxy listens on host port `8444` and forwards to
`telegram-server-postgres:8787`.

Validation:

```powershell
python scripts\validate_tls_deployment_config.py
python scripts\validate_tls_proxy_smoke.py
python scripts\validate_tls_proxy_smoke.py --port 8444 --device dev_tls_proxy_pg_smoke
```

## Certificate Handling

Do not commit private keys. Keep certificate/key material outside the repo or
under an ignored local directory such as `deploy/tls/certs/`.

For local smoke testing with a self-signed certificate:

```powershell
python scripts\generate_tls_dev_cert.py --out-dir deploy\tls\certs --overwrite
python scripts\validate_tls_config.py
python -m server.main --tcp-server --tls-cert-file <cert.pem> --tls-key-file <key.pem>
```

`validate_tls_config.py` verifies the control-plane configuration guards, not a
full client handshake.
