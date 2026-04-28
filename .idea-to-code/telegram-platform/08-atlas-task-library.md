# Project Task Library

Status date: 2026-04-28

## Operating Rules

- Chat updates and reports about delivery work use the `[idea-to-code]` prefix from the idea-to-code skill itself. No other speaker prefix is required.
- This file is the project-local task backlog: prioritized tasks, REQ-ID mapping, and pending external actions. The idea-to-code delivery bundle remains under `.idea-to-code/telegram-platform/`.
- External side effects stay in Pending Actions until confirmed: Docker start/stop, deployment, network pulls, git push, package signing, production certificate creation, and destructive cleanup.
- Each implementation task must map to a REQ-ID and checkpoint in this bundle.
- Prefer static/local validators before live integration.

## Current Delivery Plan

1. M66 PostgreSQL TLS proxy coverage: ✅ static validation in place; live smoke pending PA-001/PA-002.
2. M67 C++ TLS client transport parity: ✅ direct TLS login + sync verified end-to-end on build-verify.
3. M68 Schannel credential fix: ✅ explicit SCHANNEL_CRED resolves SEC_E_NO_CREDENTIALS; smoke green.
4. M69 Deployment hardening acceptance sweep: rerun TLS, packaging, SQLite, PostgreSQL, and desktop smoke validators; live Docker checks remain pending until approved.

## Task Backlog

| ID | Priority | State | Requirement | Task | Verification | External side effects |
|---|---:|---|---|---|---|---|
| ATLAS-M66 | P0 | in_progress | REQ-TLS-PG-PROXY | Add PostgreSQL-backed Docker TLS proxy profile and static validation. | `python scripts\validate_tls_deployment_config.py`; `docker compose ... config` only if approved/available. | Live `docker compose up` and TLS proxy smoke on 8444 pending approval. |
| ATLAS-M67 | P0 | done | REQ-TLS-CPP-CLIENT | Add direct TLS client transport parity for C++ desktop/CLI without changing UI code. | M68 fix verified: validate_cpp_tls_client.py 2/2, e2e 3/3, store 20/20. | None — runtime acceptance achieved via explicit SCHANNEL_CRED. |
| ATLAS-M68 | P0 | done | REQ-TLS-CPP-CLIENT,REQ-TLS-CONTROL-PLANE,REQ-VALIDATION | Resolve Schannel `SEC_E_NO_CREDENTIALS` by passing explicit SCHANNEL_CRED to AcquireCredentialsHandleW. | Build clean, TLS smoke + chat E2E + desktop store + TLS deployment static all pass. | None. |
| ATLAS-M69 | P1 | planned | REQ-VALIDATION | Deployment hardening acceptance sweep (full run of validate_* scripts) after TLS direct-client lands. | TLS validators, package validator, desktop smoke, PostgreSQL validators. | Docker container lifecycle and network pulls pending approval. |
| ATLAS-M70 | P1 | done | REQ-WINDOWS-PACKAGE-STAGING | Inno Setup installer with -Installer switch and validate_windows_installer.py 5/5; signing gated on PA-005. | Real .exe + .sha256 produced; static validator green. | None for build; PA-005 for Authenticode signing. |
| ATLAS-M71 | P2 | planned | REQ-REMOTE-LIFECYCLE | Resume remote-control runtime path after chat/deployment hardening. | Remote session validators and media-plane tests. | None expected until live multi-client smoke. |
| ATLAS-M81 | P1 | done | REQ-VALIDATION (Android prep) | Qt for Android prep landed: AndroidManifest skeleton, deploy/android/README.md, validate_android_prep.py covers 9 static scenarios. | Static validator green; APK now produced. | None. |
| ATLAS-M83 | P1 | done | REQ-VALIDATION (Android APK) | Real arm64-v8a APK built via Qt for Android using D:\android\sdk + JDK 21. scripts/build_android_apk.ps1 wraps the toolchain. | scripts/build_android_apk.ps1 + validate_android_prep.py 9/9. APK at build-android/.../android-build-release-unsigned.apk (11 MB). | PA-005 keystore for signing remains. |

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

- M82 closed the deployment loop: live PostgreSQL TLS proxy smoke is verified end-to-end (PA-001/PA-002/PA-003 all DONE on 2026-04-28).
- Outstanding Pending Actions: PA-005 (Authenticode cert for Windows installer signing), PA-007 (Android SDK + NDK + JDK 17 install).
- Native TLS handshake (M67/M68) and PostgreSQL repository (M82) are both production-grade verified now.
