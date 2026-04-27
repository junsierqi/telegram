# Execution Log

## Desktop contacts/groups UI (M49)

### Phase Goal

Close the most visible Telegram-like desktop gap after registration and attachments: expose contacts and group conversation management in the Qt desktop client.

### Requirement Understanding

The user wants `idea-to-code` to visibly drive a complete product phase, not only produce next-step suggestions. For this phase, the product outcome is a desktop UI that can list/add/remove contacts and create/manage group conversations using the already-verified server protocol.

### Completed Tasks

- Added C++ `ControlPlaneClient` group conversation RPCs for create, add participant and remove participant.
- Added Qt desktop contacts UI for refresh, add and remove contact by `user_id`.
- Added Qt desktop group UI for creating a group from comma-separated participant IDs.
- Added Qt desktop selected-conversation member controls for adding/removing a participant.
- Extended desktop smoke validation with contacts add/remove and group creation markers.

### Implementation Summary

- `client/src/transport/control_plane_client.h/.cpp`: added `ConversationActionResult`, conversation descriptor parsing reuse, and group management methods.
- `client/src/app_desktop/main.cpp`: added contacts panel, group creation controls, member management controls, async handlers and smoke flow coverage.
- `scripts/validate_desktop_smoke.py`: now requires contacts and group smoke success markers.
- `README.md`, `docs/architecture/current-state.md`, `docs/architecture/implementation-roadmap.md`: updated current capabilities and known gaps.

### Test Flow

- Built Debug with `cmake --build build-codex --config Debug`.
- Ran targeted validators for contacts and groups.
- Ran desktop smoke against the real `app_desktop.exe`.
- Ran desktop store regression test.
- Ran the full `scripts/validate_*.py` sweep.

### Test Results

- Debug build: PASS.
- `python scripts\validate_contacts.py`: 8/8 PASS.
- `python scripts\validate_group_conversations.py`: 6/6 PASS.
- `python scripts\validate_desktop_smoke.py`: 1/1 PASS, including contacts and group markers.
- `app_desktop_store_test.exe`: 11/11 PASS.
- Full `scripts\validate_*.py` sweep: 25/25 scripts PASS, 149 scenarios PASS.

### Acceptance

PASS. Desktop contacts/groups UI is accepted for the current MVP scope.

### Deferred Work And Risks

- Contacts UI uses raw `user_id` entry; user search/discovery and profile cards are deferred.
- Group UI is functional but minimal; no polished member list, confirmations, roles or admin policy.
- Message timeline is still debug-style transcript, not Telegram-like bubbles/status/timestamps.

### Next-Phase Recommendation

After acceptance, prioritize message timeline polish: timestamps, message status and basic bubble-like rendering. This will improve day-to-day Telegram-like feel more than deeper attachment or storage work.

## Desktop message timeline polish (M50)

### Phase Goal

Move the desktop message area from a debug transcript toward a basic Telegram-like timeline with visible time, direction and delivery/read state.

### Requirement Understanding

The user asked to continue with message timeline polish: timestamps, sent/read status and basic bubble-style rendering, while keeping the previous idea-to-code reporting discipline. The intended scope is UI polish backed by real protocol/store data, not only cosmetic string changes.

### Completed Tasks

- Added `created_at_ms` to server message send/attachment responses and conversation sync descriptors.
- Parsed `created_at_ms` and `read_markers` in the C++ `ControlPlaneClient`.
- Extended `DesktopChatStore` messages/conversations/cache with timestamps and read markers.
- Applied `message_read_update` pushes and incremental read-marker deltas in the desktop store.
- Replaced the old single-line debug transcript with basic inbound/outbound bubble-style rows, HH:MM timestamp labels, and sent/read/received status.
- Expanded `app_desktop_store_test` to verify timestamp/direction/status rendering and cache round-trip of read state.

### Implementation Summary

- `server/server/protocol.py`, `server/server/services/chat.py`: timestamped new text and attachment messages.
- `client/src/transport/control_plane_client.h/.cpp`: timestamp and read-marker parsing.
- `client/src/app_desktop/desktop_chat_store.h/.cpp`: read-marker state, cache persistence, read update push handling and bubble-like transcript rendering.
- `client/src/app_desktop/store_test.cpp`: 12/12 store coverage including timeline status.
- `README.md`, `docs/architecture/current-state.md`, `docs/architecture/implementation-roadmap.md`: updated capability and known-gap documentation.

### Test Flow

- Built Debug with `cmake --build build-codex --config Debug`.
- Ran store-level C++ timeline/cache assertions.
- Ran real desktop smoke against the Python TCP server.
- Ran targeted message regressions for read receipts, incremental sync, fanout, attachments and edit/delete.

### Test Results

- Debug build: PASS.
- `app_desktop_store_test.exe`: 12/12 PASS.
- `python scripts\validate_desktop_smoke.py`: 1/1 PASS.
- `python scripts\validate_read_receipts.py`: 6/6 PASS.
- `python scripts\validate_incremental_sync.py`: 8/8 PASS.
- `python scripts\validate_message_fanout.py`: 4/4 PASS.
- `python scripts\validate_attachments.py`: 11/11 PASS.
- `python scripts\validate_message_edit_delete.py`: 8/8 PASS.
- Full `scripts\validate_*.py` sweep: 25/25 scripts PASS, 149 scenarios PASS.
- Delivery bundle verify: PASS, 50 requirements covered.

