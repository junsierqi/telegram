# Implementation Roadmap

## Purpose

Turn the current architecture notes into an execution plan that can be implemented incrementally.

This roadmap assumes:

- `C++20` desktop client
- `Python` control-plane server
- chat product ships first
- remote desktop is a first-party subsystem built later in the same product
- remote desktop implementation can borrow patterns from `RustDesk`, but must fit this repository's client and service boundaries

## Reference projects

These projects are references, not implementation targets to mirror line-for-line.

### Messaging references

- `Telegram Desktop`
  primary reference for desktop client structure, navigation, session-oriented messaging UX and cross-platform desktop engineering tradeoffs
- `TDLib`
  primary reference for client-facing API boundaries, state synchronization ideas and separation between client logic and Telegram protocol machinery
- `Telegram Android`
  reference for mature IM product flows such as chat lifecycle, media handling, account states and device-oriented UX

### Remote desktop references

- `RustDesk`
  primary reference for first-party remote desktop decomposition, especially host, viewer, rendezvous and relay separation

### Non-reference areas

The following remain project-specific and should be designed for this repository rather than copied from public Telegram code:

- `Python` control-plane server architecture
- shared protocol between this client and this server
- chat to remote-control integration boundary
- trust, audit and device policy model for remote sessions

## Delivery strategy

Build the product in three large waves:

1. chat MVP foundation
2. remote-control control plane
3. AnyDesk-like remote desktop runtime

Each wave must leave the repository runnable and documented.

## Wave 1: chat MVP foundation

### Goal

Ship a thin but real chat system that establishes the identity, trust, device and session model required by later remote desktop work.

### Client scope

- application shell
- sign-in and sign-out flow
- conversation list
- one-to-one conversation view
- text message composer
- active device view
- reconnect and sync state handling

### Server scope

- account login
- session token issue
- websocket session gateway
- one-to-one conversation routing
- unread and ack state
- presence heartbeat
- active device registry

### Shared protocol scope

- auth request and response contracts
- presence update contracts
- conversation sync contracts
- text message send and delivery contracts
- device list contracts
- error envelope and correlation id model

### Minimal persistence

- `PostgreSQL` for users, devices, conversations and messages
- `Redis` optional at first, then introduced for presence and ephemeral sessions

### Exit criteria

- two clients can log in
- users can send and receive text messages
- reconnect does not lose conversation history
- users can inspect active devices

## Wave 2: remote-control control plane

### Goal

Add all session negotiation, authorization and service-side coordination needed before screen and input streaming exist.

### Client scope

- request remote session from chat or device panel
- incoming approval dialog
- outgoing waiting state
- session state transitions in UI
- capability reporting for current device

### Server scope

- remote session create API
- approval and rejection workflow
- device capability lookup
- session token minting
- rendezvous and peer-discovery records
- relay allocation decision
- audit log records

### Shared protocol scope

- remote invite
- remote reject
- remote approve
- remote cancel
- remote session status update
- rendezvous payload
- relay assignment payload
- short-lived remote session credential payload

### Security baseline

- attended sessions require explicit approval
- remote session tokens are short-lived and single-session scoped
- every session produces audit records
- trusted contacts or trusted devices can be enforced later as policy

### Exit criteria

- user can invite another online device into a remote session
- recipient can approve or reject
- both sides can observe synchronized session state
- server can choose direct-attempt or relay-required path
- no screen or input transport yet

## Wave 3: AnyDesk-like remote desktop runtime

### Goal

Implement the project-owned host, viewer, direct-connect and relay path needed for a usable remote desktop MVP.

### Windows-first MVP scope

- Windows host
- Windows viewer
- screen capture
- frame encode and decode
- mouse input
- keyboard input
- clipboard optional if low cost
- relay fallback

### Deferred from MVP

- macOS host
- Linux host
- multi-monitor
- audio
- file transfer inside remote session
- unattended access policies

## Target architecture split

### Client-side split

The desktop client should evolve into these areas:

- `client/src/app`
  startup, shell, navigation, lifecycle
- `client/src/auth`
  sign-in state and token lifecycle
- `client/src/chat`
  conversation state and message send path
- `client/src/devices`
  device list and trust state
- `client/src/transport`
  control-plane networking
- `client/src/remote_control`
  remote session UI and orchestration
- `client/src/remote_control/host`
  capture, encode, host state machine
- `client/src/remote_control/viewer`
  decode, render, input send
- `client/src/remote_control/rtc`
  peer connection, relay transport, session keys
- `client/src/platform`
  OS-specific capture and input injection
- `client/src/storage`
  local cache and session persistence

Reference mapping:

