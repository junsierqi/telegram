# telegram_like

A multi-platform chat application with a `C++20` client and a `Python` server,
designed so a self-built remote-desktop subsystem can layer on top of the chat
product. Today: chat + voice/video signaling + remote control across Windows /
Linux / macOS / Android (APK) / browser, with native TLS, AEAD-sealed media
plane, push-notification surface, chunked uploads, PostgreSQL persistence,
Redis hot-state cache wired into PresenceService + AuthService, production
Docker stack with nginx WebSocket reverse proxy + Prometheus, and ~70
in-process validators that GitHub Actions runs across 7 jobs on every push.

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
- `server/` — `Python` control plane + UDP media plane + WebSocket bridge
  - `server/web/` — bundled HTML/JS browser client (M110-M124)
- `shared/` — protocol vocabulary + schemas mirrored between client and server
- `deploy/` — `docker/` (SQLite + PostgreSQL + nginx TLS + production stack),
  `tls/` (stream + HTTP+WS reverse-proxy nginx configs), `windows/` (Inno
  Setup), `linux/` (.desktop + apt deps), `android/` (Qt for Android manifest),
  `macos/` + `ios/` (Info.plist templates + CMake guards)
- `scripts/` — ~70 in-process validators + helpers (build/package/sweep)
- `docs/architecture/`, `docs/flows/`, `docs/diagrams/` — text-based design docs
- `.github/workflows/ci.yml` — 7 jobs: validators · Linux C++ · Linux Qt
  desktop · macOS Qt build · bundle verify · **Windows Qt build · Android APK**

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
  [`deploy/macos`](deploy/macos/README.md) ·
  [`deploy/ios`](deploy/ios/README.md) ·
  [`deploy/tls`](deploy/tls/README.md)
- Delivery bundle: [`.idea-to-code/telegram-platform/`](.idea-to-code/telegram-platform/)

## What runs today

| Surface | Status | Build target |
|---|---|---|
| Python server (chat + remote-control protocol + UDP media plane + voice/video signaling + WebSocket bridge + observability sidecar) | ✅ | `python -m server.main` |
| C++ chat CLI | ✅ Win, Linux, macOS, **Android NDK** | `app_chat` |
| Qt Widgets desktop (full settings + Remote + Call pages, real image preview, byte-level upload progress) | ✅ Win, **Linux**, **macOS** | `app_desktop` |
| Qt Quick mobile UI (full settings hub: Profile / Contacts / Devices / Search / Attachments / Remote / Call) | ✅ Win preview + **Android arm64 APK** | `app_mobile` |
| Browser client (3-pane WebSocket bridge + chat list + attachment up/download + call dialog + PWA service worker) | ✅ any modern browser | `python -m server.main --web-port 8080` |
| Native TLS (Schannel direct + nginx stream proxy + nginx HTTP+WS reverse proxy) | ✅ Live PostgreSQL + SQLite | M67/M68/M82/M115 |
| AEAD media plane (AES-256-GCM per-call/session key, ReliableChannel over RELAY) | ✅ | M105/M106/M127 |
| Voice/video call signaling FSM + audio frame transport over relay | ✅ skeleton (PassThroughCodec; OpusCodec stub gated on PA-012) | M109/M127/M128 |
| Windows installer (Inno Setup) | ✅ unsigned | `package_windows_desktop.ps1 -Installer` |
| Android APK (Qt for Android, NDK 30) | ✅ unsigned arm64-v8a | `scripts/build_android_apk.ps1` |
| macOS .app bundle (with macdeployqt POST_BUILD; non-fatal when Homebrew Qt is incomplete) | ✅ | `cmake --target app_desktop app_mobile` on macOS |
| iOS .app scaffold | ⏳ Info.plist + CMake guard ready, needs PA-010 (macOS host + Xcode + Qt for iOS) | — |
| Push notifications (register/unregister/list + offline mock dispatch + pluggable transport + service-worker stub) | ✅ wire complete; FCM bearer = PA-008 | M84 / M91 |
| Chunked attachment upload (≤64 MB) | ✅ init/chunk/complete + C++ progress callback | M88 / M126 |
| PostgreSQL backend (snapshot save + new per-entity `upsert_*` transactional methods) | ✅ live verified | `--pg-dsn` |
| Redis hot-state cache (PresenceService + AuthService fast path, FakeRedis default + HTTP transport gated on PA-011) | ✅ wired | `--redis-fake` / `--redis-url` |
| Production Docker stack (telegram-server-prod + nginx-web TLS + Prometheus, restart=always, healthchecked Postgres) | ✅ | `--profile production --profile monitoring` |
| Observability (structured JSON logs + Prometheus `/metrics` + `/healthz`) | ✅ | `--metrics-port 9100` |
| CI on GitHub Actions | ✅ **7 jobs** on every push | `.github/workflows/ci.yml` |

