# telegram_like

A multi-platform chat application with a `C++20` client and a `Python` server,
designed so a self-built remote-desktop subsystem can layer on top of the chat
product. Today: real working chat across Windows / Linux / Android with native
TLS, push-notification surface, chunked uploads, PostgreSQL persistence, and
~45 in-process validators that GitHub Actions runs on every push.

## Principles

- architecture-first delivery
- code and docs evolve together
- chat system first, remote control second
- remote control is a native subsystem, not a third-party desktop app integration
- client and server boundaries stay explicit
- diagrams stay text-based and version-controlled

## Repository layout

- `client/` — `C++20` clients sharing a single `chat_client_core` static library
  - `app/`, `app_chat/`, `app_desktop/`, `app_mobile/`, `net/`, `transport/`, `remote_control/`
- `server/` — `Python` control plane + UDP media plane
- `shared/` — protocol vocabulary + schemas mirrored between client and server
- `deploy/` — `docker/` (SQLite + PostgreSQL + nginx TLS), `tls/`, `windows/`
  (Inno Setup), `linux/` (.desktop + apt deps), `android/` (Qt for Android manifest)
- `scripts/` — 45 in-process validators + helpers (build/package/sweep)
- `docs/architecture/`, `docs/flows/`, `docs/diagrams/` — text-based design docs
- `.github/workflows/ci.yml` — Python sweep + Linux C++ + Linux Qt desktop + bundle verify

## Documentation map

- [Current-state architecture](docs/architecture/current-state.md) — authoritative file walk
- [System overview](docs/architecture/overall.md)
- [Implementation roadmap](docs/architecture/implementation-roadmap.md)
- [Telegram compatibility notes](docs/architecture/telegram-compatibility.md)
- [Client architecture](docs/architecture/client.md)
- [Server architecture](docs/architecture/server.md)
- [Remote-control extension](docs/architecture/remote-control.md)
- [User flows](docs/flows/user-flows.md) · [System sequence flows](docs/flows/sequence-flows.md)
- Platform deploy READMEs: [`deploy/docker`](deploy/docker/README.md) ·
  [`deploy/linux`](deploy/linux/README.md) ·
  [`deploy/android`](deploy/android/README.md) ·
  [`deploy/tls`](deploy/tls/README.md)
- Delivery bundle: [`.idea-to-code/telegram-platform/`](.idea-to-code/telegram-platform/)

## What runs today

| Surface | Status | Build target |
|---|---|---|
| Python server (chat + remote-control protocol + UDP media plane) | ✅ | `python -m server.main` |
| C++ chat CLI | ✅ Win, Linux, **Android NDK** | `app_chat` |
| Qt Widgets desktop | ✅ Win, **Linux** | `app_desktop` |
| **Qt Quick mobile UI** | ✅ Win preview + **Android arm64 APK** | `app_mobile` |
| Native TLS (Schannel direct + nginx stream proxy) | ✅ Live PostgreSQL + SQLite | M67/M68/M82 |
| Windows installer (Inno Setup) | ✅ unsigned | `package_windows_desktop.ps1 -Installer` |
| Android APK (Qt for Android, NDK 30) | ✅ unsigned | `scripts/build_android_apk.ps1` |
| Push notifications (register/unregister/list + offline mock dispatch + pluggable transport) | ✅ wire complete; FCM bearer token = PA-008 | M84 / M91 |
| Chunked attachment upload (≤64 MB) | ✅ init/chunk/complete | M88 |
| PostgreSQL backend | ✅ live verified | `--pg-dsn` |
| CI/CD on GitHub Actions | ✅ 4 jobs on every push | `.github/workflows/ci.yml` |

## Quick start

```bash
# 1. server — pick one persistence backend
python -m server.main --tcp-server                                     # JSON file
python -m server.main --tcp-server --db-file .tmp_runtime.sqlite       # SQLite
python -m server.main --tcp-server --pg-dsn postgresql://...           # PostgreSQL

# 2. desktop client (Windows, Linux, or Android)
cmake -S . -B build -DCMAKE_PREFIX_PATH=<path-to-Qt>
cmake --build build --config Debug --target app_desktop app_mobile app_chat
./build/client/src/Debug/app_desktop.exe                                # Windows
./build/client/src/app_desktop                                          # Linux
powershell scripts/build_android_apk.ps1                                # Android APK

# 3. chat CLI (no Qt needed)
./build/client/src/Debug/app_chat.exe --user alice --password alice_pw --device dev_alice_win

# 4. native TLS direct (Windows Schannel)
./build/client/src/Debug/app_chat.exe --user alice --password alice_pw \
    --device dev_alice_win --port 8443 --tls --tls-insecure --tls-server-name localhost

# 5. Docker — SQLite, PostgreSQL, or with nginx TLS proxy on 8443/8444
wsl bash -lc "cd /mnt/.../telegram && docker compose -f deploy/docker/docker-compose.yml up --build telegram-server"
wsl bash -lc "docker compose -f deploy/docker/docker-compose.yml --profile postgres --profile tls up postgres telegram-server-postgres telegram-tls-proxy-postgres"
```

