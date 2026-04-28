# Current-state architecture

This is the authoritative reference for what actually exists in the repo
today. Unlike `overall.md` / `server.md` / `client.md` (which capture the
product direction and may still describe placeholder scaffolds), this file
walks the directory tree and annotates every real module with its current
responsibilities and its runtime contract.

Last synced: after milestone **M66 — PostgreSQL TLS proxy coverage**.
Bundle status: PostgreSQL repository validator 3/3, PostgreSQL backup/restore validator 1/1, session hardening 3/3, TLS config 3/3, TLS handshake 1/1, TLS deployment config 4/4, TLS dev cert 2/2, live SQLite TLS proxy smoke passed, PostgreSQL TLS proxy live smoke pending approval, C++ TLS transport compiles but runtime smoke is blocked by Schannel `SEC_E_NO_CREDENTIALS`, Windows package validation passed with zip + SHA256.

---

## System shape

```
+--------------------------+            TCP control plane          +--------------------------+
|  C++ client (Windows)    |  <-- JSON-per-line envelopes --->     |  Python server          |
|                          |                                       |                          |
|  app_desktop.exe         |      UDP media plane (auth-gated)     |  - ThreadedTCPServer    |
|  app_chat.exe            |  <----------- relay --------------->  |  - ThreadedUDPServer    |
|  telegram_like_client.exe|                                       |  - InMemoryState        |
|                          |                                       |  - JSON or SQLite store |
+--------------------------+                                       +--------------------------+
       |                                                                      |
       |  also spoken by:                                                     |
       |                                                                      |
 scripts/chat_cli.py  (dev-only Python interactive CLI)                       |
 scripts/validate_*.py  (Python runtime validators)                           |
```

Control plane: line-delimited JSON over TCP, one persistent socket per
logged-in session. Request/response use matching `correlation_id`; server
pushes (message_deliver, message_edited, message_read_update, etc.) arrive
on the same socket with a `push_*` correlation_id.

Media plane: UDP. Authorized per-session by active remote-session
membership. Three body shapes — legacy echo, structured frame_chunk
subscribe stream, and peer RELAY forwarding. Reliability (NAK + ACK +
tail-loss tick) lives in `reliable_stream.py` as a pure algorithm module;
it is **not yet wired** into the UDP transport.

---

## Top-level layout

```
telegram/
├── CMakeLists.txt                # top of C++ build (adds client/)
├── README.md
├── client/                       # C++20 client — Win32 today, POSIX-ready
│   └── src/
│       ├── CMakeLists.txt        # chat_client_core.lib + CLI/demo/Qt GUI exe targets
│       ├── main.cpp              # entry for telegram_like_client.exe
│       ├── app/                  # scripted demo (app_shell)
│       ├── app_chat/             # interactive chat binary (A3)
│       ├── app_desktop/          # Qt Widgets desktop + local chat store/cache + incremental sync + attachments + devices (C1-C6c)
│       ├── auth/                 # AuthController (placeholder — see § 3.4)
│       ├── chat/                 # ChatController (placeholder)
│       ├── contacts/             # ContactController (placeholder)
│       ├── devices/              # DeviceController (placeholder)
│       ├── remote_control/       # RemoteSessionController (placeholder)
│       ├── net/                  # cross-platform socket abstraction (B1/A1)
│       └── transport/            # wire protocol + control-plane client (A2)
├── server/                       # Python 3.8+ server (stdlib only)
│   ├── main.py                   # argparse entry, wires TCP + UDP
│   └── server/
│       ├── app.py                # ServerApplication + dispatch() router
│       ├── control_plane.py      # ThreadedTCPServer + per-connection handler
│       ├── media_plane.py        # ThreadedUDPServer + frame/relay framing
│       ├── connection_registry.py# session_id -> thread-safe writer
│       ├── protocol.py           # MessageType enum + typed payload dataclasses
│       ├── state.py              # InMemoryState + JSON persistence
│       ├── crypto.py             # PBKDF2-SHA256 password hashing (F2)
│       ├── reliable_stream.py    # standalone NAK/ACK reliability algorithm
│       ├── screen_source.py      # ScreenSource protocol + test patterns
│       └── services/             # one module per service
│           ├── auth.py           # login + register + session resolution
│           ├── chat.py           # conversations, messages, read, edit, attach
│           ├── contacts.py       # directed per-user contact lists
│           ├── input.py          # remote-session input event injection
│           ├── presence.py       # heartbeat + TTL-based online
│           └── remote_session.py # full invite→approve→rendezvous→terminate lifecycle
├── shared/
│   └── include/shared/protocol/  # C++ mirror of wire types
│       ├── control_envelope.h
│       ├── message_types.h
│       ├── errors.h
│       ├── chat_models.h
│       └── remote_session.h
├── scripts/
│   ├── chat_cli.py               # dev-only Python interactive chat CLI
│   └── validate_*.py             # 39 validation scripts
├── docs/
│   ├── architecture/             # this file + overall.md / server.md / client.md / …
│   ├── flows/
│   └── diagrams/
├── build/                        # cmake out-of-source build (gitignored in intent)
└── .idea-to-code/telegram-platform/  # delivery bundle (status.json + 00–06 artefacts)
```