## Quick start

```bash
# 1. server — pick one persistence backend, optionally add web/metrics/redis
python -m server.main --tcp-server                                     # JSON file
python -m server.main --tcp-server --db-file .tmp_runtime.sqlite       # SQLite
python -m server.main --tcp-server --pg-dsn postgresql://...           # PostgreSQL
python -m server.main --tcp-server --web-port 8080                     # + browser at http://127.0.0.1:8080/
python -m server.main --tcp-server --metrics-port 9100                 # + /metrics + /healthz on 9100
python -m server.main --tcp-server --redis-fake                        # + in-memory hot-state cache (M111/M116/M117)

# 2. desktop client (Windows, Linux, or macOS)
cmake -S . -B build -DCMAKE_PREFIX_PATH=<path-to-Qt>
cmake --build build --config Debug --target app_desktop app_mobile app_chat
./build/client/src/Debug/app_desktop.exe                                # Windows
./build/client/src/app_desktop                                          # Linux
open ./build/client/src/app_desktop.app                                 # macOS

# 3. mobile (Android APK or Win preview)
powershell scripts/build_android_apk.ps1                                # Android APK
./build/client/src/Debug/app_mobile.exe                                 # Windows phone-shaped preview

# 4. CLI / no-Qt
./build/client/src/Debug/app_chat.exe --user alice --password alice_pw --device dev_alice_win

# 5. native TLS direct (Windows Schannel)
./build/client/src/Debug/app_chat.exe --user alice --password alice_pw \
    --device dev_alice_win --port 8443 --tls --tls-insecure --tls-server-name localhost

# 6. browser — open http://127.0.0.1:8080/ after step 1's --web-port

# 7. Docker — dev SQLite/PG, or full production stack
wsl bash -lc "cd /mnt/.../telegram && docker compose -f deploy/docker/docker-compose.yml up --build telegram-server"
wsl bash -lc "docker compose -f deploy/docker/docker-compose.yml --profile postgres --profile tls up postgres telegram-server-postgres telegram-tls-proxy-postgres"
wsl bash -lc "docker compose -f deploy/docker/docker-compose.yml --env-file deploy/docker/.env --profile production --profile monitoring up --build -d"
```

## Capabilities (current state)

### Chat / messaging

- text + reply + forward + edit + delete + reactions + pin
- conversations: create / add / remove participants; per-message read markers
- **incremental sync** with cursors + version vectors + bounded older-history pagination
- **conversation_updated** push so being added to a group lands without manual sync
- **block + per-conversation mute** (M98) — gates 1:1 send, leaves group fanout untouched
- **server-side drafts** (M99) — MESSAGE_SEND auto-clears
- **per-user pinned + archived chats** (M100) surfaced via conversation_sync
- **profile + group avatars** (M101) via attachment_id pointers
- **polls** (M102) — create / vote / close, single + multi-choice, POLL_UPDATED fanout
- **per-conversation owner / admin / member roles** (M103) — gated add/remove, legacy 1:1 backwards compat
- contacts (directed), user search, message search across accessible conversations
- attachments: small inline (≤1 MB) + **chunked upload up to 64 MB** with **byte-level progress** in app_desktop (M88 / M126)
- **CJK / emoji / surrogate-pair UTF-8** round-trips on the C++ client (M72)