### Acceptance

PASS. Desktop message timeline polish is accepted for the current MVP scope.

### Deferred Work And Risks

- Local pending/failed send states are still not modeled; current local outbound state starts at server-acknowledged `sent`.
- Read state is peer-read aggregate, not per-recipient detail for larger groups.
- Bubble rendering is still plain-text inside `QTextEdit`, not a custom rich chat cell/delegate.
- Legacy messages without `created_at_ms` display `--:--`.

### Next-Phase Recommendation

Prioritize profile/account polish or richer desktop navigation next. If continuing timeline work, the highest-impact follow-up is pending/failed send state plus a richer custom message list widget.

## Desktop timeline completion gaps (M51)

### Phase Goal

Close all timeline polish gaps explicitly listed after M50: pending/failed sends, group read details, rich bubble rendering and legacy timestamp handling.

### Requirement Understanding

The user asked to continue with all listed timeline leftovers, ordered by implementation priority. The correct order was to first protect message delivery state correctness, then improve read-status semantics, then improve rendering fidelity, and finally remove ambiguous missing-time UI for legacy data.

### Completed Tasks

- Added local pending message creation before the network RPC returns.
- Added server-ack resolution from `local_N` to real `msg_N` without advancing sync cursors for local-only messages.
- Added pending/failed local-send state with persisted error detail for text sends and attachment uploads.
- Added group read detail rendering: partial reads show `read by <user_ids>`, complete peer reads show `read by all`.
- Added rich HTML timeline rendering and switched the Qt message surface from `QPlainTextEdit` to `QTextBrowser`.
- Added explicit `legacy` timestamp fallback for messages without `created_at_ms`.

### Implementation Summary

- `client/src/app_desktop/desktop_chat_store.h/.cpp`: added pending/failed delivery state for text and attachment messages, local message lifecycle APIs, rich HTML timeline renderer, group read-detail status labels and legacy timestamp fallback.
- `client/src/app_desktop/main.cpp`: sends now create a pending local row immediately, resolve or fail it after the RPC, and render the timeline via `QTextBrowser::setHtml`.
- `client/src/app_desktop/store_test.cpp`: expanded store coverage from 12/12 to 16/16 for pending/failed, per-member group reads, rich HTML and legacy timestamps.
- `README.md`, `docs/architecture/current-state.md`, `docs/architecture/implementation-roadmap.md`: updated capability and known-gap documentation.

### Test Flow

- Built Debug with `cmake --build build-codex --config Debug`.
- Ran store-level C++ assertions for all four leftover areas.
- Ran real desktop smoke against the Python TCP server.
- Ran targeted message/sync regressions.

### Test Results

- Debug build: PASS.
- `app_desktop_store_test.exe`: 16/16 PASS.
- `python scripts\validate_desktop_smoke.py`: 1/1 PASS.
- `python scripts\validate_read_receipts.py`: 6/6 PASS.
- `python scripts\validate_incremental_sync.py`: 8/8 PASS.
- `python scripts\validate_message_fanout.py`: 4/4 PASS.
- `python scripts\validate_attachments.py`: 11/11 PASS.
- Full `scripts\validate_*.py` sweep: 25/25 scripts PASS, 149 scenarios PASS.
- Delivery bundle verify: PASS, 51 requirements covered.

### Acceptance

PASS. All listed M50 timeline leftovers are accepted for the current MVP scope.

### Deferred Work And Risks

- The rich renderer is still HTML inside `QTextBrowser`, not a virtualized custom message-list delegate.
- Attachment uploads now get pending/failed rows, but download/save failures still surface via transfer status rather than message rows.
- Legacy timestamps are labeled explicitly but cannot recover true historical send times.

### Next-Phase Recommendation

After full-suite verification, move to profile/account polish or richer desktop navigation/search.

## Profile/account and user discovery (M52)

### Phase Goal

Close the highest-impact “usable Telegram” account/discovery gap after timeline completion: users can manage their visible profile name and discover other users before adding contacts or creating conversations.

### Requirement Understanding

The user asked to continue autonomously on the most important missing Telegram-like capabilities. For this phase, the critical product outcome is a usable account identity surface and a search path from “I know a username/display name” to “I can find that person and add them as a contact.”

### Completed Tasks

- Added authenticated profile get/update protocol messages.
- Added authenticated user search protocol messages with self-exclusion, limit clamping, online state and contact-state flags.
- Added C++ `ControlPlaneClient` RPCs and typed result models for profile and user search.
- Added Qt desktop profile refresh/save controls.
- Added Qt desktop user search controls with online/contact result rendering.
- Extended desktop smoke validation and added a dedicated server-side profile/search validator.

### Implementation Summary

- `server/server/protocol.py`, `server/server/app.py`: new profile and user-search message types, payloads and dispatch behavior.
- `client/src/transport/control_plane_client.h/.cpp`: new `ProfileResult`, `UserSearchResult`, `profile_get`, `profile_update` and `search_users`.
- `client/src/app_desktop/main.cpp`: profile panel, search panel, async handlers and smoke coverage.
- `scripts/validate_profile_search.py`: 5 scenario server validator.
- `scripts/validate_desktop_smoke.py`: now requires profile and user-search markers.
- `README.md`, `docs/architecture/current-state.md`, `docs/architecture/implementation-roadmap.md`: updated current capability and remaining gaps.