---

## § 1. Server (Python)

Stdlib only. No third-party dependency. Plain `socketserver.ThreadedTCPServer`
+ `ThreadedUDPServer` for the two planes, JSON files for persistence,
`hashlib.pbkdf2_hmac` + `hmac.compare_digest` for password hashing.

### 1.1 Entry and routing

| File | Purpose |
|---|---|
| `server/main.py` | argparse CLI. `--tcp-server` starts control plane; `--udp-port` optionally starts media plane; `--state-file` picks the JSON persistence path; `--db-file` picks SQLite persistence; `--pg-dsn` picks PostgreSQL persistence; `--attachment-dir` picks blob storage; `--session-ttl-seconds` bounds login session age when nonzero; `--tls-cert-file` / `--tls-key-file` enable native TLS for the TCP control plane; `--screen-source <pattern>[:WxH]` attaches a synthetic frame source. Host, port, db/PG, attachment, session TTL, TLS and UDP settings can also be set through `TELEGRAM_*` environment variables for Docker deployment. Builds one `ServerApplication`, shares it between both planes so they see the same session state. |
| `server/server/app.py` | **`ServerApplication`** is the composition root. Owns `InMemoryState`, one of each service, the `ConnectionRegistry`, and an injectable `clock`. `dispatch(message: dict) -> dict` is the single entry point for every inbound TCP frame — it parses the envelope, resolves the session, dispatches to the matching service method, and handles fan-out of push envelopes. `_fanout_to_conversation` / `_fanout_to_users` generalize the push path so any conversation-scoped event (MESSAGE_DELIVER, MESSAGE_EDITED, MESSAGE_DELETED, MESSAGE_READ_UPDATE, CONVERSATION_UPDATED) reuses the same sender-exclusion rule. |
| `server/server/control_plane.py` | `ThreadedControlPlaneServer` (TCP, optionally TLS). The per-connection handler holds a write-lock, registers the session's writer into the registry on login, unregisters in a finally block. If both TLS certificate and key are provided, accepted sockets are wrapped with a server-side `ssl.SSLContext`; otherwise plaintext behavior remains the default. A TLS login round-trip validator exercises the real handshake path. This is where unsolicited pushes reach the socket. |
| `server/server/media_plane.py` | `ThreadedUdpMediaServer`. Two wire layers: the outer `sid_len|sid|body` envelope (per-session auth gate — silent drop if unauthorized), and the body verb set — legacy echo, `SUB:<count>:<cookie>` frame subscribe, `RELAY:<target_sid>:<body>` peer forward, `HELLO` register. `peer_registry` tracks session_id → last-seen addr; every authorized packet refreshes it. |
| `server/server/connection_registry.py` | Thread-safe `session_id -> writer callable` map. Writers are per-connection closures that hold the handler's write lock so request responses and push pushes never interleave bytes. |

### 1.2 Protocol and state

| File | Purpose |
|---|---|
| `server/server/protocol.py` | Single source of truth for the wire format. `MessageType` StrEnum (~40 values — login, register, message_send, message_forward, message_reaction, message_pin, message_read, message_edit, conversation_create, heartbeat_ping, presence_query_request, contact_*, attachment_*, remote_*, …). `ErrorCode` StrEnum (~40 codes) with matching human messages. Typed `@dataclass(slots=True)` payloads for every request and response, including message `created_at_ms`, reply/forward metadata, reaction summary, pinned state, attachment filename/mime/size metadata on synced messages, `ConversationSyncRequestPayload(cursors=..., versions=..., history_limits=..., before_message_ids=...)`, history-page `next_before_message_id` / `has_more`, message-search `offset` / `next_offset` / `has_more`, and `ConversationChangeDescriptor` for incremental sync. `parse_request` dispatches to per-type parsers. `Envelope` / `RequestMessage` / `ResponseMessage` structs; `make_envelope`, `make_response`, `ServiceError`. |
| `server/server/state.py` | **`InMemoryState`** holds `users`, `devices`, `sessions`, `conversations`, `remote_sessions`, `contacts`, `attachments`. Conversation records now include a durable `change_seq` and change log for edit/delete/read-marker deltas. It supports JSON `--state-file`, SQLite `--db-file`, and PostgreSQL `--pg-dsn` through `PostgresStateRepository`. `save_runtime_state()` writes the configured backend; `_load_runtime_state()` is defensive for JSON and schema-aware for SQLite/PostgreSQL. `sessions_for_user(uid)` is the fan-out lookup helper. |
| `server/server/crypto.py` | F2 deliverable. `hash_password(pt)` → `pbkdf2_sha256$iter$salt_hex$hash_hex`; `verify_password(pt, stored)` uses `hmac.compare_digest`. 120k iterations, 16 B salt, 32 B derived. |