### Authentication / sessions

- username + password (PBKDF2-SHA256 stdlib only); registration flow
- **phone-number + OTP** sign-in (M90) — 6-digit codes, 5-min TTL, 30-sec
  resend cooldown; pluggable Sender (MockSender default, real SMS via PA-009)
- **TOTP 2FA** (M94) — RFC 6238 stdlib-only; opt-in per user; `LOGIN_REQUEST`
  enforces `two_fa_code` once enabled
- **rate limiting** on REGISTER / PHONE_OTP / MESSAGE_SEND / PRESENCE_QUERY /
  attachment send (M93)
- `--session-ttl-seconds` bound + heartbeat refresh
- device management: list / trust / untrust / revoke (with current-device guard)
- **GDPR-style export + delete** (M95) — full snapshot export; password+TOTP-gated delete tombstones authored messages
- **Redis-backed AuthService session cache** (M117) — `resolve_session` cache fast path with TTL eviction; falls back transparently to in-memory state on miss / transport failure

### Presence

- TTL-based online state (default 30 s); heartbeat refresh
- **PRESENCE_UPDATE push** fan-out on offline↔online transitions (M78)
- **Redis-backed PresenceService cache** (M116) — `is_user_online` / `last_seen_ms` /
  `query_users` flow through a single resolver with cache fast path; touch /
  notify_session_started / revoke_device / transitions refresh or invalidate

### Push notifications

- per-device push token register/unregister/list (M84)
- offline-recipient mock-dispatch hook on `MESSAGE_SEND` (M84)
- `PushDispatchWorker` drains the mock queue per platform via pluggable
  `Transport` (M91): `LogOnlyTransport` default · `FakeTransport` for tests ·
  `FCMHttpTransport` (FCM v1, stdlib `urllib`, dry_run when no bearer token)
- Browser PWA service worker stub (M124) — `/sw.js` registered on login;
  ready to receive web push subscriptions when PA-008 lands

### Voice / video calls (M109 / M127 / M128)

- Signaling FSM: `ringing → accepted/declined/canceled/ended` with
  `CallSessionService` + 5 typed errors. Per-call AES-256-GCM key minted on
  accept, ridden in `CALL_RENDEZVOUS_INFO`.
- Media plane: audio frames pack a 12-byte header (codec_id, channels,
  sample_rate/100, samples_per_frame, sequence) inside the AEAD-sealed
  `RelayPeerSession` byte stream.
- Codec abstraction (`server/server/media_codec.py`): `PassThroughCodec`
  default + `OpusCodec` stub gated on PA-012 (libopus / opuslib).
- Capture/playback abstraction (`server/server/media_io.py`):
  `AudioSource`/`AudioSink` Protocol with `SyntheticAudioSource`
  (deterministic 16-bit PCM sine wave) + `MemoryAudioSink` for tests.
  Real platform capture/playback (CoreAudio / WASAPI / ALSA / AAudio) is
  the next deliverable when PA-012 lands.
- UI: `app_desktop` Settings → Call page; `app_mobile` Settings → Call
  page; browser call dialog. All wire `CALL_INVITE/ACCEPT/DECLINE/END`
  via the bridge and surface state transitions in a log.

### Remote control (ATLAS-M71 / M105 / M106 / M108)

- Full state machine: invite → approve/reject/cancel/terminate/disconnect → rendezvous
- **C++ `ControlPlaneClient` covers all 8 remote-control RPCs** (M76)
- UDP media plane: per-session auth + frame_chunk subscribe + relay + synthetic
  screen source
- **`ReliableChannel` integrated into UDP relay** (M105) — peer-side reliability
  (REL/NAK/ACK seq packets) over the dumb forwarder; `RelayPeerSession`
  composes everything into a peer-to-peer reliable byte stream
- **AES-256-GCM AEAD on every reliable packet** (M106) — per-session key
  minted by `request_rendezvous`, ridden in `RemoteRendezvousInfoPayload.relay_key_b64`;
  intercepted bytes never reveal plaintext