### Test Flow

- Built Debug with `cmake --build build-codex --config Debug`.
- Ran dedicated profile/search server validator.
- Ran real desktop smoke against the Python TCP server.
- Ran targeted contacts, registration and desktop-store regressions.
- Ran the full `scripts\validate_*.py` sweep.

### Test Results

- Debug build: PASS.
- `python scripts\validate_profile_search.py`: 5/5 PASS.
- `python scripts\validate_desktop_smoke.py`: 1/1 PASS, including profile and user-search markers.
- `python scripts\validate_contacts.py`: 8/8 PASS.
- `python scripts\validate_registration.py`: 7/7 PASS.
- `app_desktop_store_test.exe`: 16/16 PASS.
- Full `scripts\validate_*.py` sweep: 26/26 scripts PASS, 154 scenarios PASS.

### Acceptance

PASS. Profile/account and user discovery are accepted for the current MVP scope.

### Deferred Work And Risks

- Search is a simple substring scan over in-memory users; production needs indexing/ranking/rate limits.
- Desktop search results are read-only text rows; richer selection/cards and one-click add are deferred.
- Profile surface only updates display name; avatar, username changes, bio and privacy settings are deferred.

### Next-Phase Recommendation

Continue with desktop navigation/search: chat list filtering, message search in the selected conversation and keyboard-friendly navigation. This is now the largest remaining day-to-day usability gap before deeper production backend work.

## Desktop navigation/search (M53)

### Phase Goal

Close the next highest daily-usage gap after account discovery: users can narrow the chat list and search within the selected conversation without relying on raw debug transcripts or manual scrolling.

### Requirement Understanding

The user asked to keep moving toward a usable Telegram-like desktop client. For this phase, the practical outcome is local navigation/search: filter conversations, search messages in the active chat, move between matches and see the current match highlighted in the rich timeline.

### Completed Tasks

- Added local `DesktopChatStore::filtered_conversations` for chat filtering by conversation id, title, participant, message text and attachment metadata.
- Added local `DesktopChatStore::search_selected_messages` with message id, sender, snippet and timestamp result records.
- Extended rich HTML timeline rendering with search match and focused-result classes.
- Added Qt desktop chat-filter and message-search controls.
- Added previous/next search navigation and match-count status.
- Extended desktop smoke and store test coverage.

### Implementation Summary

- `client/src/app_desktop/desktop_chat_store.h/.cpp`: local filter/search helpers plus HTML match/focused markers.
- `client/src/app_desktop/main.cpp`: navigation/search row, search state, result stepping, filtered conversation list rendering and smoke marker.
- `client/src/app_desktop/store_test.cpp`: store coverage now 17/17, including search/filter/highlight assertions.
- `scripts/validate_desktop_smoke.py`: now requires `desktop navigation search smoke ok`.
- `README.md`, `docs/architecture/current-state.md`, `docs/architecture/implementation-roadmap.md`: updated capability and remaining gaps.

### Test Flow

- Built Debug with `cmake --build build-codex --config Debug`.
- Ran store-level C++ navigation/search assertions.
- Ran real desktop smoke against the Python TCP server.

### Test Results

- Debug build: PASS.
- `app_desktop_store_test.exe`: 17/17 PASS.
- `python scripts\validate_desktop_smoke.py`: 1/1 PASS, including navigation/search marker.

### Acceptance

PASS. Desktop local navigation/search is accepted for the current MVP scope.

### Deferred Work And Risks

- Search is local to loaded conversations/messages; server-side global search and paged history search remain deferred.
- UI is functional but still minimal; richer result cards, keyboard shortcuts and scroll-to-exact-cell behavior need a custom message list/delegate.
- Chat filtering scans the local cache; large histories will need indexing.

### Next-Phase Recommendation

Continue with message actions that materially improve Telegram-likeness: replies, forwards, reactions and pinned messages. These are now higher impact than additional local search polish.

## Message actions (M54)

### Phase Goal

Add the next Telegram-like interaction layer to messages: replies, forwards, reactions and pinned-message state, with server persistence, incremental sync recovery, C++ client APIs and desktop UI controls.

### Requirement Understanding

The user asked to enter the Message actions phase directly, in the established order: protocol and server data model first, then `ControlPlaneClient`, `DesktopChatStore`, Qt UI and validator/smoke coverage.

### Completed Tasks

- Added reply metadata to `message_send`.
- Added `message_forward`, `message_reaction` and `message_pin` protocol flows.
- Persisted forward metadata, reaction summaries and pinned state in message records.
- Added message-action deltas to conversation change logs for incremental sync recovery.
- Added C++ `ControlPlaneClient` APIs for reply, forward, reaction toggle and pin/unpin.
- Extended `DesktopChatStore` rendering, cache persistence, push handling and incremental-delta handling for message actions.
- Added Qt desktop controls for message id, reply, forward, reaction, pin and unpin.
- Added dedicated server validator plus desktop smoke/store coverage.

