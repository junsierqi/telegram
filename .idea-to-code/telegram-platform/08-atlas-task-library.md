# Project Task Library

Status date: 2026-04-28

## Operating Rules

- Chat updates and reports about delivery work use the `[idea-to-code]` prefix from the idea-to-code skill itself. No other speaker prefix is required.
- This file is the project-local task backlog: prioritized tasks, REQ-ID mapping, and pending external actions. The idea-to-code delivery bundle remains under `.idea-to-code/telegram-platform/`.
- External side effects stay in Pending Actions until confirmed: Docker start/stop, deployment, network pulls, git push, package signing, production certificate creation, and destructive cleanup.
- Each implementation task must map to a REQ-ID and checkpoint in this bundle.
- Prefer static/local validators before live integration.

## Recent shipped milestones (M66 → M85)

- **M66 / M82** PostgreSQL Docker TLS proxy + live PA-001/PA-002/PA-003 smoke (port 8444 → user=u_alice session=sess_1; Postgres repo + backup/restore + docker-deploy validators all green).
- **M67 / M68** Native C++ direct-TLS transport via Schannel (explicit SCHANNEL_CRED).
- **M69 / M79** Full validator sweep harness — `scripts/_sweep_validators.py` (41 in-process validators, ~200 scenarios).
- **M70 / M80** Windows Inno Setup installer (real `.exe` + `.sha256`; signing gated on PA-005).
- **M72** JSON `\uXXXX` Unicode + `ensure_ascii=False` for CJK / emoji round-trip on the C++ client.
- **M73 / M74** Telegram-style desktop redesign — 3-pane shell + 8-page Settings nav with QPainter avatar disc.
- **M75–M78** Protocol parity closure A→D (conversation_updated push + Edit/Delete UI; remote-control RPCs on ControlPlaneClient; dead enum + empty-controller cleanup; PRESENCE_UPDATE push fan-out).
- **M81 / M83** Qt for Android prep + real arm64-v8a APK (NDK 30, JDK 21, `scripts/build_android_apk.ps1`).
- **M84** Push notification protocol surface — register / unregister / list + offline-recipient mock dispatch.
- **M85** Mobile UI — Qt Quick / QML phone shell `app_mobile` (Win32 preview .exe + Android APK 20 MB).

## Open Task Backlog

| ID | Priority | State | Requirement | Task | Verification | External side effects |
|---|---:|---|---|---|---|---|
| ATLAS-M71 | P2 | planned | REQ-REMOTE-LIFECYCLE | Resume remote-control runtime path: integrate ReliableChannel into media_plane.py UDP, add Qt UI for invite/approve/host/view. | New remote-session validators + Qt smoke once a multi-client harness exists. | None until live multi-client smoke. |
| ATLAS-M87 | P1 | planned | REQ-VALIDATION (CI) | GitHub Actions workflow that runs `_sweep_validators.py` + Linux C++ build on every push. | Workflow file + green run on first push. | None. |
| ATLAS-M88 | P1 | planned | REQ-ATTACHMENTS | Chunked attachment upload (>1 MB) via init/chunk/complete RPCs; AttachmentBlobStore stitches chunks. | New `validate_chunked_upload.py` round-tripping a multi-MB file. | None. |
| ATLAS-M89 | P1 | done | REQ-VALIDATION (Linux desktop) | Real Linux build verified end-to-end on Ubuntu 24.04 (Qt 6.4 from apt). qt_policy + loadFromModule version compat fixes; deploy/linux scaffolding; ci.yml linux-desktop job. | validate_linux_desktop.py 5/5; WSL build of all 8 targets clean; json_parser_test 9/9 + app_desktop_store_test 20/20 on Linux. | None. |
| ATLAS-M90 | P1 | planned | new REQ-PHONE-OTP | Phone-number + OTP authentication path (Telegram-style sign-in). Server-side mock SMS first, real Twilio/Aliyun gateway via PA. | New protocol RPCs + validator. | PA for SMS gateway credential + cost approval. |
| ATLAS-M91 | P2 | done | REQ-CHAT-CORE | Pluggable PushDispatchWorker drains PushTokenService.pending_deliveries; LogOnlyTransport default + FakeTransport for tests + FCMHttpTransport stub (dry_run, urllib-based). | validate_push_dispatch.py 5/5 covering empty/per-platform/fallback/dry_run/end-to-end. | PA-008 only for the bearer token flow (real FCM POST); the worker itself ships now. |
| ATLAS-M92 | P2 | planned | new REQ-OBSERVABILITY | Structured logging + `/metrics` endpoint (Prometheus exposition format) + health probe distinct from port-open. | New validator hitting `/metrics`. | None. |
| ATLAS-M93 | P2 | planned | new REQ-RATE-LIMITING | Per-session rate limiting on MESSAGE_SEND / REGISTER_REQUEST / PRESENCE_QUERY. | Validator with synthetic burst. | None. |
| ATLAS-M94 | P3 | planned | new REQ-2FA | TOTP-based 2FA over the existing auth flow. | Validator drives provision + verify. | None. |
| ATLAS-M95 | P3 | planned | new REQ-ACCOUNT-DELETE | GDPR-style account deletion + data export. | Validator round-trips create → export → delete. | None. |