- **In-product Qt invite/approve/reject/cancel/terminate/rendezvous UI**
  (M108) — desktop Settings → Remote page + `app_mobile` RemoteControlPage

### Storage / persistence

- JSON file (`--state-file`), SQLite (`--db-file`), or PostgreSQL (`--pg-dsn`)
- PostgreSQL repository: users / devices / sessions / conversations / messages /
  conversation change logs / contacts / attachments / remote sessions, with
  schema-version rows and app-level backup/restore round-trip
- **Per-entity transactional methods** (M129): `upsert_user` / `upsert_session` /
  `delete_session` / `upsert_remote_session` use `INSERT ... ON CONFLICT ... DO UPDATE`
  in their own short transaction. Wiring AuthService / ChatService to call
  these instead of the legacy snapshot `save()` is a focused future milestone.
- `AttachmentBlobStore` boundary stays object-store-ready (filesystem today)
- **Redis hot-state cache bridge** (M111) with `FakeRedisTransport` default
  for dev/tests + `RedisHttpTransport` stub gated on PA-011 (Upstash-shaped
  REST gateway)

### Transport security

- native TLS on the control plane (`--tls-cert-file` + `--tls-key-file`)
- C++ direct TLS via Schannel (`--tls`/`--tls-insecure`/`--tls-server-name`)
  — Windows-only (Linux/macOS app_chat skip via `validate_cpp_tls_client.py`'s
  `NEEDS_PLATFORM` gate)
- nginx stream TLS termination for SQLite (8443) and PostgreSQL (8444); both
  paths are live-verified end-to-end
- **HTTP-aware nginx reverse proxy** for the browser client (M115) —
  `/ws` WebSocket upgrade, `/healthz` passthrough to the observability sidecar,
  static `/` + `/app.js`, 80 → 443 redirect with ACME slot

### Browser client (M110 / M123 / M124)

- stdlib-only RFC-6455 WebSocket bridge (`server/server/web_bridge.py`);
  every text frame is a JSON envelope dispatched through the same path as
  the TCP control plane
- 3-pane single-page UI (`server/web/index.html`, `app.js`): sidebar with
  chat list + selectable conversations, center pane with selected chat,
  composer with **attachment upload + per-bubble download** (`atob` /
  `Blob` round-trip via `attachment_fetch_request`)
- Voice/video call dialog (invite/accept/decline/end) backed by the same
  CALL_* RPCs the desktop and mobile clients use
- PWA service worker (`/sw.js`) + manifest (`/manifest.webmanifest`) — push
  notification contract in place; designer-supplied icon assets are the
  next deliverable

### Packaging

- Windows: Inno Setup installer (`scripts/package_windows_desktop.ps1 -Installer`),
  unsigned today (signing = PA-005)
- Android: arm64-v8a APK via Qt for Android (`scripts/build_android_apk.ps1`),
  unsigned today (keystore = PA-005)
- macOS: `.app` bundles for `app_desktop` + `app_mobile` with **macdeployqt
  POST_BUILD** auto-embedding Qt frameworks (M113); non-fatal wrapper (M118)
  so a Homebrew Qt missing optional modules (QtPdf / QtSvg / QtVirtualKeyboard)
  emits a warning and the build continues
- iOS: scaffold-only (Info.plist + CMake guard); needs PA-010
- Linux: cmake + system Qt 6 build (`deploy/linux/README.md`); `.desktop`
  entry shipped, packaging (`.deb` / `.rpm` / AppImage) deferred

### Operations / observability (M92 / M115)

- **Structured logging** — JSON-line emission to any stream; default stderr
- **Prometheus metrics** — `/metrics` endpoint on a sidecar HTTP server
  (`--metrics-port 9100`); default counters: `dispatch_requests_total`,
  `dispatch_request_duration_seconds`, `messages_sent_total`,
  `attachments_uploaded_total`, `phone_otp_requests_total`,
  `phone_otp_verifications_total`, `rate_limited_total`, `active_sessions`