### Implementation Summary

- `server/server/protocol.py`, `server/server/services/chat.py`, `server/server/app.py`: message action payloads, dispatch, state mutation, fan-out and sync descriptors.
- `client/src/transport/control_plane_client.h/.cpp`: message action result models and RPC methods.
- `client/src/app_desktop/desktop_chat_store.h/.cpp`: reply/forward/reaction/pin state, HTML/transcript rendering and cache round-trip.
- `client/src/app_desktop/main.cpp`: message action controls, async handlers and smoke flow.
- `scripts/validate_message_actions.py`, `scripts/validate_desktop_smoke.py`, `client/src/app_desktop/store_test.cpp`: new validation coverage.
- `shared/include/shared/protocol/message_types.h`, `shared/include/shared/protocol/chat_models.h`: shared protocol vocabulary/model updates.

### Test Flow

- Ran server-side message-action validator.
- Ran incremental sync, edit/delete and typed-error regressions.
- Built Debug with CMake.
- Ran desktop store test, desktop smoke, attachment and SQLite regressions.

### Test Results

- `python scripts\validate_message_actions.py`: 3/3 PASS.
- `python scripts\validate_incremental_sync.py`: 8/8 PASS.
- `python scripts\validate_message_edit_delete.py`: 8/8 PASS.
- `python scripts\validate_typed_errors.py`: 11/11 PASS.
- `cmake --build build-codex --config Debug`: PASS, with existing `getenv` warning.
- `app_desktop_store_test.exe`: 18/18 PASS.
- `python scripts\validate_desktop_smoke.py`: 1/1 PASS, including message-action marker.
- `python scripts\validate_attachments.py`: 11/11 PASS.
- `python scripts\validate_sqlite_persistence.py`: 2/2 PASS.
- Full `scripts\validate_*.py` sweep: 27/27 scripts PASS, 157 scenarios PASS.

### Acceptance

PASS for the first Message actions slice. Reply, forward, reaction and pin state now flow through protocol, server state, C++ client, desktop store/UI and automated validation.

### Deferred Work And Risks

- Reactions are summarized as `emoji:count`; per-user reaction detail and emoji picker UI are deferred.
- Forwarding currently copies text/attachment reference metadata; richer forwarded-message cards are deferred.
- Pin UI is raw message-id driven; a polished pinned banner/list is deferred.
- Reply UI is raw message-id driven; quote previews and click-to-jump need a richer message list.

### Next-Phase Recommendation

Polish message-action UX with selectable message rows, reply/forward preview cards, pinned banner/list and reaction picker, or switch to production paging/global search if backend hardening is higher priority.

## Backlog tasks 1-5 verified slices (M55)

### Completed Tasks

- Added clickable `msg://` message ids in the rich desktop timeline so message-action targets can be selected directly.
- Added `Use Match` and `Use Latest` controls to populate the action target from focused search results or the latest selected-conversation message.
- Added authenticated server-side message search with optional conversation scope and attachment filename matching.
- Added C++ `ControlPlaneClient::search_messages` parsing and desktop smoke coverage for the server search path.
- Added validator coverage for attachment filename search and SQLite persistence of reply/forward/reaction/pin metadata.
- Added a Qt confirmation dialog before device revoke.

### Test Results

- `cmake --build build-codex --config Debug`: PASS.
- `python scripts\validate_message_search.py`: 5/5 PASS.
- `python scripts\validate_message_actions.py`: 4/4 PASS.
- `python scripts\validate_desktop_smoke.py`: 1/1 PASS.
- `app_desktop_store_test.exe`: 19/19 PASS.
- `python scripts\validate_incremental_sync.py`: 8/8 PASS.
- `python scripts\validate_typed_errors.py`: 11/11 PASS.

### Acceptance

PASS for the first verified pass through task list 1-5. The next larger slice should focus on production search/history paging and richer UI cards.

## Production history paging and Linux Docker boundary (M56)

### Completed Tasks

- Extended `conversation_sync` with `history_limits` and `before_message_ids` for bounded newest-to-older history pages.
- Added `next_before_message_id` and `has_more` to conversation sync responses.
- Extended server-side message search with `offset`, `next_offset` and `has_more`.
- Added `ControlPlaneClient::conversation_history_page` and parsed paging flags on C++ sync/search responses.
- Added desktop smoke coverage for the C++ history page API.
- Added `deploy/docker/server.Dockerfile` and `deploy/docker/docker-compose.yml` for Linux Docker server development, with persistent `/data` and an optional PostgreSQL profile.
- Added `TELEGRAM_*` environment variable support for server container configuration.

### Test Results

- `cmake --build build-codex --config Debug`: PASS.
- `python scripts\validate_history_paging.py`: 2/2 PASS.
- `python scripts\validate_desktop_smoke.py`: 1/1 PASS, including history page marker.
- `python scripts\validate_message_search.py`: 5/5 PASS.
- `python scripts\validate_incremental_sync.py`: 8/8 PASS.
- `app_desktop_store_test.exe`: 19/19 PASS.
- `python scripts\validate_typed_errors.py`: 11/11 PASS.
- `python scripts\validate_message_actions.py`: 4/4 PASS.
- WSL `docker compose ... config`: PASS for default server and `postgres` profile.
- WSL Docker image build: BLOCKED by Docker Hub timeout while resolving `python:3.12-slim`.