### 1.3 Services

Each service owns a narrow slice of domain state mutations. All mutations
that need to survive restart call `self._state.save_runtime_state()`.

| File | Responsibility |
|---|---|
| `services/auth.py` | `login()` verifies via `verify_password` then creates a `SessionRecord` (populating `last_seen_at` via injected clock). `register()` validates username regex + password length + uniqueness, then creates user + device + session atomically. `resolve_session(sid)` is the dispatch-layer gate against `INVALID_SESSION`; when configured with `session_ttl_seconds`, expired sessions are removed and reported as invalid. |
| `services/attachment_store.py` | Filesystem-backed `AttachmentBlobStore`. Stores attachment bodies under an attachment blob directory and returns stable blob keys. This is the object-store-ready boundary; replacing it with S3/MinIO later should not require changing `ChatService` validation or the control-plane protocol. |
| `services/chat.py` | The fattest service. `sync_for_user_since` accepts per-conversation `last_message_id` cursors plus change versions, returns newer messages and durable edit/delete/read-marker/reaction/pin/conversation-metadata deltas, supports bounded history pages through `history_limits` / `before_message_ids`, compacts old change entries with a full-sync fallback for stale versions, and falls back to the full conversation for unknown cursors. Message search supports accessible-conversation filtering, offset paging and attachment filename matches. Also owns timestamped `send_message` with optional reply metadata, `forward_message`, reaction toggles, pin/unpin state, `create_conversation` / `add_participant` / `remove_participant`, `mark_read` (forward-only pointer), `edit_message` / `delete_message` (sender-only, soft-delete via `deleted=True`), `send_attachment_message` (1 MB cap, strict base64 validate, size match, metadata in state + content in blob store), `fetch_attachment` (participant-only access, content read from blob store or legacy inline base64). |
| `services/presence.py` | Injectable `clock` + `ttl_seconds` (default 30 s). `touch(sid)` refreshes `last_seen_at`. `is_user_online` / `is_device_online` / `is_session_fresh` all compare `(now - last_seen_at) <= ttl`. `query_users(ids)` returns typed status. `list_devices(uid)` routes `active` flag through the TTL check. |
| `services/contacts.py` | Directed per-user contact lists keyed by owner_user_id. `add` rejects self-adds + duplicates + unknown targets. `list` returns descriptors enriched with live presence. |
| `services/input.py` | Remote-session keyboard/mouse input injection. Per-kind data-field validation (`key`, `mouse_move`, `mouse_button`, `scroll`). Records a monotonic event log. Only the requester of an active remote session can inject. |
| `services/remote_session.py` | Full remote-control lifecycle state machine: invite → awaiting_approval → approved → negotiating → terminated (with reject / cancel / disconnect branches). `request_rendezvous()` returns ICE-style candidate list + relay metadata. |

### 1.4 Standalone algorithm module

| File | Purpose |
|---|---|
| `server/server/reliable_stream.py` | `ReliableChannel` — pure algorithm, transport-agnostic. Wire verbs `REL:<seq>:<body>` / `NAK:<seqs>` / `ACK:<hw>`. Sender keeps unacked buffer, retransmits on NAK, trims on cumulative ACK, `tick_retransmit()` for tail-loss recovery. Receiver buffers out-of-order, drains contiguous in-order, re-NAKs on every gap-creating packet, emits cumulative ACK, ignores duplicates. Validated against 30 % random loss + 2-drop + reorder + duplicate + tail-loss scenarios. **Not yet wired** into `media_plane.py` — left for a later integration milestone. |
| `server/server/screen_source.py` | `ScreenSource` protocol + `StaticImageScreenSource` + `build_test_pattern` (gradient/black/white/red) + `make_test_pattern_source` factory. Plugs into `ThreadedUdpMediaServer` via `screen_source=`. |

---

## § 2. Client (C++20)

Built with CMake 3.24+. Currently Windows-only at runtime (MSVC-tested).
POSIX branches in `net/` are structurally correct but not yet
compile-exercised. Two executables + one static library:

- `chat_client_core.lib` — all non-`main` sources
- `telegram_like_client.exe` — scripted demo (`app_shell`)
- `app_chat.exe` — interactive chat binary (A3)
- `app_desktop.exe` — Qt Widgets desktop baseline through incremental sync and device management (C1-C6c)

### 2.1 Networking foundation (`client/src/net/`)

This is the platform-abstracted layer — every socket call in the codebase
must route through here. The `#ifdef _WIN32 / #else` split inside each
file is the only place that knows about Winsock vs POSIX.