- **Health probe** — `/healthz` on the same sidecar; pluggable `HealthCheck`s
- **Production docker-compose profile** (`production`) with healthchecked
  `telegram-server-prod` (TCP + WS + sidecar, restart=always) + `nginx-web`
  (TLS termination + WS upgrade reverse proxy) + healthchecked `postgres`;
  optional `monitoring` profile adds Prometheus that scrapes the sidecar
  every 15 s; `deploy/docker/production.env.example` documents every env
  knob + PA-008/009/011 procurement placeholders

## Verification

`scripts/_sweep_validators.py` runs every `validate_*.py` (~70 in-process
validators, ~280 scenarios) with three skip categories:
- `SKIP_EXTERNAL` — needs Docker / live PostgreSQL / live TLS proxy (4 today)
- `SKIP_NO_BINARY` — backing C++ binary not built on this host
- `SKIP_PLATFORM` (M119) — Windows-only validators on POSIX runners

CI runs the same sweep + 6 build/verify jobs on every push.

```bash
python scripts/_sweep_validators.py             # full local sweep
python scripts/validate_desktop_smoke.py        # Qt desktop smoke (Windows)
python scripts/validate_call_session.py         # voice/video FSM + AEAD audio frames
python scripts/validate_media_codec.py          # codec abstraction E2E
python scripts/validate_media_aead.py           # AES-256-GCM relay round-trip
python scripts/validate_reliable_relay.py       # ReliableChannel over RELAY
python scripts/validate_presence_cache.py       # PresenceService Redis fast path
python scripts/validate_auth_cache.py           # AuthService Redis fast path
python scripts/validate_web_bridge.py           # WS handshake + PWA assets
python scripts/validate_production_compose.py   # docker-compose production profile shape
python scripts/validate_chunked_upload.py       # 5 MB chunked upload byte-exact
python scripts/validate_postgres_repository.py --pg-dsn postgresql://...
python scripts/validate_tls_proxy_smoke.py --port 8444 --device dev_pg_smoke
```

`build-verify/client/src/Debug/json_parser_test.exe` (9/9) and
`app_desktop_store_test.exe` (20/20) are the native C++ test binaries; they
also run on Linux + macOS.

## Pending external dependencies

The codebase is feature-complete for every milestone it claims; the only
items still gated on user action are credential / cost / hardware decisions:

- **PA-005** — Authenticode certificate (Windows) + Apple Developer + Android
  keystore for signed installer / APK / `.app` distribution
- **PA-008** — FCM service-account JSON / APNs token to flip
  `FCMHttpTransport.dry_run = False` and reach real device wake-up channels
- **PA-009** — Twilio account SID + auth token (or Aliyun SMS) to replace
  `MockSender` and deliver phone OTP codes via real SMS
- **PA-010** — macOS host running Xcode 15+ + Qt for iOS for the iOS build
  (also lets a real Mac runner verify the macdeployqt-embedded `.app`)
- **PA-011** — Real Redis endpoint + auth token (Upstash / ElastiCache REST
  gateway / self-hosted) to flip `RedisHttpTransport.dry_run = False`
- **PA-012** — `libopus` / `opuslib` library so `OpusCodec` can leave dry_run
  and call sites can encode real Opus frames

See [`.idea-to-code/telegram-platform/08-atlas-task-library.md`](.idea-to-code/telegram-platform/08-atlas-task-library.md)
for the full backlog. Tracked future engineering work (no PA needed):

- **AuthService / ChatService callsite refactor** to route writes through
  M129's `upsert_*` per-entity transactional methods instead of the
  snapshot `save()` (the methods exist; the integration is the deferred
  follow-up)
- **Real audio capture / playback** (CoreAudio / WASAPI / ALSA / AAudio)
  once PA-012 lands so OpusCodec can encode device audio
- **Native iOS UI tweaks** (safe-area insets, iOS HIG) once a real device
  runs the QML phone shell
- **macOS `.dmg` packaging + notarization** via `macdeployqt -dmg` + `xcrun notarytool`
- **Designer-supplied PWA icon set** for `/icons/*` so the browser client
  can install with a real icon and notifications can show a branded badge