- `client/src/app`, `client/src/chat`, `client/src/contacts`, `client/src/devices`
  look mostly to `Telegram Desktop` and `Telegram Android`
- `client/src/transport`
  look to `TDLib` for boundary ideas, but keep protocol local to this project
- `client/src/remote_control`, `client/src/remote_control/host`, `client/src/remote_control/viewer`, `client/src/remote_control/rtc`
  look mostly to `RustDesk`
- `client/src/platform`
  use OS-native APIs and keep the abstraction local to this codebase

### Server-side split

The Python server should remain the control plane and later coordinate extra services:

- `server/server/services/auth.py`
  login, token issue, device trust
- `server/server/services/chat.py`
  chat routing and sync
- `server/server/services/presence.py`
  presence heartbeat and device online state
- `server/server/services/remote_session.py`
  remote session workflow, credentials, audit
- future `server/server/services/rendezvous.py`
  peer discovery and connection hints
- future `server/server/services/relay_registry.py`
  relay capacity and assignment metadata

Reference mapping:

- chat-side service boundaries may borrow product concepts from Telegram clients and `TDLib`
- remote desktop coordination should borrow more from `RustDesk`-style rendezvous and relay thinking
- the actual `Python` control-plane implementation remains specific to this repository

### Service split after MVP

When remote desktop traffic becomes real, introduce separate long-lived services:

- rendezvous service
- relay service
- metrics and QoS service

The Python control plane should not become the binary frame forwarding bottleneck.

## Protocol layering

### Layer 1: control plane

Used for:

- auth
- chat messages
- presence
- device management
- remote invite and approval
- rendezvous metadata
- relay assignment

Suggested transport:

- websocket first

### Layer 2: remote session setup

Used for:

- NAT traversal hints
- direct-connect attempts
- relay fallback decision
- short-lived session keys

Suggested direction:

- dedicated session setup payloads carried by the control plane
- runtime sockets established separately from chat messages

### Layer 3: media and input

Used for:

- video frames
- input events
- optional clipboard
- later audio

Suggested direction:

- direct peer transport when available
- relay transport when direct path fails
- binary framing independent of chat envelopes

## First concrete protocol expansion

The current shared message enum is enough for placeholders, but not for implementation. First real expansion should add:

- `login_request`
- `login_response`
- `session_refresh`
- `presence_update`
- `conversation_sync`
- `message_send`
- `message_deliver`
- `message_ack`
- `device_list_request`
- `device_list_response`
- `remote_invite`
- `remote_invite_response`
- `remote_session_state`
- `remote_rendezvous_info`
- `remote_relay_assignment`
- `remote_session_terminated`
- `error`

The enum should remain a small vocabulary layer. Payload schemas should move into shared structures instead of being implied by message names alone.

## Recommended first code tasks

### Task set A: make chat control plane real

- add structured protocol models under `shared/include/shared/protocol`
- add server request dispatch skeleton
- add client session gateway send and receive skeleton
- add in-memory chat and presence state before database wiring

### Task set B: make remote control plane real

- define remote session state machine
- define invite, approval and termination payloads
- add device capability model
- add audit event model

### Task set C: prepare Windows runtime boundary

- create `platform/windows` adapters for capture and input injection interfaces
- keep implementations stubbed at first
- make `remote_control` orchestrate host and viewer objects without transport yet

### Task set D: add relay-ready runtime boundary

- define direct transport interface
- define relay transport interface
- keep the Python control plane responsible only for negotiation and assignment

## Suggested milestone order

1. runnable websocket-based login and chat loop
2. conversation sync and device list
3. remote invite and approval flow without streaming
4. local fake screen-frame loop between host and viewer modules
5. real Windows capture and render path
6. direct-connect attempt
7. relay fallback
8. hardening, audit and unattended-access policy work

## Chat completion arc (C1-C5)

This arc raises the project from verified protocol prototype toward a usable Telegram-like MVP. It deliberately prioritizes completeness and maturity over adding new remote-control features.

### C1: desktop GUI baseline

- Qt Widgets desktop shell
- login form
- conversation sync display
- live push display
- text message composer
- automated smoke validation

