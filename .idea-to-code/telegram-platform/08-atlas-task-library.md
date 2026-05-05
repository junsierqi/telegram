# Project Task Library

Status date: 2026-05-04

## Operating Rules

- Chat updates and reports about delivery work use the `[idea-to-code]` prefix from the idea-to-code skill itself. No other speaker prefix is required.
- This file is the project-local task backlog: prioritized tasks, REQ-ID mapping, and pending external actions. The idea-to-code delivery bundle remains under `.idea-to-code/telegram-platform/`.
- External side effects stay in Pending Actions until confirmed: Docker start/stop, deployment, network pulls, git push, package signing, production certificate creation, and destructive cleanup.
- Each implementation task must map to a REQ-ID and checkpoint in this bundle.
- Prefer static/local validators before live integration.

## Current Bundle Snapshot

- Bundle: `.idea-to-code/telegram-platform`
- State: `in_progress`
- Current focus: Telegram Desktop original-screenshot 1:1 UI restoration
- Next gate: login welcome / QR / phone reference states move from structural parity toward screenshot-matched GUI evidence
- Verify: `python C:\Users\junsierqi\.codex\skills\idea-to-code\scripts\manage_delivery_bundle.py verify --root . --slug telegram-platform` passes with 91 requirements, 0 problems, 0 blockers.
- Latest checkpoint: `Desktop UI parity expansion 1-6` passed. Current release-candidate work has local gates for RC-001/003/004/005/006; next unblocked product work is deeper original-screenshot UI restoration.

## Recently Shipped Capability Groups

- **Transport / TLS / deployment**: PostgreSQL Docker TLS proxy, native C++ direct TLS via Schannel, TLS proxy smoke, Docker production profiles, Windows Inno installer and package checksums.
- **Validation / CI**: full validator sweep harness, GitHub Actions jobs, platform skip logic, Linux desktop build, Windows + Android CI hardening.
- **Desktop Telegram parity**: 3-pane shell, Settings redesign, right info panel, left drawer, login/reconnect/no-network states, popup/menu/emoji/context surfaces, right-info tabs, productized Account/Privacy/Chat Tools entries, strict screenshot lock over generated GUI smoke states.
- **Chat completeness**: conversation updates, edit/delete UI, replies/forwards/reactions/pins, drafts, pinned/archived chats, avatars, polls, roles, block/mute, 2FA, account lifecycle.
- **Media / remote / calls**: ReliableChannel over UDP relay, AEAD media packets, Qt remote-control UI, voice/video signaling and AEAD media skeleton.
- **Mobile / web / packaging**: Qt Quick mobile shell, Android APK build, browser client bridge/PWA stub, macOS/iOS scaffolding.
- **Persistence / hot state**: SQLite, PostgreSQL repository path, per-entity PG methods, Redis bridge plus Presence/Auth cache wiring.

## Current Open Backlog