### Acceptance

PARTIAL. Protocol/client/server paging is accepted and verified. Docker deployment files are structurally valid under WSL Docker, but runtime image build still needs registry access or a preloaded base image.

## WSL Docker deployment smoke (M57)

### Completed Tasks

- Configured the WSL Docker daemon proxy so Docker image pulls use the current `10.20.11.30:10809` proxy.
- Added proxy build args and container environment forwarding to `deploy/docker/docker-compose.yml`.
- Added `scripts/deploy_wsl_docker.ps1` as a one-command Windows-to-WSL deployment script.
- Kept SQLite as the default local-test server backend under `/data/runtime.sqlite`.
- Verified optional `-Mode postgres` starts the PostgreSQL service alongside the SQLite-backed server for future repository work.
- Added `scripts/validate_docker_deploy.py` to smoke-test the deployed container via a real TCP `login_request`.

### Test Results

- WSL Docker daemon proxy: configured and verified through successful Docker Hub pulls.
- `docker compose -f deploy/docker/docker-compose.yml build telegram-server`: PASS.
- `docker compose -f deploy/docker/docker-compose.yml up -d telegram-server`: PASS; container healthy.
- `python scripts\validate_docker_deploy.py`: PASS.
- `powershell -ExecutionPolicy Bypass -File scripts\deploy_wsl_docker.ps1 -NoBuild`: PASS.
- `powershell -ExecutionPolicy Bypass -File scripts\deploy_wsl_docker.ps1 -Mode postgres -NoBuild -NoSmoke`: PASS; `postgres` and `telegram-server` running.

### Acceptance

PASS for WSL Docker deployability. The server is currently deployed in Docker using SQLite by default; PostgreSQL is available as an auxiliary container but not yet used by the server.

## PostgreSQL repository boundary first slice (M58)

### Completed Tasks

- Added `PostgresStateRepository` as the first production repository boundary.
- Normalized users, devices and sessions into PostgreSQL tables.
- Preserved conversations, remote sessions, contacts and attachment metadata in a JSONB snapshot for compatibility until later repository migrations.
- Added `InMemoryState(pg_dsn=...)`, `ServerApplication(pg_dsn=...)`, `--pg-dsn` and `TELEGRAM_PG_DSN`.
- Updated Docker postgres mode to start a separate PostgreSQL-backed server on port `8788`, while keeping the default SQLite server on `8787`.
- Installed optional `psycopg[binary]` in the Docker server image.
- Fixed login with a new device id so the device record is created before session persistence; PostgreSQL foreign keys exposed this consistency gap.
- Added `scripts/validate_postgres_repository.py`.

### Test Results

- `docker compose --profile postgres build telegram-server-postgres`: PASS.
- `docker compose --profile postgres up -d postgres telegram-server-postgres`: PASS.
- Container `python scripts/validate_postgres_repository.py`: 1/1 PASS.
- `python scripts\validate_docker_deploy.py --port 8788 --device dev_docker_pg_smoke_2`: PASS.
- `python scripts\validate_docker_deploy.py --port 8787 --device dev_docker_sqlite_smoke_2`: PASS.
- `cmake --build build-codex --config Debug`: PASS.
- `python scripts\validate_desktop_smoke.py`: 1/1 PASS.
- `python scripts\validate_registration.py`: 7/7 PASS.
- `python scripts\validate_device_management.py`: 3/3 PASS.
- `python scripts\validate_sqlite_persistence.py`: 2/2 PASS.
- `python scripts\validate_typed_errors.py`: 11/11 PASS.

### Acceptance

PASS for the first PostgreSQL repository slice. It is intentionally limited to users, devices and sessions; conversations/messages/change logs should be the next repository migration.

## PostgreSQL conversation repository and desktop paging/search polish (M59)

### Phase Goal

Advance tasks 1-5 from the active list: migrate conversations/messages/change logs into PostgreSQL, keep SQLite as the default local backend, expose older-history loading in the desktop UI and make server search results more useful.

### Completed Tasks

- Added PostgreSQL tables for conversations, conversation_messages and conversation_changes.
- Kept remote sessions, contacts and attachments in the JSONB compatibility snapshot for later repository slices.
- Made PostgreSQL repository saves cover users/devices/sessions/conversation domains in one transaction.
- Added `DesktopChatStore::apply_history_page` plus cached `next_before_message_id` / `has_more`.
- Added Qt desktop `Load Older` and `Search Server` controls with a readable server-result panel.
- Expanded `validate_postgres_repository.py` to cover message and change-log persistence after restart.

### Implementation Summary

- `server/server/repositories.py`: PostgreSQL schema/load/save for conversations, messages and change logs.
- `client/src/app_desktop/desktop_chat_store.h/.cpp`: history-page state and older-page merge.
- `client/src/app_desktop/main.cpp`: desktop older-history and server-search UI.
- `scripts/validate_postgres_repository.py`: PostgreSQL restart validation for conversation/message/change-log recovery.
- `README.md`, `docs/architecture/current-state.md`, `docs/architecture/implementation-roadmap.md`: updated current capability and remaining gaps.

