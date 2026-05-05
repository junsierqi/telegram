# PRD

## Goal

- Continue the Telegram-like platform toward a verified Telegram Desktop parity target: a runnable Qt desktop client backed by the Python control-plane server, with screenshot-driven UI restoration, real local chat/account flows where implemented, and explicit blockers for provider-backed or platform-only features.

## Users

- Developers validating local desktop/server behavior.
- Operators validating Docker, TLS, SQLite, and PostgreSQL deployment paths.
- Reviewers comparing the desktop client against the original Telegram Desktop reference screenshots in `artifacts/desktop-reference-originals/`.

## Main Flows

- Desktop startup/login: first-run opens a Telegram-style login/onboarding surface; remembered-login startup without backend stays in the main shell with loading/no-network state.
- Desktop chat shell: three-pane Telegram-like layout with conversation list, center chat timeline/composer, and right-side info panel.
- Chat/account operations: local server-backed login/register, contacts, group/channel creation, message send/sync, attachments, edit/delete/reply/forward/reactions, devices, 2FA, phone OTP mock flow, account export/delete, block/mute, drafts, pin/archive, avatars, and polls where local server support exists.
- Verification loop: implement small UI/feature slices, run static validators, build `app_desktop`, run smoke tests, and update the delivery bundle.
- External actions: Docker startup, git push, release signing, production push/SMS, Redis, iOS/macOS host, and codec/object-store provider work stay pending until explicitly confirmed or provisioned.

## Scope

- In scope: Qt Widgets desktop UI restoration, code-backed interaction entry points, local mock/provider-safe feature flows, validation scripts, delivery-bundle updates, and non-destructive local builds/tests.
- Out of scope for local-only slices: real SMS delivery, FCM/APNs live push, signed Windows release, production certificate automation, iOS build on non-Apple hosts, real Redis endpoint smoke, and production media codec capture/playback.

## Functional Requirements

- REQ-DESKTOP-SCREENSHOT-PARITY: Desktop UI surfaces are restored state-by-state against the original Telegram Desktop reference screenshots.
- REQ-DESKTOP-UI-VERIFY: Each restored UI state has static and/or GUI smoke validation so visual work does not regress core chat behavior.
- REQ-C1-DESKTOP-GUI: Desktop client exposes the implemented server-backed chat/account capabilities through product-facing UI, not only debug controls.
- REQ-CHAT-CORE: Chat flows remain backed by the control-plane protocol and local state store.
- REQ-C4-DURABLE-PERSISTENCE: SQLite/default and PostgreSQL repository paths preserve sessions, conversations, messages, contacts, attachments, and remote-session state as implemented.
- REQ-POSTGRES-REPOSITORY-BOUNDARY: Focused PostgreSQL writes are used where repository methods exist; snapshot fallback remains explicit where no focused method exists.
- REQ-ATLAS-TASK-LIBRARY: The task library remains the human-readable source of current priorities, evidence, blockers, and pending external actions.

## Technical Shape

- C++20/Qt desktop client remains in `client/src/app_desktop`.
- Shared C++ transport wrappers remain in `client/src/transport`.
- Python stdlib server remains in `server/server`, with SQLite default, optional PostgreSQL repository, JSON state fallback, and provider stubs for external services.
- The durable delivery bundle remains `.idea-to-code/telegram-platform`.
- Screenshot references live under ignored local `artifacts/`; validators must run strict comparisons when artifacts exist and skip cleanly when ignored artifacts are absent.
- 1:1 Telegram Desktop UI restoration proceeds screenshot-state by screenshot-state. Structural/static parity is not the same as final pixel parity; pixel tolerances require committed or locally available reference assets and designer-approved thresholds.

## Current Architecture Status

- Implemented locally: desktop three-pane shell, Telegram-style conversation rows, left account drawer, centered settings modal, first-run login modal, remembered-login no-network state, right info panel, search/create/contact dialogs, attachment/menu/emoji/context-menu surfaces, productized Account/Privacy/Chat Tools entries, advanced RPC wrappers, rich message bubble visual surfaces, no-seed startup mode, desktop GUI smoke, image diff, reference-map validation, and focused PG session/remote-session persistence.
- Partially implemented: phone/QR login UI states, poll/file/system bubble visual depth, screenshot coverage for popup/login sub-states, and strict external-reference pixel parity.
- Blocked externally: signed Windows installer, real FCM/APNs push, real SMS provider, iOS host, real Redis endpoint, real Opus/media dependencies, and object-store credentials.

## Acceptance

- Local build/test evidence is recorded for every implementation slice.
- Documentation reflects code reality: implemented, partial, and blocked work are separated.
- The delivery bundle verifies with no uncovered open requirements, or any uncovered work is explicitly blocked/deferred.
- No git push, Docker startup, signing, or live provider call is performed without explicit confirmation.