| ID | Priority | State | Requirement | Task | Verification | External side effects |
|---|---:|---|---|---|---|---|
| RC-001 | P0 | done | REQ-VALIDATION / release | Active `build-ui-verify` `app_mobile` AutoMoc/build path passes; stale `build-local` cache still points at an old source dir and is not the release gate. | `cmake --build build-ui-verify --config Debug --target app_mobile`; mobile validators; bundle verify. | None. |
| RC-002 | P0 | blocked-external | REQ-WINDOWS-PACKAGE-STAGING / REQ-WINDOWS-PACKAGE-CHECKSUMS | Produce signed Windows installer/package once PA-005 is procured. | `scripts\package_windows_desktop.ps1 -BuildDir <build> -Installer`; `scripts\validate_windows_package.ps1`; signature verification. | PA-005 signing certificate and signtool setup. |
| RC-003 | P1 | done | REQ-DESKTOP-SCREENSHOT-PARITY / REQ-DESKTOP-UI-VERIFY | Original Telegram reference screenshots are mapped through `reference-map.json` crop sets with per-state tolerances; generated GUI baseline remains separately locked. | `python scripts\validate_desktop_gui_smoke.py`; `python scripts\validate_desktop_reference_map.py`; `python scripts\validate_desktop_image_diff.py`. | None for local mapped crops; stricter pixel parity still needs designer-approved tolerances. |
| RC-004 | P1 | done | REQ-DESKTOP-SCREENSHOT-PARITY | Desktop popup/menu states now cover top overflow menu, attachment menu, emoji/sticker panel, and message context menu. | `python scripts\validate_desktop_popup_states.py`; `python scripts\validate_desktop_gui_smoke.py`. | None. |
| RC-005 | P1 | done | REQ-C1-DESKTOP-GUI / REQ-CHAT-CORE | Desktop `ControlPlaneClient` wrappers and Advanced settings UI cover server-backed account export/delete, block/mute, drafts, pin/archive, 2FA, phone OTP, polls, and avatar update. | `python scripts\validate_desktop_smoke.py` includes RC-005 runtime markers. | PA-009 only for real SMS; mock OTP flow can ship locally. |
| RC-006 | P1 | done | REQ-C4-DURABLE-PERSISTENCE / REQ-POSTGRES-REPOSITORY-BOUNDARY | Existing per-entity PG methods are now used for existing-device session writes and remote-session lifecycle writes; snapshot fallback remains where no focused method exists. | `python scripts\validate_pg_transactional.py`; desktop and remote-session smokes. | Needs PostgreSQL service only for live PG smoke. |
| RC-007 | P2 | blocked-external | REQ-CHAT-CORE / push | Turn push dispatch from dry-run/stub into real FCM/APNs delivery. | Push dispatch validator with fake transport remains local; live token smoke after credentials. | PA-008 FCM/APNs credentials. |
| RC-008 | P2 | blocked-external | REQ-CHAT-CORE / phone OTP | Turn mock phone OTP into real SMS delivery. | `validate_phone_otp.py` plus provider integration smoke with approved test number. | PA-009 SMS gateway credentials and cost approval. |
| RC-009 | P2 | blocked-external | mobile / iOS | Build and smoke the iOS scaffold on a real Apple host. | Xcode/Qt for iOS build, app launch smoke, mobile QML smoke where possible. | PA-010 macOS + Xcode + Qt for iOS. |
| RC-010 | P2 | blocked-external | persistence / hot state | Run Redis bridge against a real Redis endpoint and tune production TTL/failure behavior. | Redis cache validator against real endpoint plus Auth/Presence smoke. | PA-011 Redis endpoint and token. |
| RC-011 | P2 | blocked-external | voice/video | Replace `PassThroughCodec` with real Opus codec path and add platform capture/playback follow-up. | Codec validator, call session validator, desktop/mobile/web call smoke. | PA-012 libopus/opuslib and later platform media work. |
| RC-012 | P3 | open | attachments / storage | Replace filesystem blob store with a true object-store implementation or adapter while preserving `AttachmentBlobStore` contract. | Attachment validators plus restart/migration smoke. | Object-store credentials only for live integration. |
| UI-001 | P0 | active | REQ-DESKTOP-SCREENSHOT-PARITY / REQ-DESKTOP-UI-VERIFY | Restore original login welcome, QR login, and phone-number screens toward 1:1 Telegram Desktop layout while preserving local username/password/server advanced fields. | Static login reference validator, `app_desktop` build, GUI smoke screenshot capture where available. | None. |
| UI-002 | P1 | open | REQ-DESKTOP-SCREENSHOT-PARITY | Add GUI screenshot states for top overflow, attachment menu, emoji/sticker panel, message context menu, login failure, QR, and phone screens. | Extended `validate_desktop_gui_smoke.py` plus image diff/reference-map entries. | None unless exact reference assets are refreshed. |
| UI-003 | P1 | open | REQ-DESKTOP-SCREENSHOT-PARITY / REQ-C1-DESKTOP-GUI | Deepen right info panel, chat bubbles, poll/file/system rendering, and settings subpages against the original reference screenshots. | Static validators plus screenshot diff for each restored state. | None. |