| File | Purpose |
|---|---|
| `net/platform.h` | Header-only façade. `using NativeSocket = SOCKET \| int`. `kInvalidSocket`, `kSocketError`, `socklen_type`, `is_valid(NativeSocket)`, `close_native_socket`, `set_recv_timeout_ms`, `native_send/recv/sendto/recvfrom`. Includes `<WinSock2.h>` + `<WS2tcpip.h>` on Win, `<sys/socket.h>` etc. on POSIX. |
| `net/socket_error.h/.cpp` | `NetErrorCode` enum (ok, would_block, timeout, connection_refused, dns_failure, …). `last_native_error()` → `WSAGetLastError()` or `errno`. `map_native_error(int)` → `NetErrorCode`. `describe(code)` returns stable snake_case name. |
| `net/socket_subsystem.h/.cpp` | `SocketSubsystem` RAII guard. On Windows, refcounted `WSAStartup`/`WSACleanup` behind a static mutex so multiple owners each construct/destruct without stepping on each other. On POSIX, no-op. |
| `net/socket_raii.h` | `Socket` — move-only RAII wrapper around `NativeSocket`. `reset`, `release`, `get`, `valid`. |
| `net/tcp_line_client.h/.cpp` | **A1/M67.** Async JSON-line TCP client. Background reader thread drains `\n`-delimited frames into a `std::deque<std::string>` behind mutex + condvar. `send_line()` is thread-safe via a separate write mutex. `wait_for(predicate, timeout_ms)` pops the first matching frame, leaves the rest in queue order. Predicate builders: `match_correlation_id(id)` (naive JSON scan), `match_any()`. Windows builds now expose a Schannel-backed `connect_tls` path with optional dev insecure certificate validation bypass; it compiles but local runtime smoke is blocked by Schannel credential acquisition. Destructor `shutdown(SD_BOTH / SHUT_RDWR)` to unblock `recv()`, then joins the reader. |

### 2.2 Wire & control-plane (`client/src/transport/`)

| File | Purpose |
|---|---|
| `transport/json_value.h/.cpp` | Hand-rolled JSON value + parser. `JsonValue` holds a `variant<nullptr, bool, double, string, array, object>`. `JsonParser` is a simple recursive-descent. `find_member`, `string_or_empty`, `array_size` helpers. |
| `transport/request_messages.h/.cpp` | Dataclass-style request structs + handwritten serializers for the **legacy** control-plane path (login, message_send, remote_* — the set that `app_shell` uses). |
| `transport/response_messages.h/.cpp` | Typed response payload variants + `parse_response_json`. Covers login, device_list, conversation_sync, message_deliver, and the full remote_* family. Does NOT yet cover the E-series push types — those parse via ad-hoc helpers in `control_plane_client.cpp`. |
| `transport/session_gateway_client.h/.cpp` | **Legacy** synchronous request/response TCP client. One send, read until `\n`, return. Used by `app_shell` for its scripted demo flow. Now built on `net/`. |
| `transport/control_plane_client.h/.cpp` | **A2/C3/C5/C6/M52/M54/M55/M56.** High-level typed wrapper around `TcpLineClient`. Every RPC assigns a fresh `rpc_<n>` correlation_id and blocks on the exact match. Typed results with `{ok, error_code, error_message}` for: `login`, `register_user`, `profile_get`, `profile_update`, `search_users`, `search_messages`, `conversation_sync`, `conversation_sync_since`, `conversation_history_page`, `send_message`, `reply_message`, `forward_message`, `toggle_reaction`, `set_message_pin`, `send_attachment`, `fetch_attachment`, `mark_read`, `edit_message`, `delete_message`, `list_contacts` / `add_contact` / `remove_contact`, `create_conversation` / `add_conversation_participant` / `remove_conversation_participant`, `list_devices`, `revoke_device`, `update_device_trust`, `presence_query`, `heartbeat_ping`. Message responses parse `created_at_ms`, reply/forward metadata, reaction summary and pinned state; attachment sync responses parse attachment_id plus filename/mime/size; message-search responses parse conversation, message, sender, snippet, attachment metadata and offset paging flags. Incremental sync cursors carry both `last_message_id` and `version`, history pages carry `next_before_message_id` / `has_more`, and responses parse `changes` plus read markers. A background **dispatcher thread** pulls any frame whose correlation_id starts with `push_` and invokes a single `PushHandler` callback (`type`, `envelope_json`). Optional `start_heartbeat(interval_ms)` spawns a periodic `heartbeat_ping` thread. |
| `transport/udp_media_probe.h/.cpp` | Simple UDP probe matching `media_plane.py`'s `sid_len\|sid\|body` framing. Now uses `net::SocketSubsystem` + `net::Socket`. |
| `transport/udp_frame_stream.h/.cpp` | `subscribe_and_collect(host, port, sid, count, cookie)` — UDP SUB + frame-chunk parser that mirrors the server wire format byte-for-byte (kind='F' \| seq \| payload_len \| width \| height \| timestamp_ms \| codec \| 3 rsv \| body). |

### 2.3 Executables