Status: started. `app_desktop.exe` now covers connect, login, sync and send through the existing `ControlPlaneClient`.
Registration update: the same Qt desktop shell now has a Register button backed by `ControlPlaneClient::register_user`, with smoke coverage for native new-account creation.
Contacts/groups update: the Qt desktop now has contacts list/add/remove controls plus basic group create and selected-conversation member add/remove controls, with smoke coverage for contacts and group creation.
Timeline update: desktop message rows now show basic inbound/outbound bubble-style rendering, HH:MM timestamps for newly created server messages, local sent/read state driven by read markers, and cache round-trip coverage for read state.
Timeline completion update: the desktop store now models local pending and failed text/attachment sends, renders group read receipts as per-member detail (`read by u_bob` / `read by all`), exposes a rich HTML bubble renderer used by the Qt UI, and shows legacy messages with an explicit `legacy` timestamp fallback instead of an ambiguous missing time.
Profile/search update: the protocol now exposes authenticated profile get/update and user search. The Qt desktop can refresh/save the current display name and search users by username, display name or user_id with online/contact status, with server and desktop smoke coverage.
Navigation/search update: the Qt desktop now has chat-list filtering and selected-conversation message search with prev/next navigation and rich timeline match/focused highlighting. Store and smoke tests cover the local search behavior.
Message actions update: replies, forwards, reaction toggles and pin/unpin now flow through the control-plane protocol, server message records, fan-out pushes, incremental sync deltas, `ControlPlaneClient`, `DesktopChatStore` cache/rendering and raw Qt desktop controls.
Backlog 1-5 slice update: message-action targets are now discoverable from timeline ids and focused search matches; the server exposes authenticated message search with optional conversation scope and attachment filename matches; the C++ client and desktop smoke cover that search path; message-action metadata has SQLite persistence coverage; and device revoke now requires a Qt confirmation.
Telegram reference UI update: the Qt desktop reference shell now treats right-side details as a first-class Telegram Desktop surface. Channel, one-to-one contact and group info states render through distinct branches, with GUI smoke evidence for `reference-09-chat-channel-info-panel.png`, `reference-10-chat-user-info-panel.png` and `reference-11-chat-group-info-panel-empty.png` covering the M-Team channel summary, Hello Blake contact summary and 三叉戟 member list shapes.
Production paging/deploy update: `conversation_sync` now supports bounded history pages with `history_limits`, `before_message_ids`, `next_before_message_id` and `has_more`; message search supports offset paging; `ControlPlaneClient` exposes `conversation_history_page`; and `deploy/docker` defines the Linux Docker server path with a persistent `/data` volume plus an optional PostgreSQL compose profile. WSL Docker build/up/smoke now passes through the configured proxy, and `scripts/deploy_wsl_docker.ps1` is the one-command deployment entry.
PostgreSQL repository update: the PostgreSQL-backed server path is available behind `--pg-dsn` / `TELEGRAM_PG_DSN`. Users, devices, sessions, conversations, messages, conversation change logs, contacts, attachment metadata and remote sessions are normalized in PostgreSQL. Docker `-Mode postgres` runs this PG-backed server on port 8788 while preserving the SQLite server on 8787.
Production hardening update: PostgreSQL now records repository schema versions through `schema_migrations` and has an app-level backup/restore validator. Login session expiry is configurable through `--session-ttl-seconds` / `TELEGRAM_SESSION_TTL_SECONDS`; heartbeat refresh keeps active sessions alive and expired sessions are removed. The Python TCP control plane can run native TLS when `--tls-cert-file` and `--tls-key-file` are configured together, and `validate_tls_handshake.py` verifies a real TLS login round trip. Docker also has `nginx` stream TLS termination profiles for the SQLite-backed service on port 8443 and PostgreSQL-backed service on port 8444, backed by `generate_tls_dev_cert.py`, `validate_tls_deployment_config.py` and `validate_tls_proxy_smoke.py`; PostgreSQL live proxy smoke remains a pending external action until approved. C++ clients now have a Windows Schannel TLS transport entrypoint, but runtime acceptance is partial in this environment because Schannel credential acquisition returns `SEC_E_NO_CREDENTIALS`. Windows desktop package staging is available through `scripts/package_windows_desktop.ps1` with zip and SHA256 output, plus `scripts/validate_windows_package.ps1` for package-shape validation.

### C2: client state and local cache

- conversation and message store behind the GUI
- update cursor / last-known sync point
- reconnect then reconcile missed messages
- unread counts and message status

Status: partial. C2a added an in-memory `DesktopChatStore` behind the Qt GUI with sync/send/push merge and unread counts for unselected conversations. C2b added JSON cache save/load and full-sync reconciliation after reconnect. C2c added a real Qt conversation list and persisted per-conversation `last_message_id` cursors. C6a added server-side cursor-based incremental `conversation_sync`; C6b added durable per-conversation change versions and edit/delete/read-marker delta recovery; C6c added membership metadata deltas and compacted-log full fallback. Message timeline polish added `created_at_ms` propagation, read-marker application in the desktop store, sent/read status for outbound rows, pending/failed local text/attachment send states, per-member group read details, rich HTML bubble rendering and legacy timestamp fallback. Profile/search work added account display-name update and basic user discovery outside the timeline. Navigation/search work added local chat filtering plus selected-conversation message search and result highlighting. Message actions added reply metadata, forwarded-message metadata, reaction summaries, pinned state and clickable action targets across server sync/push and the local desktop cache. Server-side message search now exists for accessible conversations with optional scope, attachment filename matches and offset paging, and the desktop shows server result cards. `conversation_sync` now has bounded history pages and the desktop can load older selected-conversation pages into the cache. Remaining C2/C6 work: conflict recovery metadata and deeper navigation polish.