### Test Results

- `cmake --build build-codex --config Debug`: PASS.
- `python scripts\validate_history_paging.py`: 2/2 PASS.
- `python scripts\validate_message_search.py`: 5/5 PASS.
- `app_desktop_store_test.exe`: 20/20 PASS.
- `python scripts\validate_desktop_smoke.py`: 1/1 PASS.
- `python scripts\validate_incremental_sync.py`: 8/8 PASS.
- `python scripts\validate_sqlite_persistence.py`: 2/2 PASS.
- `python scripts\validate_typed_errors.py`: 11/11 PASS.
- `python scripts\validate_message_actions.py`: 4/4 PASS.
- Docker PostgreSQL deploy smoke on port 8788: PASS.
- Container `validate_postgres_repository.py`: 2/2 PASS.

### Acceptance

PASS. Tasks 1-5 are accepted for this slice: PostgreSQL now owns the core conversation repository path, SQLite/default behavior remains green, and the desktop can load older history plus show richer server search results.

### Deferred Work And Risks

- Contacts, attachments and remote sessions still use the PostgreSQL compatibility snapshot.
- There is not yet a formal migration/versioning framework for PostgreSQL schema changes.
- Server search result UI is functional text-card output, not a custom virtualized result list.
- Conflict recovery metadata remains deferred.

### Next-Phase Recommendation

Continue C4 production hardening by moving contacts and attachment metadata to dedicated PostgreSQL tables, then add schema migrations.

## PostgreSQL remaining domain repository migration (M60)

### Phase Goal

Close the remaining PostgreSQL repository-domain gap needed before delivery hardening: contacts, attachment metadata and remote sessions should no longer depend on the JSONB compatibility snapshot.

### Completed Tasks

- Added PostgreSQL `contacts`, `attachments` and `remote_sessions` tables.
- Extended PostgreSQL repository save/load to persist those domains in dedicated tables.
- Kept the compatibility snapshot as a fallback for older databases with empty migrated tables.
- Expanded `validate_postgres_repository.py` from 2 to 3 scenarios, covering contacts, attachment fetch after restart and remote-session restart recovery.

### Implementation Summary

- `server/server/repositories.py`: added remaining-domain schema, transactional save rows and load reconstruction.
- `scripts/validate_postgres_repository.py`: added contact, attachment and remote-session persistence scenario.
- `README.md`, `docs/architecture/current-state.md`, `docs/architecture/implementation-roadmap.md`: updated PostgreSQL repository status and remaining hardening work.

### Test Results

- `python -m py_compile server\server\repositories.py scripts\validate_postgres_repository.py`: PASS.
- `python scripts\validate_sqlite_persistence.py`: 2/2 PASS.
- `python scripts\validate_contacts.py`: 8/8 PASS.
- `python scripts\validate_attachments.py`: 11/11 PASS.
- `python scripts\validate_rendezvous.py`: 6/6 PASS.
- Docker container `validate_postgres_repository.py`: 3/3 PASS.
- `python scripts\validate_docker_deploy.py --port 8788 --device dev_docker_pg_remaining_smoke`: PASS.
- `python scripts\validate_desktop_smoke.py`: 1/1 PASS.
- `python scripts\validate_incremental_sync.py`: 8/8 PASS.
- `python scripts\validate_typed_errors.py`: 11/11 PASS.
- `python scripts\validate_session_persistence.py`: 5/5 PASS.

### Acceptance

PASS. PostgreSQL now owns the core runtime domains needed for a production persistence path while SQLite remains the default local backend and JSON compatibility remains available.

### Deferred Work And Risks

- PostgreSQL schema changes are still `CREATE TABLE IF NOT EXISTS`, not a formal migration/versioning system.
- Backup/restore and operational runbooks are not implemented.
- Presence/session hot state still lives in the durable repository path rather than Redis.

### Next-Phase Recommendation

Add schema migrations/versioning and backup/restore checks, then proceed to TLS/session hardening and installation packaging.

## PostgreSQL schema/versioning, backup/restore, session TTL and package staging (M61)

### Phase Goal

Move the PostgreSQL-backed server path closer to deployable operation and start the delivery-hardening layer requested for Telegram usability.

### Completed Tasks

- Added PostgreSQL repository schema version tracking through a `schema_migrations` table.
- Added repository backup/restore round-trip validation for messages, contacts, attachments and remote sessions.
- Added configurable login-session TTL with heartbeat refresh and expired-session cleanup.
- Added Windows desktop package staging script for CMake-built executables, optional Qt runtime deployment and zip output.
- Updated README and architecture roadmap/current-state docs.

### Implementation Summary

- `server/server/repositories.py`: current schema version constant, migration marker table and `schema_version()` query.
- `scripts/validate_postgres_repository.py`: asserts repository schema version is at least the current code version.
- `scripts/validate_postgres_backup_restore.py`: validates app-level load/save restore from a PostgreSQL repository snapshot.
- `server/server/services/auth.py`, `server/server/app.py`, `server/main.py`: session TTL wiring from CLI/env to dispatch authorization.
- `scripts/validate_session_hardening.py`: covers TTL expiry, heartbeat refresh and zero-TTL compatibility.
- `scripts/package_windows_desktop.ps1`: stages Windows desktop delivery artifacts under `artifacts/windows-desktop`.