| File | Purpose |
|---|---|
| `client/src/main.cpp` | Entry for `telegram_like_client.exe` → calls `app_shell`. |
| `client/src/app/app_shell.cpp` | Scripted demo flow: alice+bob login → device_list → conversation_sync → message_send → remote_invite → approve → rendezvous → (optional UDP probe + frame subscribe if `TELEGRAM_LIKE_UDP_PORT` env set) → terminate. Used as an end-to-end smoke test for the legacy path. |
| `client/src/app_chat/main.cpp` | **A3.** Interactive stdin-driven chat binary. Matches `scripts/chat_cli.py` UX: slash commands `/sync /read /edit /del /contacts /add /presence /q`, non-slash lines = `send_message` on the configured conversation. Uses `ControlPlaneClient` + registers a `PushHandler` that pretty-prints MESSAGE_DELIVER / MESSAGE_EDITED / MESSAGE_DELETED / MESSAGE_READ_UPDATE / CONVERSATION_UPDATED. |
| `client/src/app_desktop/main.cpp` | **C1-C6c/C3e + registration/contacts/groups/timeline/profile/search/message-actions UI.** Qt Widgets desktop baseline. Provides host/port/conversation fields, login/register form, profile load/update controls, user discovery search with online/contact flags, chat-list filtering, selected-conversation message search with prev/next navigation, server-side search result cards, older-history loading for the selected conversation, left-side conversation list, rich read-only message timeline, composer, live push display, text send, reply/forward/reaction/pin controls, an Attach button, attachment-id save control, stage-based attachment transfer status, contacts add/remove/list controls, group create/member controls and a device-management panel. Device panel lists active/trusted devices, confirms destructive revoke, and can revoke non-current devices or toggle trust. Message rows render through `QTextBrowser` as styled inbound/outbound bubbles with timestamps, pending/sent/failed/read status, per-member group read details, reply/forward/reaction/pin metadata and search match/focused highlighting; rendered message ids are clickable `msg://` action targets and search navigation can promote the focused match into the action id field. Attachment rows show filename/size metadata, type previews and the save dialog defaults to the known filename. Includes `--smoke` / `--smoke-register` / `--smoke-attachment` / `--smoke-save-dir` mode for non-interactive validation of connect → login/register → local navigation/search → server message search → profile get/update → user search → sync → text send → reply/forward/reaction/pin → incremental sync → device list → contacts add/remove → group create → attachment send/fetch/save plus transfer-status markers. The UI renders from `DesktopChatStore`, loads `--cache-file` before network sync, sends cached cursors to `conversation_sync_since`, and writes after sync/send/push/select/action/history-page. |
| `client/src/app_desktop/desktop_chat_store.h/.cpp` | **C2/C6c/C3e + timeline/search/message actions.** GUI-facing local conversation/message store. Applies full `conversation_sync`, incremental sync, bounded older-history pages, local pending/sent/failed text and attachment send states and push envelopes (`message_deliver`, `message_edited`, `message_deleted`, `message_read_update`, `message_reaction_updated`, `message_pin_updated`), tracks selected conversation, unread counts for unselected conversations, read markers, per-conversation `last_message_id` plus `sync_version` cursors, and history-page `next_before_message_id` / `has_more`, retains timestamps, reply/forward metadata, reaction summary, pinned state, attachment IDs plus filename/mime/size/preview metadata for local sends/cache reloads, supports local conversation filtering and selected-conversation message search, renders both testable text transcript and rich HTML bubble snapshots with match/focused markers, and can save/load its JSON cache. Cached state displays first, then incremental sync merges missed messages, applies edit/delete/read-marker/reaction/pin deltas and updates title/participant metadata from the server. |

### 2.4 Controller placeholders

`client/src/{auth,chat,contacts,devices,remote_control}/*_controller.*` are
empty shells preserved from the original scaffold. They define module
boundaries but do not carry real logic — actual chat logic lives in
`transport/control_plane_client.cpp` today. When a UI layer (Qt / Android /
iOS) lands, these controllers are the intended attach points for
view-model orchestration.

---

## § 3. Shared protocol (`shared/include/shared/protocol/`)

C++ mirror of the Python `protocol.py`. Kept byte-identical wire values
across both sides.

| Header | Purpose |
|---|---|
| `message_types.h` | `enum class MessageType` + `to_string()`. Mirrors Python `MessageType` enum values. |
| `control_envelope.h` | Envelope fields (`type`, `correlation_id`, `session_id`, `actor_user_id`, `sequence`). |
| `errors.h` | `enum class ErrorCode` + `to_wire` / `from_wire` helpers. Matches Python `ErrorCode`. |
| `chat_models.h` | Shared struct shapes for conversation / message descriptors. |
| `remote_session.h` | Remote-session state enum + payload shapes. |

---

## § 4. Dev tooling

### 4.1 `scripts/chat_cli.py`