## Pending Actions

| ID | Created | Action | Reason | Confirmation needed |
|---|---|---|---|---|
| ~~PA-001~~ | 2026-04-27 → resolved 2026-04-28 | `docker compose -f deploy/docker/docker-compose.yml --profile postgres --profile tls up -d postgres telegram-server-postgres telegram-tls-proxy-postgres` | Start live PostgreSQL-backed TLS proxy stack for integration smoke. | DONE — required dockerd HTTP proxy drop-in (10.20.11.30:10809) and ARG/ENV plumbing in server.Dockerfile so pip install reaches pypi.org. |
| ~~PA-002~~ | 2026-04-27 → resolved 2026-04-28 | `python scripts\validate_tls_proxy_smoke.py --port 8444 --device dev_tls_proxy_pg_smoke` | Verify real login through PostgreSQL TLS proxy after PA-001. | DONE — `tls proxy smoke ok: user=u_alice session=sess_1`; Postgres repo + backup/restore + docker deploy validators all green against the live stack. |
| ~~PA-003~~ | 2026-04-27 → resolved 2026-04-28 | `docker compose -f deploy/docker/docker-compose.yml --profile postgres --profile tls config` | Static compose expansion may depend on local Docker/WSL availability. | DONE — implicitly verified by PA-001 succeeding with profiles postgres+tls. |
| PA-005 | 2026-04-28 | Acquire Authenticode certificate, then re-run `scripts\package_windows_desktop.ps1 -BuildDir build-verify -Installer` after uncommenting `SignTool=` in `deploy/windows/telegram_like_desktop.iss.template`. | Code-sign the Inno Setup installer so SmartScreen / Defender accept it without warning. | Yes — needs cert procurement + signtool config |
| ~~PA-007~~ | 2026-04-28 → resolved 2026-04-28 | `powershell scripts\build_android_apk.ps1` (one-liner, wraps qt-cmake + cmake --target apk + manifest+gradle plumbing). | Produce a real Android APK. | DONE — toolchain found at D:\android\sdk (NDK 30, build-tools 37, platform android-37.0 → junctioned to android-37, JDK 21.0.11); 11.4 MB unsigned APK produced. |
| PA-008 | 2026-04-28 | Acquire FCM service-account JSON (or APNs token), wire `httpx` POST in a new push delivery worker that drains `PushTokenService.pending_deliveries` on a tick. | Send the mock pushes the server already records to real device wake-up channels. | Yes — needs FCM/APNs credential procurement. |

## Notes

- 83 milestones recorded; 72 REQs all covered; bundle verify ok, 0 problems, 0 blockers.
- 41 in-process validators are green; 4 external-state validators were green at last live run (M82).
- Remaining external dependencies are PA-005 (signing cert) and PA-008 (FCM/APNs credential). Both block "shippable" but neither blocks further development.
- Tier 0 release-readiness still pending: iOS client, voice/video calls, large-file (M88 partial), phone-number OTP (M90 in backlog).