## Pending Actions

| ID | Created | Action | Reason | Confirmation needed |
|---|---|---|---|---|
| ~~PA-001~~ | 2026-04-27 → resolved 2026-04-28 | `docker compose -f deploy/docker/docker-compose.yml --profile postgres --profile tls up -d postgres telegram-server-postgres telegram-tls-proxy-postgres` | Start live PostgreSQL-backed TLS proxy stack for integration smoke. | DONE — required dockerd HTTP proxy drop-in (10.20.11.30:10809) and ARG/ENV plumbing in server.Dockerfile so pip install reaches pypi.org. |
| ~~PA-002~~ | 2026-04-27 → resolved 2026-04-28 | `python scripts\validate_tls_proxy_smoke.py --port 8444 --device dev_tls_proxy_pg_smoke` | Verify real login through PostgreSQL TLS proxy after PA-001. | DONE — `tls proxy smoke ok: user=u_alice session=sess_1`; Postgres repo + backup/restore + docker deploy validators all green against the live stack. |
| ~~PA-003~~ | 2026-04-27 → resolved 2026-04-28 | `docker compose -f deploy/docker/docker-compose.yml --profile postgres --profile tls config` | Static compose expansion may depend on local Docker/WSL availability. | DONE — implicitly verified by PA-001 succeeding with profiles postgres+tls. |
| PA-005 | 2026-04-28 | Acquire Authenticode certificate, then re-run `scripts\package_windows_desktop.ps1 -BuildDir build-verify -Installer` after uncommenting `SignTool=` in `deploy/windows/telegram_like_desktop.iss.template`. | Code-sign the Inno Setup installer so SmartScreen / Defender accept it without warning. | Yes — needs cert procurement + signtool config |
| ~~PA-007~~ | 2026-04-28 → resolved 2026-04-28 | `powershell scripts\build_android_apk.ps1` (one-liner, wraps qt-cmake + cmake --target apk + manifest+gradle plumbing). | Produce a real Android APK. | DONE — toolchain found at D:\android\sdk (NDK 30, build-tools 37, platform android-37.0 → junctioned to android-37, JDK 21.0.11); 11.4 MB unsigned APK produced. |
| PA-008 | 2026-04-28 | Acquire FCM service-account JSON (or APNs token), wire `httpx` POST in a new push delivery worker that drains `PushTokenService.pending_deliveries` on a tick. | Send the mock pushes the server already records to real device wake-up channels. | Yes — needs FCM/APNs credential procurement. |
| PA-009 | 2026-04-28 | Acquire Twilio account SID + auth token (or Aliyun SMS), wire real HTTP POST in a TwilioSender that replaces MockSender in PhoneOtpService. | Deliver phone OTP codes via real SMS instead of stderr/log. | Yes — needs SMS gateway credential + cost approval. |
| PA-010 | 2026-05-04 | Provide macOS host with Xcode 15+ and Qt for iOS. | Build and smoke the iOS scaffold; current Windows/Linux environment cannot validate it. | Yes — needs Apple hardware/cloud Mac and installed toolchain. |
| PA-011 | 2026-05-04 | Provide real Redis endpoint and token. | Exercise Redis-backed Auth/Presence hot-state cache against production-like transport instead of FakeRedis. | Yes — needs Redis service and credential. |
| PA-012 | 2026-05-04 | Provide `libopus` / `opuslib` or approved codec dependency. | Move voice/video calls beyond `PassThroughCodec` / stub codec into real encoded audio path. | Yes — needs dependency approval/install. |

## Notes

- 151 milestones recorded; 91 REQs all covered; bundle verify ok, 0 problems, 0 blockers.
- The old `ATLAS-M71 planned` row is superseded by later ReliableChannel, AEAD, and Qt remote-control UI milestones. Remote-control follow-up now belongs under RC/full-product polish, not as a stale planned core task.
- Most remaining work is either release-candidate hardening, UI parity depth, production provider wiring, or external credential/toolchain procurement.