Interactive Python chat client. Same UX as `app_chat.exe`. Kept as a
dev-only tool — do not build UI on top of it. Used for quick two-terminal
manual testing.

### 4.2 Runtime validators

36 scripts. Each is standalone — no pytest, no fixture
framework. Convention: `SCENARIOS = [(name, fn), ...]`; each scenario
function raises on failure; `main()` returns non-zero if any fail.

| Validator | Covers |
|---|---|
| `validate_typed_errors.py` | Every `ErrorCode` has a human message + dispatch returns typed codes for the full known error set. |
| `validate_session_persistence.py` | Session counter recovery; session survives restart; no-state-file stays in-memory. |
| `validate_session_hardening.py` | Configured login-session TTL expiry, heartbeat refresh and zero-TTL legacy behavior. |
| `validate_tls_config.py` | Native TLS control-plane config guards: plaintext default, cert/key pair requirement and invalid material rejection. |
| `validate_tls_handshake.py` | Generates a temporary self-signed cert, starts the TLS control plane and performs a TLS login request. |
| `validate_tls_deployment_config.py` | Static checks for the Docker `nginx` TLS termination profiles and proxy configs, including the default SQLite service and PostgreSQL-backed service. |
| `validate_tls_dev_cert.py` | Verifies `generate_tls_dev_cert.py` emits usable PEM material and refuses accidental overwrite by default. |
| `validate_tls_proxy_smoke.py` | Performs a TLS login request through a Docker nginx stream proxy. Defaults to the SQLite-backed proxy on port 8443; can target the PostgreSQL-backed proxy on 8444. |
| `validate_cpp_tls_client.py` | Starts native TLS server mode and drives `app_chat.exe --tls --tls-insecure` through login/sync. Currently documents a local Schannel `SEC_E_NO_CREDENTIALS` blocker. |
| `validate_empty_state_file.py` | `_load_runtime_state` is defensive vs empty / whitespace / missing-path. |
| `validate_terminate_disconnect.py` | Remote session terminate + disconnect + post-terminal guards. |
| `validate_rendezvous.py` | Rendezvous state transitions + candidate list shape + actor auth. |
| `validate_udp_media.py` / `_auth.py` / `_relay.py` | UDP echo, per-session auth drop, peer relay, registry refresh. |
| `validate_media_frames.py` / `validate_screen_source.py` | Structured frame_chunk stream + synthetic screen source patterns. |
| `validate_input_injection.py` | Key/mouse/scroll input events, per-kind validation, seq monotonicity. |
| `validate_reliable_stream.py` | ReliableChannel under clean / drops / reorder / duplicate / 30 % random loss. |
| `validate_message_fanout.py` | Real TCP server, 2 clients, MESSAGE_DELIVER push to others + not to sender. |
| `validate_presence_heartbeat.py` | FakeClock + short TTL: login populates last_seen_at, heartbeat refreshes, stale flips offline. |
| `validate_registration.py` | Register flow, password hashed (not plaintext), uniqueness, persistence. |
| `validate_group_conversations.py` | Create, add/remove participant, fan-out, persistence. |
| `validate_incremental_sync.py` | C6 `conversation_sync` cursor semantics: newer messages only, no-change empty response, unknown-cursor full fallback, new conversation inclusion, edit/delete/read-marker deltas, membership metadata deltas, JSON/SQLite change-log persistence and compacted-log full fallback. |
| `validate_read_receipts.py` | mark_read advances pointer forward-only, push to others, sync exposes markers. |
| `validate_message_edit_delete.py` | Sender-only auth, push, soft-delete, reject after delete. |
| `validate_message_actions.py` | Reply metadata, forwarded-message metadata, reaction toggle summaries, pin/unpin state, fan-out, conversation_sync descriptors and SQLite persistence of action metadata. |
| `validate_message_search.py` | Server-side message search across accessible conversations, optional conversation scoping, non-participant exclusion, attachment filename matches and empty-query rejection. |
| `validate_history_paging.py` | Server-side history pages from newest to older with `next_before_message_id`, plus message-search offset paging without overlap. |
| `validate_contacts.py` | Add/remove/list, directed semantics, presence-aware online flag. |
| `validate_profile_search.py` | Current profile get/update, display-name validation and persistence, user search by identity/display text, self-exclusion, online/contact flags. |
| `validate_attachments.py` | Size cap, base64 validation, fetch auth, metadata-vs-blob separation, blob restart round-trip, legacy inline-base64 migration and sync descriptor coverage for attachment id plus filename/mime/size metadata. |
| `validate_cpp_chat_e2e.py` | Spawns Python server + 2 real `app_chat.exe` subprocesses, asserts bob's push handler prints alice's MESSAGE_DELIVER. |
| `validate_desktop_smoke.py` | Spawns Python server + real `app_desktop.exe --smoke`, asserts the Qt desktop target can connect, log in, exercise local chat/message navigation search, server message search through `ControlPlaneClient`, get/update profile, search users, sync, send, reply/forward/react/pin a message, perform incremental sync, list devices, add/remove a contact, create a group, send/fetch/save an attachment through `ControlPlaneClient`, emit upload/download/save transfer-status markers, and register a new account via `--smoke-register`. |
| `validate_device_management.py` | Covers trust/untrust, non-current device revoke, current-device revoke denial and SQLite persistence of trust state. |
| `validate_sqlite_persistence.py` | Exercises `--db-file` persistence for sessions, messages, contacts, remote sessions and attachments, plus a JSON-mode regression guard. |
| `validate_postgres_repository.py` | Exercises the PostgreSQL repository-backed runtime domains and schema version marker. |
| `validate_postgres_backup_restore.py` | App-level repository backup/restore round trip for messages, contacts, attachments and remote sessions. |
| `app_desktop_store_test.exe` | C++ store-level test binary covering sync initialization, sent/pushed message merge, attachment metadata and preview retention, edit/delete/read-marker/reaction/pin mutation, unread count for unselected conversations, cache save/load, full-sync reconciliation, incremental merge, edit and message-action delta application, metadata delta application, pending/failed local send state, group per-member read details, rich HTML bubble rendering, legacy timestamp fallback, local navigation search/filtering, clickable message-action targets and per-conversation cursor/version persistence. |