## Capabilities (current state)

### Chat / messaging

- text + reply + forward + edit + delete + reactions + pin
- conversations: create / add / remove participants; per-message read markers
- **incremental sync** with cursors + version vectors + bounded older-history pagination
- **conversation_updated** push so being added to a group lands without manual sync
- contacts (directed), user search, message search across accessible conversations
- attachments: small inline (≤1 MB) + **chunked upload up to 64 MB** (init/chunk/complete)
- **CJK / emoji / surrogate-pair UTF-8** round-trips on the C++ client (M72)

### Authentication / sessions

- username + password (PBKDF2-SHA256 stdlib only); registration flow
- `--session-ttl-seconds` bound + heartbeat refresh
- device management: list / trust / untrust / revoke (with current-device guard)

### Presence

- TTL-based online state (default 30 s); heartbeat refresh
- **PRESENCE_UPDATE push** fan-out on offline↔online transitions to anyone sharing a conversation (M78)

### Push notifications

- per-device push token register/unregister/list (M84)
- offline-recipient mock-dispatch hook on `MESSAGE_SEND` (M84)
- `PushDispatchWorker` drains the mock queue per platform via pluggable
  `Transport` (M91): `LogOnlyTransport` default · `FakeTransport` for tests ·
  `FCMHttpTransport` (FCM v1, stdlib `urllib`, dry_run when no bearer token)

### Remote control

- full state machine: invite → approve/reject/cancel/terminate/disconnect → rendezvous
- **C++ ControlPlaneClient covers all 8 remote-control RPCs** (M76); legacy
  `session_gateway_client` retained for the `app_shell` demo
- UDP media plane: per-session auth + frame_chunk subscribe + relay + synthetic
  screen source; `ReliableChannel` algorithm validated, integration into
  `media_plane.py` deferred

### Storage / persistence

- JSON file (`--state-file`), SQLite (`--db-file`), or PostgreSQL (`--pg-dsn`)
- PostgreSQL repository: users / devices / sessions / conversations / messages /
  conversation change logs / contacts / attachments / remote sessions, with
  schema-version rows and app-level backup/restore round-trip
- `AttachmentBlobStore` boundary stays object-store-ready (filesystem today)

### Transport security

- native TLS on the control plane (`--tls-cert-file` + `--tls-key-file`)
- C++ direct TLS via Schannel (`--tls`/`--tls-insecure`/`--tls-server-name`),
  fixed in M68 by passing an explicit `SCHANNEL_CRED`
- nginx stream TLS termination for SQLite (8443) and PostgreSQL (8444); both
  paths are live-verified end-to-end

### Packaging

- Windows: Inno Setup installer (`scripts/package_windows_desktop.ps1 -Installer`),
  unsigned today (signing = PA-005)
- Android: arm64-v8a APK via Qt for Android (`scripts/build_android_apk.ps1`),
  unsigned today (keystore = PA-005)
- Linux: cmake + system Qt 6 build (`deploy/linux/README.md`); .desktop entry
  shipped, packaging (.deb / .rpm / AppImage) deferred

## Verification

`scripts/_sweep_validators.py` runs every `validate_*.py` (~45 in-process
validators, ~200 scenarios) and tags 4 external-state validators as
`SKIP_EXTERNAL`. CI runs the same sweep + a Linux C++ build + a Linux Qt
desktop build + a bundle integrity check on every push.

```bash
python scripts/_sweep_validators.py        # full local sweep
python scripts/validate_desktop_smoke.py   # Qt desktop smoke (Windows)
python scripts/validate_cpp_tls_client.py  # native TLS round-trip
python scripts/validate_chunked_upload.py  # 5 MB upload byte-exact round-trip
python scripts/validate_presence_push.py   # PRESENCE_UPDATE fan-out
python scripts/validate_push_dispatch.py   # FCM/APNs worker via FakeTransport
python scripts/validate_postgres_repository.py --pg-dsn postgresql://...
python scripts/validate_tls_proxy_smoke.py --port 8444 --device dev_pg_smoke
```

`build-verify/client/src/Debug/json_parser_test.exe` (9/9) and
`app_desktop_store_test.exe` (20/20) are the native C++ test binaries.

## Pending external dependencies

The codebase is feature-complete for the milestones it claims; the only
items still gated on user action are credential/cost decisions:

- **PA-005** — Authenticode certificate (Windows) + Android keystore for
  signed installer/APK distribution
- **PA-008** — FCM service-account JSON / APNs token to flip
  `FCMHttpTransport.dry_run = False` and reach real device wake-up channels

See [`.idea-to-code/telegram-platform/08-atlas-task-library.md`](.idea-to-code/telegram-platform/08-atlas-task-library.md)
for the full backlog (Linux desktop ✅, mobile UI ✅, push wiring ✅, plus
planned: phone-number OTP, 2FA, observability, rate limiting, account
deletion, voice/video, iOS, E2E encryption).