### Test Results

- `python -m py_compile server\server\repositories.py server\server\services\auth.py server\server\app.py server\main.py scripts\validate_postgres_repository.py scripts\validate_postgres_backup_restore.py scripts\validate_session_hardening.py`: PASS.
- Docker container `validate_postgres_repository.py`: 3/3 PASS.
- Docker container `validate_postgres_backup_restore.py`: 1/1 PASS.
- `python scripts\validate_session_hardening.py`: 3/3 PASS.
- `python scripts\validate_session_persistence.py`: 5/5 PASS.
- `python scripts\validate_typed_errors.py`: 11/11 PASS.
- `powershell -ExecutionPolicy Bypass -File scripts\package_windows_desktop.ps1 -SkipQtDeploy`: PASS; staged `app_desktop.exe`, `app_chat.exe` and `telegram_like_client.exe`.

### Acceptance

PASS for this hardening slice. PostgreSQL now exposes version evidence, the app repository can round-trip backup/restore state, session lifetime can be bounded, and Windows desktop artifacts have a repeatable staging path.

### Deferred Work And Risks

- PostgreSQL migrations currently record version presence and idempotent schema creation; there is not yet a forward-only SQL migration directory with ordered upgrade scripts.
- Backup/restore validation is app-level repository state round-trip, not `pg_dump` / `pg_restore` operational automation.
- TLS is still pending; current control-plane transport remains plaintext TCP unless deployed behind external TLS termination.
- Package staging is not a signed installer and `windeployqt` requires Qt tools on PATH.

### Next-Phase Recommendation

Implement TLS termination/native TLS configuration and turn the staged Windows artifact into a signed or at least checksummed installer bundle.

## Native TLS control-plane configuration (M62)

### Phase Goal

Add the first deployable TLS hardening slice without breaking the existing plaintext local development path.

### Completed Tasks

- Added optional server-side TLS wrapping to `ThreadedControlPlaneServer`.
- Added CLI/env wiring through `--tls-cert-file`, `--tls-key-file`, `TELEGRAM_TLS_CERT_FILE` and `TELEGRAM_TLS_KEY_FILE`.
- Added TLS config validation for plaintext default behavior, cert/key pair enforcement and invalid PEM rejection.
- Updated README and architecture docs.

### Implementation Summary

- `server/server/control_plane.py`: builds an `ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)` only when both cert and key are configured; wraps accepted sockets in TLS; leaves default TCP behavior unchanged.
- `server/main.py`: exposes TLS certificate/key arguments and passes them into `serve_tcp()`.
- `scripts/validate_tls_config.py`: covers the configuration guardrails.

### Test Results

- `python -m py_compile server\server\control_plane.py server\main.py scripts\validate_tls_config.py scripts\validate_session_hardening.py`: PASS.
- `python scripts\validate_tls_config.py`: 3/3 PASS.
- `python scripts\validate_session_hardening.py`: 3/3 PASS.
- Delivery bundle verify: PASS.

### Acceptance

PASS for server-side native TLS configuration. Plaintext remains the default for current local clients, and production deployments can enable TLS when PEM material is provided.

### Deferred Work And Risks

- Existing C++ clients still use plaintext sockets and need a TLS-capable transport slice before they can connect directly to native TLS mode.
- No certificate provisioning or rotation automation is included; deployment must provide PEM files or use external TLS termination.
- Signed installer/checksum packaging is still pending after the current staging script.

### Next-Phase Recommendation

Add C++ TLS client support or document reverse-proxy TLS termination, then add checksummed/signed Windows package output.

## Checksummed Windows package output and TLS delivery notes (M63)

### Phase Goal

Make the Windows desktop artifact handoff verifiable and document the current TLS deployment boundary honestly.

### Completed Tasks

- Extended `scripts/package_windows_desktop.ps1` to emit `SHA256SUMS.txt`.
- Extended zip mode to emit a sibling `.zip.sha256` checksum file.
- Added `scripts/validate_windows_package.ps1` to run package creation and assert required executables, manifest, checksums and zip output exist.
- Added `deploy/tls/README.md` documenting native TLS server mode, reverse-proxy TLS termination, and the remaining C++ direct TLS client gap.
- Updated README and architecture docs.

### Implementation Summary

- `scripts/package_windows_desktop.ps1`: staged package directory now has per-file SHA256 checksums; zip output has a standalone checksum file.
- `scripts/validate_windows_package.ps1`: package-shape validation for CI/manual release checks.
- `deploy/tls/README.md`: deployment notes for TLS operation without overstating current C++ client support.

### Test Results

- `powershell -ExecutionPolicy Bypass -File scripts\validate_windows_package.ps1`: PASS; produced package dir, zip and `.sha256`.
- `powershell -ExecutionPolicy Bypass -File scripts\package_windows_desktop.ps1 -SkipQtDeploy -Zip`: PASS.
- `python scripts\validate_tls_config.py`: 3/3 PASS.
- `python -m py_compile scripts\validate_tls_config.py scripts\validate_session_hardening.py`: PASS.

### Acceptance

PASS for package handoff hardening. Release artifacts now have deterministic shape checks and checksum files. TLS delivery is documented with the current server-side capability and the explicit C++ client parity gap.

