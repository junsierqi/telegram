# telegram_like

A multi-platform chat application roadmap with a `C++20` client and a `Python` server, designed so a self-built remote-desktop system can be added on top of the chat product in later phases.

## Principles

- architecture-first delivery
- code and docs evolve together
- chat system first, remote control second
- remote control is a native subsystem, not a third-party desktop app integration
- client and server boundaries stay explicit
- diagrams stay text-based and version-controlled

## Documentation map

- [System overview](docs/architecture/overall.md)
- [Implementation roadmap](docs/architecture/implementation-roadmap.md)
- [Telegram compatibility notes](docs/architecture/telegram-compatibility.md)
- [Client architecture](docs/architecture/client.md)
- [Server architecture](docs/architecture/server.md)
- [Remote-control extension](docs/architecture/remote-control.md)
- [Document maintenance rules](docs/architecture/document-maintenance.md)
- [User flows](docs/flows/user-flows.md)
- [System sequence flows](docs/flows/sequence-flows.md)

## Repository layout

- `client/`: `C++20` desktop client skeleton built with `CMake`
- `server/`: `Python` control-plane server skeleton
- `shared/`: shared protocol vocabulary and future schemas
- `docs/`: architecture and flow documentation

## Initial phases

1. Define architecture and flows.
2. Scaffold code to match the architecture.
3. Build chat MVP.
4. Add real-time session negotiation for calls and remote control.
5. Add AnyDesk-like remote-control capabilities implemented in this codebase, with architecture direction informed by RustDesk-style designs.

## Current runnable entry points

```powershell
cmake -S . -B build-codex -DCMAKE_PREFIX_PATH=C:\Qt\6.11.0\msvc2022_64
cmake --build build-codex --config Debug
.\build-codex\client\src\Debug\telegram_like_client.exe
.\build-codex\client\src\Debug\app_chat.exe --user alice --password alice_pw --device dev_alice_win
.\build-codex\client\src\Debug\app_chat.exe --user alice --password alice_pw --device dev_alice_win --port 8443 --tls --tls-insecure --tls-server-name localhost
.\build-codex\client\src\Debug\app_desktop.exe
.\build-codex\client\src\Debug\app_desktop.exe --cache-file .tmp_app_desktop_cache.json
python -m server.main
python -m server.main --tcp-server --attachment-dir .tmp_attachments
python -m server.main --tcp-server --db-file .tmp_runtime.sqlite --attachment-dir .tmp_attachments
python -m server.main --tcp-server --pg-dsn postgresql://telegram:telegram_dev_password@localhost:5432/telegram
python -m server.main --tcp-server --session-ttl-seconds 86400
python -m server.main --tcp-server --tls-cert-file server.crt --tls-key-file server.key
wsl bash -lc "cd /mnt/d/code_codex/telegram && docker compose -f deploy/docker/docker-compose.yml up --build telegram-server"
wsl bash -lc "cd /mnt/d/code_codex/telegram && docker compose -f deploy/docker/docker-compose.yml --profile postgres up postgres telegram-server-postgres"
wsl bash -lc "cd /mnt/d/code_codex/telegram && docker compose -f deploy/docker/docker-compose.yml --profile postgres --profile tls up postgres telegram-server-postgres telegram-tls-proxy-postgres"
powershell -ExecutionPolicy Bypass -File scripts\deploy_wsl_docker.ps1
powershell -ExecutionPolicy Bypass -File scripts\deploy_wsl_docker.ps1 -Mode postgres
python scripts\validate_tls_handshake.py
python scripts\validate_tls_deployment_config.py
python scripts\generate_tls_dev_cert.py --out-dir deploy\tls\certs --overwrite
python scripts\validate_tls_proxy_smoke.py
python scripts\validate_tls_proxy_smoke.py --port 8444 --device dev_tls_proxy_pg_smoke
python scripts\validate_cpp_tls_client.py
powershell -ExecutionPolicy Bypass -File scripts\package_windows_desktop.ps1 -SkipQtDeploy
powershell -ExecutionPolicy Bypass -File scripts\package_windows_desktop.ps1 -SkipQtDeploy -Zip
```

## Current milestone

The repository now contains a verified chat and remote-control control-plane prototype, plus the first desktop GUI baseline:

- `app_desktop.exe` is a Qt Widgets desktop shell for login, conversation sync, live push display and text send
- `app_desktop.exe` also exposes a Register button for new-account creation through the same native control-plane client
- `app_desktop.exe` now renders from `DesktopChatStore`; sync/send/push events update one local conversation/message model, persist to `--cache-file`, drive a real conversation list, and reconnect with per-conversation message cursors plus change versions for message and metadata deltas
- desktop message timeline rendering now includes HH:MM timestamps for new messages, an explicit legacy timestamp fallback, rich inbound/outbound bubble-style rows, local pending/sent/failed/read state, per-member group read details, and preserved read markers in the local cache
- desktop contacts/groups UI can list/add/remove contacts, create groups and add/remove selected conversation members
- desktop profile/account UI can load and update the current display name; user discovery can search by username, display name or user_id and shows online/contact state
- desktop navigation/search now includes chat-list filtering plus selected-conversation message search with match navigation and timeline highlighting
- server-side message search now covers accessible conversations with optional conversation scope, offset paging, C++ client support, desktop result cards and attachment filename matches
- conversation history can be requested in bounded pages through `conversation_sync` history limits and `next_before_message_id`
- the desktop GUI can request older selected-conversation history pages and merge them into the local cache
- desktop message actions now cover replies, forwards, reaction toggles and pin/unpin state through protocol, server persistence, incremental sync, local cache and Qt controls; timeline message ids and focused search matches can be used directly as action targets
- attachments now use an object-store-ready boundary: metadata stays in runtime state, content goes to `--attachment-dir`, and the desktop GUI can send/save attachments while showing filename/size metadata, type previews and stage-based transfer status
- server persistence can use `--db-file` for SQLite-backed durable state while JSON `--state-file` remains supported
- Linux Docker deployment files live under `deploy/docker`; the default server container persists SQLite state and attachments under `/data`, while the PostgreSQL compose profile also starts a PG-backed server on port 8788
- the PostgreSQL repository path now stores users, devices, sessions, conversations, messages, conversation change logs, contacts, attachment metadata and remote sessions in dedicated tables, records schema version rows and has an app-level backup/restore round-trip validator
- login sessions can be bounded with `--session-ttl-seconds` / `TELEGRAM_SESSION_TTL_SECONDS`; heartbeats refresh the active session age and expired sessions are removed
- the TCP control plane can run native TLS when `--tls-cert-file` and `--tls-key-file` are configured together, with a real TLS login smoke validator; Docker also has `nginx` stream TLS termination profiles for the SQLite-backed service on port 8443 and PostgreSQL-backed service on port 8444; the C++ control-plane client now has a Windows Schannel TLS transport entrypoint, but the local direct TLS smoke is blocked by Schannel credential acquisition in this environment
- Windows desktop package staging is available through `scripts\package_windows_desktop.ps1`, with optional `windeployqt` runtime collection, zip output and SHA256 checksum files
- desktop device management can list devices, toggle trust and revoke non-current device sessions, with confirmation before revoke
- `app_chat.exe` is the native interactive C++ chat CLI
- Python server dispatches auth, chat, group, read, edit/delete, contacts, attachments, presence and remote-session messages
- client and server exchange line-delimited JSON over persistent TCP sockets
- UDP media-plane prototypes cover auth-gated echo, frame subscription, relay and synthetic screen frames
- production storage, real mobile clients and real remote-desktop capture/render remain deferred

For the current GUI smoke demo:

1. Start `python -m server.main --tcp-server`
2. Run `.\build-codex\client\src\Debug\app_desktop.exe`
3. Connect as `alice` / `alice_pw`, then send text in `conv_alice_bob`

Automated smoke check:

```powershell
python scripts\validate_desktop_smoke.py
.\build-codex\client\src\Debug\app_desktop_store_test.exe
python scripts\validate_message_actions.py
python scripts\validate_message_search.py
python scripts\validate_history_paging.py
python scripts\validate_docker_deploy.py
python scripts\validate_docker_deploy.py --port 8788 --device dev_docker_pg_smoke
docker exec -e TELEGRAM_TEST_PG_DSN=postgresql://telegram:telegram_dev_password@postgres:5432/telegram docker-telegram-server-postgres-1 python scripts/validate_postgres_repository.py
docker exec -e TELEGRAM_TEST_PG_DSN=postgresql://telegram:telegram_dev_password@postgres:5432/telegram docker-telegram-server-postgres-1 python scripts/validate_postgres_backup_restore.py
python scripts\validate_session_hardening.py
python scripts\validate_tls_config.py
python scripts\validate_tls_handshake.py
python scripts\validate_tls_deployment_config.py
python scripts\validate_tls_dev_cert.py
python scripts\validate_tls_proxy_smoke.py
python scripts\validate_tls_proxy_smoke.py --port 8444 --device dev_tls_proxy_pg_smoke
python scripts\validate_cpp_tls_client.py
powershell -ExecutionPolicy Bypass -File scripts\package_windows_desktop.ps1 -SkipQtDeploy
powershell -ExecutionPolicy Bypass -File scripts\validate_windows_package.ps1
python scripts\validate_profile_search.py
python scripts\validate_incremental_sync.py
python scripts\validate_attachments.py
python scripts\validate_sqlite_persistence.py
python scripts\validate_device_management.py
```