### C3: production attachment path

- metadata remains on the control plane
- content moves out of JSON/base64 state snapshots
- file picker upload and download/save UI in the desktop client
- object-store-compatible server boundary

Status: partial. Server-side content now moves out of runtime JSON into `AttachmentBlobStore` under `--attachment-dir`, while metadata stays in state. Legacy inline `content_b64` state remains readable. C++ `ControlPlaneClient` can send/fetch attachments, sync exposes filename/mime/size metadata, server search can match attachment filenames, and the Qt desktop has an Attach button, an attachment-id save control, filename/size transcript rendering, lightweight text/image type previews, stage-based upload/download/save status and smoke attachment send/fetch/save round-trip. Remaining C3 work: real decoded thumbnails, byte-level progress for a future chunked transport and a true object-store implementation.

### C4: durable server persistence

- PostgreSQL-backed users, devices, conversations, messages, contacts and attachment metadata
- migration path from seed/dev JSON state
- transaction boundaries around message write + fan-out inputs

Status: partial. C4a added a SQLite-backed `--db-file` backend to `InMemoryState` while preserving JSON `--state-file`. The SQLite schema persists users, devices, sessions, conversations, remote sessions, contacts and attachment metadata, and C4 validation covers restart recovery across those domains. Message-action metadata now has targeted SQLite restart coverage. The Linux Docker server path now defaults to `/data/runtime.sqlite` and `/data/attachments`, and has a verified one-command WSL deployment script. The PostgreSQL repository path normalizes users, devices, sessions, conversations, messages, conversation change logs, contacts, attachment metadata and remote sessions and is available through a separate PG-backed Docker server on port 8788; repository saves use one PostgreSQL transaction, records schema versions and is covered by repository plus backup/restore validators. Remaining C4 work: Redis-backed presence/session hot state and a real external backup operator flow beyond the app-level restore check.

### C5: device management completeness

- list active devices in GUI
- revoke sessions
- trusted-device state
- clearer presence/last-seen UX

Status: pass for current MVP scope. The Qt desktop can list devices, show online/trusted state, confirm revoke, revoke non-current devices and toggle trust. Server protocol handles `device_revoke_request` and `device_trust_update_request`, with current-device revoke denied and SQLite persistence verified. Remaining production polish: richer last-seen labels, audit records and admin policy.

### C6: incremental sync and delta recovery

- cursor-bearing `conversation_sync`
- reconnect fetches only missed messages where possible
- fallback to full conversation if a cursor is unknown
- durable delta stream for edits, deletes, read markers and membership metadata
- compacted-log full fallback for stale client versions
- future paging/windowing and explicit conflict metadata

Status: partial. C6a keeps the existing `conversation_sync` message type compatible with `{}` full sync while accepting `{cursors:{conversation_id:last_message_id}}` for incremental message fetch. C6b adds `{versions:{conversation_id:change_seq}}`, a durable JSON/SQLite change log, and edit/delete/read-marker deltas when no new messages exist. C6c records membership metadata deltas, applies title/participant metadata in the Qt desktop cache, and caps retained changes with full conversation fallback when a client version is older than the retained log. Remaining C6 work: server-side paging/windowing and explicit conflict recovery metadata.

## Current repository implications

The current repository is already aligned with the broad shape, but these additions are expected soon:

- richer Qt desktop surfaces on top of `ControlPlaneClient`
- message navigation polish and richer message-action cards/pickers
- client `storage` folder around the current local cache and sync cursors
- durable server persistence replacing JSON snapshots
- file/object storage boundary for attachments
- complete C++ TLS client runtime parity after resolving the Schannel credential blocker or selecting a different TLS backend; PostgreSQL TLS proxy live smoke remains pending approval
- signed/checksummed Windows installer packaging after current package staging
- future rendezvous and relay service modules after chat completeness improves

## Rule for future work

Any implementation step that changes phase boundaries, protocol contracts or module ownership must update:

- `README.md`
- matching files under `docs/architecture`
- matching files under `docs/flows`
- affected Mermaid diagrams