### Deferred Work And Risks

- Package output is not yet signed and does not include a true installer UX.
- `windeployqt` must be on PATH for a fully self-contained Qt runtime package.
- Direct C++ TLS remains pending; current clients need plaintext or external TLS termination.

### Next-Phase Recommendation

Add C++ TLS client transport behind `TcpLineClient`/`ControlPlaneClient`, or add a concrete reverse-proxy compose profile for TLS termination.

## TLS handshake smoke and Docker TLS termination profile (M64)

### Phase Goal

Turn TLS from configuration-only into a verified server path and add a concrete deployment profile for TLS termination.

### Completed Tasks

- Added `scripts/validate_tls_handshake.py`, which generates a temporary self-signed certificate, starts the TLS control plane, and performs a real TLS login request.
- Added `deploy/tls/nginx.conf` and a `telegram-tls-proxy` compose service under the `tls` profile.
- Added `scripts/validate_tls_deployment_config.py` for static validation of compose/proxy wiring.
- Expanded `deploy/tls/README.md`, README and architecture docs.

### Implementation Summary

- `validate_tls_handshake.py`: exercises the actual `ssl.SSLContext` server path and login response over TLS.
- `deploy/docker/docker-compose.yml`: `--profile tls` can run `telegram-server` behind `nginx:1.27-alpine` on host port 8443.
- `deploy/tls/nginx.conf`: terminates TLS using mounted `server.crt` / `server.key` and forwards to `telegram-server:8787`.

### Test Results

- `python -m py_compile scripts\validate_tls_handshake.py scripts\validate_tls_deployment_config.py scripts\validate_tls_config.py`: PASS.
- `python scripts\validate_tls_handshake.py`: 1/1 PASS.
- `python scripts\validate_tls_deployment_config.py`: 2/2 PASS.
- `python scripts\validate_tls_config.py`: 3/3 PASS.

### Acceptance

PASS for server/proxy TLS delivery. Native server TLS now has real handshake evidence, and Docker has a concrete TLS termination profile.

### Deferred Work And Risks

- Direct C++ desktop-to-TLS support is still pending.
- The TLS proxy profile expects `deploy/tls/certs/server.crt` and `server.key`; certificate provisioning/rotation is still operator-managed.
- The compose profile was statically validated in this slice; it was not brought up with Docker in this run.

### Next-Phase Recommendation

Implement C++ TLS client transport parity or add an automated certificate generation/dev-run script for the Docker TLS profile.

## Dev cert generation and live TLS proxy smoke (M65)

### Phase Goal

Make the Docker TLS profile runnable in a local dev environment and prove the proxy carries the JSON-over-TCP control plane correctly.

### Completed Tasks

- Added `scripts/generate_tls_dev_cert.py` for local self-signed PEM generation under `deploy/tls/certs`.
- Added `deploy/tls/certs/` to `.gitignore` so generated private keys are not committed.
- Reused the cert generator in `validate_tls_handshake.py`.
- Added `scripts/validate_tls_dev_cert.py`.
- Added `scripts/validate_tls_proxy_smoke.py`.
- Corrected nginx from HTTP proxy mode to `stream` TLS termination, which matches the raw JSON-over-TCP protocol.
- Started the Docker TLS profile and verified login through `127.0.0.1:8443`.

### Implementation Summary

- `generate_tls_dev_cert.py`: creates RSA 2048-bit self-signed cert/key with SANs for localhost and 127.0.0.1.
- `deploy/tls/nginx.conf`: uses nginx `stream` with `listen 8443 ssl` and `proxy_pass telegram_control_plane`.
- `validate_tls_proxy_smoke.py`: opens an SSL socket through the proxy and performs `login_request`.

### Test Results

- `python -m py_compile scripts\generate_tls_dev_cert.py scripts\validate_tls_dev_cert.py scripts\validate_tls_handshake.py scripts\validate_tls_deployment_config.py scripts\validate_tls_proxy_smoke.py`: PASS.
- `python scripts\validate_tls_dev_cert.py`: 2/2 PASS.
- `python scripts\validate_tls_handshake.py`: 1/1 PASS.
- `python scripts\validate_tls_deployment_config.py`: 2/2 PASS.
- `docker compose -f deploy/docker/docker-compose.yml --profile tls config`: PASS.
- `docker compose -f deploy/docker/docker-compose.yml --profile tls up -d telegram-server telegram-tls-proxy`: PASS.
- `python scripts\validate_tls_proxy_smoke.py`: PASS.
- `python scripts\validate_docker_deploy.py`: PASS for plaintext server on 8787 after TLS profile start.

### Acceptance

PASS. The TLS termination path is now locally runnable and verified with a real login over TLS through nginx stream proxy.

### Deferred Work And Risks

- C++ direct TLS transport is still pending; the proxy path preserves plaintext between nginx and the server container.
- Generated dev certs are suitable for local testing only, not production.
- The proxy profile currently targets the default SQLite-backed `telegram-server`; PostgreSQL TLS proxy wiring can be added if needed.

### Next-Phase Recommendation

Implement C++ TLS client transport parity or add TLS proxy coverage for the PostgreSQL-backed server profile.