---

## § 5. Data flow example — `message_send` end-to-end

To anchor module responsibilities, here is what happens when Alice sends
a message from `app_chat.exe`:

1. `app_chat/main.cpp` reads stdin, calls `ControlPlaneClient::send_message(conv, text)`.
2. `control_plane_client.cpp` composes a `{type:"message_send", correlation_id:"rpc_N", payload:{conversation_id, text}, …}` envelope and calls `TcpLineClient::send_line`.
3. `tcp_line_client.cpp` sends `envelope + "\n"` through `net::native_send` — which on Windows becomes `::send(SOCKET, const char*, int, 0)`.
4. Server `control_plane.py::_ControlPlaneHandler` reads the line, hands it to `app.dispatch(message)`.
5. `app.py::dispatch` → `MESSAGE_SEND` branch → `ChatService.send_message` validates participant + non-empty + creates message record + calls `state.save_runtime_state()`.
6. `app.py` then calls `_fanout_to_conversation(...)` which iterates every participant session (via `state.sessions_for_user`), composes a `MESSAGE_DELIVER` envelope with `correlation_id="push_<msg_id>"` and recipient's `session_id`, and calls `connection_registry.push(sid, envelope)` — which grabs the target handler's write-lock and flushes the bytes.
7. The original handler writes the RPC response (typed MESSAGE_DELIVER with alice's own correlation_id) back to Alice's socket.
8. Alice's `TcpLineClient` reader-thread pushes the RPC response frame into the inbox; her `wait_for(match_correlation_id("rpc_N"))` returns it; `send_message` returns an `ok` result to app_chat.
9. Bob's `TcpLineClient` reader-thread pushes the `push_*` frame into his inbox; his dispatcher thread matches the `push_` predicate, calls his `PushHandler`, which in `app_chat` prints `[u_alice] <text>  (msg=msg_N)` to stdout.

---

## § 6. Build + run quick reference

```bash
# Server (Python 3.8+ stdlib — no venv needed for dev)
python -m server.main --tcp-server --port 8787 --state-file <path>.json

# Optional: also serve UDP media plane with a synthetic gradient source
python -m server.main --tcp-server --port 8787 --udp-port 8787 \
                     --screen-source gradient:24x16 --state-file <path>.json

# C++ client build (configure once, build many times)
cmake -S . -B build
cmake --build build --config Debug

# Interactive chat (two terminals)
./build/client/src/Debug/app_chat.exe --user alice --password alice_pw --device dev_alice_win
./build/client/src/Debug/app_chat.exe --user bob   --password bob_pw   --device dev_bob_win

# Python equivalent for quick testing
python scripts/chat_cli.py --user alice --password alice_pw --device dev_alice_win

# Run a validator (any one)
python scripts/validate_message_fanout.py

# Run all validators
for f in scripts/validate_*.py; do python "$f" 2>&1 | tail -2; done
```

---

## § 7. Delivery bundle (`.idea-to-code/telegram-platform/`)

Every milestone is recorded here via the `idea-to-code` skill's
`manage_delivery_bundle.py`. Not compiled or shipped — it is the audit
trail and trace matrix.

| File | Purpose |
|---|---|
| `status.json` | Machine-readable state: title, current_focus, next_gate, milestones[], requirements[], blockers[]. |
| `00-idea.md` | Original brief. |
| `01-requirements.md` / `02-prd.md` | Frozen requirement and PRD docs. |
| `03-milestones.md` | Auto-generated rollup; one entry per `checkpoint` call. |
| `04-verification.md` | Aggregated verification evidence. |
| `05-final-report.md` / `06-acceptance.md` | Produced by `finalize`. |

Run `python "$HOME/.claude/skills/idea-to-code/scripts/manage_delivery_bundle.py" verify --root . --slug telegram-platform` to sanity-check the matrix; non-zero exit means an open REQ is uncovered or a fail gate is unaddressed.

---

## § 8. Known gaps / deferred

| Area | Why it's not here yet |
|---|---|
| D9: AEAD on media plane | User deferred until after E-series. Crypto library still to pick (cryptography / pynacl). |
| ReliableChannel wired into UDP transport | Pure algorithm exists + validated; integration deferred. |
| POSIX compile path | Code structurally correct; no Linux/macOS CI; first real 2nd platform port will validate. |
| C++ client parity with E-series | `app_chat` covers send / read / edit / delete / contacts / presence. `app_desktop` now covers registration, profile update, user discovery, contacts, basic group creation/member management and attachments. Remaining parity gaps are mostly polish and deeper UX rather than missing core RPC surface. |
| Real database / Redis / object store | SQLite `--db-file` now provides a durable local database backend, but this is still single-process/dev-grade. PostgreSQL migrations, transactional repository boundaries and Redis-backed hot presence/session state remain future C4 work. |
| UI layer breadth (Android / iOS / Web) | Not started. Controller placeholders exist as attach points; only the Windows Qt desktop baseline exists today. |
| Product-grade desktop UI | C1-C6c/C3e plus registration/profile/user-discovery/contacts/groups/timeline/search/message-actions UI has a Qt Widgets shell backed by a local JSON cache, conversation list filtering, selected-chat message search, server-side message search result cards, older-history page loading, incremental reconnect sync, attachment send/save UI with filename/size metadata, lightweight type previews, stage-based transfer status, contacts/groups controls, device-management panel and rich bubble/timestamp/pending/sent/failed/read message rows with reply/forward/reaction/pin metadata and clickable action targets. It is not yet a full Telegram-like client: no polished design system, rich message-action cards/pickers, real decoded thumbnails, byte-level streaming progress or advanced conflict recovery metadata. |
| TLS/client transport parity | The Python TCP control plane can run native TLS with configured PEM material and has a real TLS login smoke. Docker includes `nginx` stream TLS termination profiles for the SQLite-backed service on 8443 and the PostgreSQL-backed service on 8444; a dev cert generator and proxy smoke validator are available. The SQLite proxy has live smoke evidence; PostgreSQL proxy live smoke is a pending action until approved. C++ clients expose `--tls` / `--tls-insecure` and `ControlPlaneClient::connect_tls` on Windows via Schannel, but direct runtime smoke is still partial because this environment returns `SEC_E_NO_CREDENTIALS` during credential acquisition. |
| Linux Docker deployment | `deploy/docker/server.Dockerfile`, `deploy/docker/docker-compose.yml`, `deploy/docker/README.md` and `scripts/deploy_wsl_docker.ps1` define the default Linux container path. The default server exposes 8787 and persists SQLite state plus attachments under `/data`; SQLite remains the default local-test backend. The `postgres` profile starts PostgreSQL plus `telegram-server-postgres` on port 8788 using `TELEGRAM_PG_DSN`. WSL Docker build/up/smoke has passed with Docker daemon proxy configured. |
| PostgreSQL repository boundary | `server/server/repositories.py` contains the production repository slice. `PostgresStateRepository` normalizes users, devices, sessions, conversations, messages, conversation change logs, contacts, attachment metadata and remote sessions into PostgreSQL tables in a single save transaction. It creates `schema_migrations`, records the current repository schema version, and is covered by a backup/restore round-trip validator. The JSONB runtime snapshot remains only as a compatibility fallback for older databases. `InMemoryState(pg_dsn=...)` delegates load/save to this repository; `--pg-dsn` / `TELEGRAM_PG_DSN` enable it. |
| Windows package staging | `scripts/package_windows_desktop.ps1` stages `app_desktop.exe`, `app_chat.exe` and `telegram_like_client.exe` from a CMake build output into `artifacts/windows-desktop/<timestamp>`, optionally includes PDBs, optionally runs `windeployqt`, emits `SHA256SUMS.txt`, and can emit a zip plus `.sha256` file. `scripts/validate_windows_package.ps1` verifies the package shape. This is staging/package handoff, not a signed installer yet. |

---

## § 9. Sibling docs

- `overall.md` — product direction, long-term phase plan (older, still mostly valid as vision)
- `server.md` / `client.md` — per-side deep-dive (descriptions of **intended** boundaries; reference this file for current state)
- `remote-control.md` / `telegram-compatibility.md` — subsystem notes
- `implementation-roadmap.md` — multi-phase plan
- `document-maintenance.md` — rule: docs are part of the implementation, update in the same change set
- `../flows/*.md` and `../diagrams/*.mmd` — user/system flow documents + Mermaid diagrams
