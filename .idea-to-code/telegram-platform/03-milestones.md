# Milestones

## Current Phase

- Status: in_progress
- Current focus: release-readiness — CI hardening
- Next gate: User direction

## Milestone History

## Artifact-driven skill upgrade

- Timestamp: 2026-04-20T05:26:28.072684+00:00
- Delivered: Strengthened the idea-to-code skill with persistent delivery bundle management and repository-backed milestone artifacts.
- Verified: Ran the bundle script commands against the telegram repo and inspected the generated files plus status output.
- Next: Use the same bundle while continuing typed protocol and UI work in the telegram project.
- Covers: REQ-CHAT-CORE

## Typed server request payloads

- Timestamp: 2026-04-20T05:39:53.945849+00:00
- Delivered: Converted login, message_send, remote_invite, and remote_approve request payloads into typed dataclasses and updated server dispatch to consume typed fields.
- Verified: Ran cmake --build build, python -m server.main, and a TCP end-to-end run with the Python server plus the C++ client executable.
- Next: Continue tightening the protocol boundary, likely with typed client response models or stronger server-side validation.
- Covers: REQ-CHAT-CORE, REQ-REMOTE-LIFECYCLE, REQ-TYPED-PROTO

## Typed client response models

- Timestamp: 2026-04-20T05:45:09.260611+00:00
- Delivered: Added typed client response parsing for login, device list, conversation sync, message delivery, remote session state, and relay assignment, then updated client state handling to consume typed response payloads.
- Verified: Ran cmake --build build, python -m server.main, and a TCP end-to-end run with python -m server.main --tcp-server plus the built C++ client executable.
- Next: Tighten protocol robustness further with explicit client-side error handling and stronger request or response validation.
- Covers: REQ-CHAT-CORE, REQ-REMOTE-LIFECYCLE, REQ-TYPED-PROTO

## Protocol error handling and validation

- Timestamp: 2026-04-20T05:50:46.084722+00:00
- Delivered: Added explicit server-side validation for invalid credentials, empty messages, conversation access, remote invite mismatches, and remote approval authorization, then surfaced protocol error responses into the client state and logs.
- Verified: Ran cmake --build build, python -m server.main, a TCP end-to-end run with python -m server.main --tcp-server plus the C++ client executable, and a targeted Python validation script covering invalid login, empty message send, and unauthorized remote approval.
- Next: Keep hardening the control plane with typed error codes or move into the next layer such as persistence and richer session lifecycle handling.
- Covers: REQ-CHAT-CORE, REQ-REMOTE-LIFECYCLE, REQ-VALIDATION

## Lightweight server persistence

- Timestamp: 2026-04-20T05:59:05.134820+00:00
- Delivered: Added JSON-backed runtime persistence for conversations and remote sessions, wired message and remote-session mutations to save state, restored counters from persisted records, and exposed a configurable --state-file entrypoint.
- Verified: Ran cmake --build build, python -m server.main, a TCP end-to-end run with python -m server.main --tcp-server --state-file <temp file> plus the C++ client executable, and a restart-focused Python validation script that verified message and remote-session state survive across app instances.
- Next: Move from file-backed snapshots toward richer lifecycle handling, likely explicit session termination/rejection/cancel flows or a more structured persistence layer.
- Covers: REQ-CHAT-CORE, REQ-PERSISTENCE, REQ-REMOTE-LIFECYCLE

## Remote session reject and cancel flows

- Timestamp: 2026-04-20T06:16:32.660948+00:00
- Delivered: Extended the control plane with explicit remote reject and cancel request handling, added terminated payload parsing on the client, and hardened remote-session service transitions for rejected and cancelled states.
- Verified: Ran cmake --build build, python -m server.main, a TCP end-to-end run with python -m server.main --tcp-server --state-file <temp file> plus the built C++ client executable, and a targeted Python lifecycle script covering reject, cancel, and invalid follow-up transitions.
- Next: Push the remote-control lifecycle further with termination/disconnect flows and then start separating control-plane events from eventual media-plane orchestration.
- Covers: REQ-REMOTE-LIFECYCLE

## Remote session terminate and disconnect flows (gate: pass)

- Timestamp: 2026-04-20T08:31:02+00:00
- Delivered: Added REMOTE_TERMINATE / REMOTE_DISCONNECT protocol messages (server + shared + C++ client), terminate/disconnect methods on RemoteSessionService with active-state guard and actor authorization, terminated/disconnected records with detail payloads, and a C++ demo terminate call in app_shell. RemoteDisconnectRequestPayload carries optional reason.
- Verified: Ran cmake --build build, started python -m server.main --tcp-server --state-file <temp>, exercised the C++ client which now ends with a terminate round-trip, and ran scripts/validate_terminate_disconnect.py covering 8 lifecycle scenarios (terminate by requester/target, disconnect with reason, pre-approval terminate -> not_active, double terminate -> already_terminal, non-participant -> invalid_session, actor mismatch -> session_actor_mismatch, disconnect-after-terminate -> already_terminal).
- Next: Start separating control-plane events from the media-plane (rendezvous info + relay handshake) or push into structured persistence / typed error codes.
- Covers: REQ-REMOTE-LIFECYCLE, REQ-TYPED-PROTO, REQ-VALIDATION
## Robust state-file loading (gate: pass)

- Timestamp: 2026-04-20T09:12:42+00:00
- Delivered: InMemoryState._load_runtime_state now treats empty / whitespace-only state files as 'start fresh' instead of crashing with JSONDecodeError. Discovered during end-to-end TCP run when mktemp produced an empty file.
- Verified: python scripts/validate_empty_state_file.py passes 4 scenarios: empty file, whitespace-only file, missing nested path (parent created on first save), and non-empty existing file (regression guard for persistence round-trip).
- Next: Move into the media-plane handshake (REMOTE_RENDEZVOUS_REQUEST → REMOTE_RENDEZVOUS_INFO, approved→negotiating state transition).
- Covers: REQ-PERSISTENCE

## Media-plane rendezvous handshake (Plan A) (gate: pass)

- Timestamp: 2026-04-20T09:23:03+00:00
- Delivered: New REMOTE_RENDEZVOUS_REQUEST / REMOTE_RENDEZVOUS_INFO control-plane exchange. RemoteSessionService.request_rendezvous() validates actor+state, transitions approved->negotiating on first call, and returns an ICE-style candidate list (host/host/srflx/relay) plus relay metadata. Typed payloads on both sides: server RemoteRendezvousInfoPayload + RemoteRendezvousCandidate dataclasses; client RemoteRendezvousInfoPayload + RemoteRendezvousCandidate structs added to the response variant; RemoteControlState now tracks candidate_count. app_shell demo now issues an alice rendezvous request between approve and terminate.
- Verified: cmake --build build (clean); python scripts/validate_rendezvous.py 6/6 (approved->negotiating; idempotent in negotiating; awaiting_approval -> not_ready; terminated -> not_ready; actor mismatch -> session_actor_mismatch; unknown session -> unknown_remote_session); regression passes on validate_terminate_disconnect.py 8/8 and validate_empty_state_file.py 4/4; TCP end-to-end run shows rendezvous yielding 4 candidates with correct kinds and relay info, state transitioning approved->negotiating.
- Next: Move toward real media-plane bytes: either structured persistence for sessions, typed error-code enum, or a minimal UDP media channel between rendezvous candidates.
- Covers: REQ-MEDIA-RENDEZVOUS, REQ-REMOTE-LIFECYCLE, REQ-TYPED-PROTO

## Typed error codes (gate: pass)

- Timestamp: 2026-04-20T09:51:08+00:00
- Delivered: Introduced ErrorCode enum in shared C++ header (kInvalidCredentials .. kRemoteSessionNotReadyForRendezvous, 23 members + to_wire/from_wire helpers) and a matching Python StrEnum. New ServiceError exception carries a typed ErrorCode; all 23 raise sites in auth/chat/remote_session services converted. ERROR responses now emit {code: <wire>, message: <human>} via a new ErrorResponsePayload dataclass/struct; dispatch fallback for unsupported message types and transport-level errors also use typed codes. Client parser reads code, ClientViewState exposes last_error_code alongside last_error_message, app_shell prints both.
- Verified: cmake --build build clean. python scripts/validate_typed_errors.py 11/11 (invalid_credentials, invalid_session, session_actor_mismatch, unknown_conversation, empty_message, unknown_target_device, self_remote, remote_approval_denied, rendezvous_not_ready, unsupported_message_type, code-catalog completeness). Regressions pass: terminate_disconnect 8/8, rendezvous 6/6, empty_state_file 4/4. TCP end-to-end run unchanged on happy path; last_error_code field visible in client state prints.
- Next: Milestone A — persist login sessions across server restart.
- Covers: REQ-TYPED-ERRORS, REQ-TYPED-PROTO, REQ-VALIDATION

## Session persistence (gate: pass)

- Timestamp: 2026-04-20T10:03:23+00:00
- Delivered: InMemoryState now persists the sessions dict alongside conversations and remote sessions. Load path reconstructs SessionRecord entries. AuthService counter recovered from highest persisted sess_N (parallel to RemoteSessionService._next_remote_counter). login() triggers save_runtime_state() so each issued session hits disk immediately.
- Verified: scripts/validate_session_persistence.py 5/5 (session survives restart, counter skips past persisted max, no-state-file keeps memory-only semantics, unknown session still returns typed INVALID_SESSION, cumulative persistence across conversations+remote_sessions+sessions). Regressions intact: typed_errors 11/11, terminate_disconnect 8/8, rendezvous 6/6, empty_state_file 4/4.
- Next: Milestone C — first real media-plane byte channel (UDP echo bound to relay port, C++ probe after rendezvous).
- Covers: REQ-SESSION-PERSIST, REQ-PERSISTENCE

## First UDP media-plane byte channel (gate: pass)

- Timestamp: 2026-04-20T10:11:37+00:00
- Delivered: New server/server/media_plane.py hosts a threaded UDP echo (ThreadedUdpMediaServer) with a tiny framing scheme (4-byte sid length + session_id + payload) and a client helper send_probe. server/main.py exposes --udp-port (0 = disabled). C++ client gains transport/udp_media_probe.{h,cpp} — a Winsock UDP probe with configurable timeout that frames identically. app_shell triggers the probe after alice's rendezvous when TELEGRAM_LIKE_UDP_PORT is set, prints ack=yes|no + byte count + text. chat_client_core now exports ws2_32 publicly so the UDP file links cleanly.
- Verified: scripts/validate_udp_media.py 5/5 (basic echo, empty/small/near-MTU payloads, 3 distinct session ids don't corrupt each other, MAX_PACKET_SIZE constant present, thread shuts down cleanly). TCP+UDP end-to-end with --udp-port 9001 --state-file <tmp>: C++ client prints 'udp probe ack=yes bytes=39 text=ack:sess_1:hello from alice media plane'. Regressions all green: typed_errors 11/11, session_persistence 5/5, terminate_disconnect 8/8, rendezvous 6/6, empty_state_file 4/4.
- Next: Wire the UDP probe into the rendezvous response by routing the probe to relay_endpoint port; add per-session validation on the UDP path; then move toward real screen-capture / input-injection payloads.
- Covers: REQ-MEDIA-BYTE-CHANNEL, REQ-MEDIA-RENDEZVOUS, REQ-TYPED-PROTO

## Per-session UDP media-plane auth (gate: pass)

- Timestamp: 2026-04-20T10:38:03+00:00
- Delivered: ThreadedUdpMediaServer gains optional authorizer callback; _UdpEchoHandler checks it and silently drops unauthorized packets. Crucial subtlety: DatagramRequestHandler.finish() unconditionally replies with wfile.getvalue(), so a bare return emits a zero-length ACK — overrode finish() to honour a _drop flag and actually stay silent. server/main.py now constructs ServerApplication up front and passes it into both serve_udp_in_thread (as the authorizer's backing state) and serve_tcp (new keyword arg), giving both planes a shared InMemoryState. control_plane.serve_tcp accepts an optional pre-built app without breaking existing callers. Authorization rule: session_id must map to a logged-in user who is currently a participant in at least one active (approved/negotiating/connecting/streaming/controlling) remote session.
- Verified: scripts/validate_udp_media_auth.py 5/5 (unknown session_id drops silently, logged-in-only drops, approved-participant echoes, terminate flips back to drop, no-authorizer keeps legacy accept-all behaviour). Full regression green: validate_udp_media 5/5, validate_typed_errors 11/11, validate_session_persistence 5/5, validate_terminate_disconnect 8/8, validate_rendezvous 6/6, validate_empty_state_file 4/4.
- Next: Switch UDP from pure echo to a structured media frame (frame_chunk with seq + payload), driven by session state; start real media semantics on top of this auth gate.
- Covers: REQ-MEDIA-AUTH, REQ-MEDIA-BYTE-CHANNEL, REQ-REMOTE-LIFECYCLE

## Structured frame_chunk stream (gate: pass)

- Timestamp: 2026-04-20T10:52:18+00:00
- Delivered: Media plane now emits structured frame_chunk datagrams on subscribe. Payload grammar: envelope(sid_len|sid|body) where body is either legacy echo or subscribe 'SUB:<count>:<cookie>' -> server emits <count> frame_chunks (kind=F | u32 seq | u32 len | payload). Frame payload is deterministic (_fake_frame_payload: b'frame-<n>|<cookie>') for byte-exact assertions. Auth gate from D1 still applies — unauthorized subscribe drops silently. MAX_FRAME_COUNT=32 caps abusive counts. build_frame_chunk / parse_frame_chunk / build_subscribe_payload / subscribe_and_collect are the public surface for callers. Legacy echo preserved so validate_udp_media stays green. Binary wire format kept tiny (9-byte header per frame).
- Verified: scripts/validate_media_frames.py 6/6 (subscribe N=5 returns seq 1..5 with exact payload bytes, subscribe N=0 is silent, cookie round-trip, legacy echo still works, unauthorized subscribe silent-drops, MAX_FRAME_COUNT cap honored). Full regression 44/44: udp_media_auth 5/5, udp_media 5/5, typed_errors 11/11, session_persistence 5/5, terminate_disconnect 8/8, rendezvous 6/6, empty_state_file 4/4.
- Next: D3 — wire a C++ UDP subscribe/frame-receiver into the client so app_shell demo can print received seq numbers after rendezvous (mirrors validate_media_frames.py logic in the client).
- Covers: REQ-MEDIA-FRAME-STREAM, REQ-MEDIA-AUTH, REQ-MEDIA-BYTE-CHANNEL

## Structured frame payload header (gate: pass)

- Timestamp: 2026-04-20T11:02:45+00:00
- Delivered: frame_chunk payload body now starts with a 12-byte structured header: u16 width | u16 height | u32 timestamp_ms | u8 codec | 3 reserved. New helpers build_frame_payload / parse_frame_payload keep the struct format in one place. _fake_frame_payload wraps the old deterministic body (frame-<n>|<cookie>) with the header — existing byte-exact assertions keep passing, new assertions verify structured fields (640x360, CODEC_RAW, 33ms*seq timestamps). CODEC_RAW=1 placeholder until we pick something real.
- Verified: scripts/validate_media_frames.py 7/7 including new parse_frame_payload round-trip scenario and field-level assertions in the basic stream scenario. Legacy cookie/echo/auth/cap regressions all still green.
- Next: D3 — C++ udp_frame_stream module to consume these structured frames; app_shell prints seq/width/height/codec after rendezvous.
- Covers: REQ-FRAME-HEADER, REQ-MEDIA-FRAME-STREAM

## C++ UDP frame_chunk consumer (gate: pass)

- Timestamp: 2026-04-20T11:33:48+00:00
- Delivered: New client/src/transport/udp_frame_stream.{h,cpp} — Winsock UDP subscribe + frame_chunk parser that mirrors server/server/media_plane.py wire format byte-for-byte (sid_len|sid envelope | 'F' kind | u32 seq | u32 payload_len | u16 w | u16 h | u32 ts | u8 codec | 3 rsv | body). subscribe_and_collect returns FrameChunk structs with parsed header fields. CMakeLists adds the new translation unit. app_shell now, when TELEGRAM_LIKE_UDP_PORT is set, performs the post-rendezvous probe *and* a subscribe(5, 'demo'), then prints each frame's seq / width×height / codec / ts / body_bytes.
- Verified: cmake --build clean. TCP+UDP end-to-end: C++ client prints 5 received frames with correct header fields (640x360, codec=1, ts=33ms*seq, body_bytes=12). Full regression 51/51 across 8 validators (media_frames 7/7, udp_media_auth 5/5, udp_media 5/5, typed_errors 11/11, session_persistence 5/5, terminate_disconnect 8/8, rendezvous 6/6, empty_state_file 4/4).
- Next: D5 — synthetic screen capture: server reads one PPM/BMP frame and streams its pixel rows as frame_chunk bodies; width/height come from the real image, not the hardcoded 640x360.
- Covers: REQ-CPP-FRAME-CONSUMER, REQ-FRAME-HEADER, REQ-MEDIA-FRAME-STREAM

## Synthetic screen capture source (gate: pass)

- Timestamp: 2026-04-20T11:55:05+00:00
- Delivered: New server/server/screen_source.py with a ScreenSource Protocol and StaticImageScreenSource implementation. Four bundled patterns (gradient/black/white/red) built via build_test_pattern; make_test_pattern_source(width, height, pattern) is the public factory. ThreadedUdpMediaServer accepts optional screen_source; handler calls source.next_frame(seq, cookie) when present and falls back to _fake_frame_payload when absent — backward compatible with every existing validator. server/main.py gains --screen-source '<pattern>[:WxH]' flag. End-to-end with --screen-source gradient:24x16: C++ client now prints real 24x16 RGB gradient frames (1156 body bytes = 1152 pixels + cookie).
- Verified: validate_screen_source 5/5 (gradient pixel pin, solid red, no-source regression, custom dims propagate, unknown pattern rejected). Full regression 56/56 across 9 validators. TCP+UDP end-to-end confirmed: C++ receives 24x16 codec=1 frames reflecting real source dims.
- Next: D6 — client -> server input events (keyboard/mouse) over the control plane; new InputService + REMOTE_INPUT_EVENT message type.
- Covers: REQ-SCREEN-SOURCE, REQ-FRAME-HEADER, REQ-MEDIA-FRAME-STREAM

## Input event injection (control plane) (gate: pass)

- Timestamp: 2026-04-20T12:04:42+00:00
- Delivered: Two new protocol message types (REMOTE_INPUT_EVENT / REMOTE_INPUT_ACK) cross server (Python StrEnum) and shared C++ header. RemoteInputEventRequestPayload carries {remote_session_id, kind, data}; RemoteInputAckPayload returns {remote_session_id, sequence, kind}. Three new typed error codes: REMOTE_INPUT_DENIED, UNSUPPORTED_INPUT_KIND, INVALID_INPUT_PAYLOAD (+ human messages). New InputService validates four kinds (key, mouse_move, mouse_button, scroll) with per-kind required data-field schemas, authorizes only the requester of an active remote session, records an in-memory monotonic event log. dispatch branch in app.py wires it.
- Verified: validate_input_injection 9/9: ack payload contents, seq monotonic across 4 kinds, target-user denied, unknown remote_session, pre-approval rejected, terminated rejected, unknown kind, missing-data fields, 4-kind log round-trip. Full regression 65/65 across 10 validators.
- Next: D7 — real relay: server routes bytes between two connected clients (not just server-generated frames). Needs per-session socket bookkeeping + routing table + a second C++ client instance or a Python peer in validators.
- Covers: REQ-INPUT-INJECT, REQ-TYPED-PROTO, REQ-VALIDATION, REQ-TYPED-ERRORS

## Server-side UDP relay (gate: pass)

- Timestamp: 2026-04-20T12:11:03+00:00
- Delivered: ThreadedUdpMediaServer now carries a peer_registry (session_id -> last-seen addr) protected by a lock. Every authorized inbound packet refreshes the registry — no separate control-plane roundtrip needed. Two new wire verbs inside the sid_len|sid envelope: HELLO (register-only, no reply) and RELAY:<target_sid>:<body> (server forwards body to target's registered addr as envelope(sender_sid, body)). Unknown target, malformed relay, and unauthorized sender all silently drop (D1's rule carries through). Python client helpers build_relay_payload / build_hello_payload / send_hello / open_peer_socket for multi-peer tests and future C++ mirror.
- Verified: validate_udp_relay 6/6: unidirectional A→B, bidirectional ping/pong, unknown target silent drop, unauthorized sender silent drop, malformed RELAY drop, registry refresh on ephemeral port change. Regression 71/71 across 11 validators.
- Next: D8 — UDP reliability layer (seq tracking, NACK-based retransmit, ordering buffer). Likely its own session because it's substantial.
- Covers: REQ-UDP-RELAY, REQ-MEDIA-AUTH, REQ-MEDIA-BYTE-CHANNEL

## UDP reliability layer (ReliableChannel) (gate: pass)

- Timestamp: 2026-04-20T12:31:12+00:00
- Delivered: New server/server/reliable_stream.py — transport-agnostic ReliableChannel class. Wire verbs REL:<seq>:<body>, NAK:<seq_list>, ACK:<high_water>. Sender assigns monotonic seqs, keeps unacked buffer, retransmits on NAK, trims buffer on cumulative ACK, exposes tick_retransmit() for tail-loss timer-driven recovery. Receiver buffers out-of-order arrivals, drains contiguous seqs in-order on delivery, re-NAKs on every gap-creating packet (dropped NAKs / retransmits recover), emits cumulative ACK as high-water advances, ignores duplicates. Pure algorithm module — not yet wired into the UDP transport (left for a later integration milestone).
- Verified: validate_reliable_stream 5/5 via lossy/reorder/duplicate fake transport: clean 10-pkt stream no NAKs, seq 3+7 drop triggers NAK+retx, seq 4/5 reorder buffered+drained in order, duplicate seq 2 silently dropped, 30% random loss on 20 packets delivers everything in order via NAK-driven retx + tick tail-loss recovery. Regression 76/76 across 12 validators.
- Next: D9 — DTLS on the media plane. Needs an external crypto library (pynacl or cryptography). Will pause at start of next session to confirm dependency choice.
- Covers: REQ-UDP-RELIABILITY

## Chat message fan-out (E1) (gate: pass)

- Timestamp: 2026-04-20T12:49:40+00:00
- Delivered: New ConnectionRegistry (server/server/connection_registry.py) keys session_id -> thread-safe writer callable. _ControlPlaneHandler registers on successful login and unregisters in a finally block, with a per-connection write lock that serializes response writes with async pushes. ServerApplication._fanout_message_deliver pushes a MESSAGE_DELIVER envelope (correlation_id='push_<msg_id>', session_id set to recipient) to every participant session except the origin session — multi-device participants see their own pushes too. InMemoryState.sessions_for_user helper added. SessionRecord gains last_seen_at:float=0.0 (unused here, groundwork for E4) with backward-compatible load path.
- Verified: validate_message_fanout.py 4/4 — push_to_other_participant (bob gets push with push_* correlation, alice gets only response), push_to_other_session_of_same_user (alice's session B gets push when she sends from session A), no_crash_when_participant_logged_out, multiple_messages_arrive_in_order (5 sequential sends arrive at receiver in-order). Regression sampled: session_persistence 5/5, typed_errors 11/11, input_injection 9/9 — no breakage from the SessionRecord field addition.
- Next: E4 — heartbeat + TTL presence: HEARTBEAT_PING/ACK messages, PRESENCE_QUERY_REQUEST/RESPONSE, last_seen_at populated on login and heartbeat, is_device_online/is_user_online use TTL.
- Covers: REQ-CHAT-FANOUT, REQ-CHAT-CORE, REQ-TYPED-PROTO

## Presence heartbeat + TTL-based online (E4) (gate: pass)

- Timestamp: 2026-04-20T12:52:57+00:00
- Delivered: Four new message types (HEARTBEAT_PING/ACK, PRESENCE_QUERY_REQUEST/RESPONSE) with typed dataclass payloads. AuthService takes a clock callable; SessionRecord.last_seen_at is populated on login. PresenceService takes clock + ttl_seconds (default 30s); touch() refreshes timestamps + persists; is_session_fresh / is_device_online / is_user_online all compare (now - last_seen_at) <= ttl; query_users returns PresenceUserStatus list with online bool + last_seen_at_ms; list_devices.active now routes through the TTL check rather than plain 'session exists'. ServerApplication accepts clock + presence_ttl_seconds constructor args, dispatches HEARTBEAT_PING (touches + returns HEARTBEAT_ACK with server_timestamp_ms and echoed client_timestamp_ms) and PRESENCE_QUERY_REQUEST (returns per-user status + server_timestamp_ms).
- Verified: validate_presence_heartbeat.py 6/6 via fake clock + ttl=5s: login_populates_last_seen (session.last_seen_at=1000.0, user/device online), stale_session_flips_offline (still online at 4.9s past TTL, offline at 5.1s past), heartbeat_refreshes_last_seen (heartbeat at t=4s keeps online at t=8.9s, offline at t=9.1s; ACK echoes client_ts and reports server_ts=1004000ms), presence_query_returns_typed_status (alice/bob online, ghost offline + last_seen_at_ms=0), device_list_active_mirrors_ttl (device.active flips after 6s stale), multi_session_user_online_if_any_fresh (user counts online if any session is within TTL). Full regression 86/86 across 14 validators — no breakage.
- Next: E2 (registration) — will need F2 password hashing pulled forward. OR E5 group conversations / E6 read receipts / E7 edit-delete / E8 contacts / E3 attachments as the remaining chat-completeness arc.
- Covers: REQ-PRESENCE-HEARTBEAT, REQ-TYPED-PROTO, REQ-CHAT-CORE

## Registration + password hashing (E2+F2) (gate: pass)

- Timestamp: 2026-04-20T13:23:02+00:00
- Delivered: New server/server/crypto.py: PBKDF2-SHA256 (120k iters, 16B salt, 32B derived) via stdlib hashlib + hmac.compare_digest. Format 'pbkdf2_sha256$iter$salt_hex$hash_hex'. UserRecord.password -> UserRecord.password_hash (rename); seed users (alice/bob) hashed at module init via hash_password(). state.py save_runtime_state now persists users + devices; load path accepts legacy 'password' key by re-hashing on read for migration. AuthService.login switched to verify_password. New AuthService.register validates username pattern (^[A-Za-z0-9_][A-Za-z0-9_.-]{2,31}$), min password len 8, unique username (case-insensitive), unique device_id, non-empty display_name; creates UserRecord+DeviceRecord+SessionRecord atomically with hashed password. New message types REGISTER_REQUEST/RESPONSE + RegisterRequestPayload/RegisterResponsePayload. New error codes USERNAME_TAKEN / WEAK_PASSWORD / DEVICE_ID_TAKEN / INVALID_REGISTRATION_PAYLOAD with matching human messages. Dispatch branch in app.py wires it.
- Verified: validate_registration.py 7/7 (seed users still login, register+login round-trip, password stored as pbkdf2_sha256$... not plaintext, duplicate username rejected, weak password rejected, duplicate device rejected, malformed usernames rejected incl empty/short/space/emoji/leading-dash, new account survives state-file restart). validate_typed_errors.py 11/11 — code-catalog completeness picked up the 4 new codes with human messages.
- Next: E5 — group conversations: CONVERSATION_CREATE / CONVERSATION_ADD_PARTICIPANT / CONVERSATION_REMOVE_PARTICIPANT; fan-out unchanged; persist membership.
- Covers: REQ-USER-REGISTRATION, REQ-PASSWORD-HASH, REQ-TYPED-PROTO, REQ-TYPED-ERRORS, REQ-PERSISTENCE

## Group conversations (E5) (gate: pass)

- Timestamp: 2026-04-20T13:26:33+00:00
- Delivered: ConversationRecord gains title:str. ChatService gains create_conversation (dedupes participants, rejects unknown user_ids, rejects <2 total), add_participant (auth via existing-participant check, rejects duplicates + unknown users), remove_participant (same auth, rejects not-present). Three new message types CONVERSATION_CREATE / CONVERSATION_ADD_PARTICIPANT / CONVERSATION_REMOVE_PARTICIPANT; CONVERSATION_UPDATED is used as both the response type and the fan-out push type. Four new error codes: UNKNOWN_USER, CONVERSATION_PARTICIPANT_ALREADY_PRESENT, CONVERSATION_PARTICIPANT_NOT_PRESENT, CONVERSATION_TOO_FEW_PARTICIPANTS. Fan-out helper refactored: _fanout_message_deliver split into _fanout_to_conversation + _fanout_to_users (reusable for any conversation-scoped push); dedupes sessions via a seen set. Remove-participant fan-out explicitly notifies the kicked user too (so their client learns they left).
- Verified: validate_group_conversations.py 6/6 — create 3-person group, dedupe + unknown-user + too-few, add/remove lifecycle incl duplicate-add + missing-remove, non-participant cannot modify, fan-out on create + send + remove (kicked user still gets notified), persistence across restart. Regressions green: validate_message_fanout 4/4, validate_typed_errors 11/11 (new codes all have human messages), validate_session_persistence 5/5.
- Next: E6 — read receipts: MESSAGE_READ + per-user last-read pointer persisted; MESSAGE_READ_UPDATE fanned out to other participants.
- Covers: REQ-GROUP-CONVERSATIONS, REQ-TYPED-PROTO, REQ-TYPED-ERRORS, REQ-PERSISTENCE, REQ-CHAT-FANOUT

## Read receipts (E6) (gate: pass)

- Timestamp: 2026-04-20T13:28:45+00:00
- Delivered: ConversationRecord gains read_markers: dict[user_id -> last_read_message_id] persisted; ConversationDescriptor exposes the same via CONVERSATION_SYNC. New MESSAGE_READ / MESSAGE_READ_UPDATE messages with MessageReadRequestPayload / MessageReadUpdatePayload dataclasses. ChatService.mark_read enforces participant access, rejects unknown message_id with typed UNKNOWN_MESSAGE, and advances the pointer forward-only (if the user tries to mark an older message the pointer stays put). Dispatch branch pushes MESSAGE_READ_UPDATE via _fanout_to_conversation to other participants; reader gets the synchronous response.
- Verified: validate_read_receipts.py 6/6: mark-read advances pointer + pushes to other participants (reader only gets response, no echo push), forward-only advancement (mark m3 then m1 stays at m3), unknown_message rejected, non-participant access_denied, read_markers surface in conversation_sync, markers persist across state-file restart.
- Next: E7 — message edit/delete: MESSAGE_EDIT / MESSAGE_DELETE; sender-only auth; MESSAGE_EDITED / MESSAGE_DELETED push; soft-delete with deleted=true flag.
- Covers: REQ-READ-RECEIPTS, REQ-TYPED-PROTO, REQ-TYPED-ERRORS, REQ-PERSISTENCE, REQ-CHAT-FANOUT

## Message edit + delete (E7) (gate: pass)

- Timestamp: 2026-04-20T13:30:47+00:00
- Delivered: Four new message types: MESSAGE_EDIT / MESSAGE_EDITED (request + push), MESSAGE_DELETE / MESSAGE_DELETED (request + push). Three new typed error codes: MESSAGE_EDIT_DENIED, MESSAGE_DELETE_DENIED, MESSAGE_ALREADY_DELETED. MessageDescriptor gains edited:bool + deleted:bool so CONVERSATION_SYNC and pushed descriptors show the flags. ChatService.edit_message: sender-only, rejects empty text + already-deleted. ChatService.delete_message: sender-only, soft-delete sets deleted=True + text='', rejects double-delete. Both push to other participants via _fanout_to_conversation; sender gets the response, others get push. Storage keeps the message record (for id continuity / read-marker references); only text + edited/deleted flags change.
- Verified: validate_message_edit_delete.py 8/8: edit own + push, edit others denied, edit empty rejected, delete own soft-deletes + push + sync sees it, double-delete rejected, edit after delete rejected, delete others denied, unknown message rejected. All existing validators should remain green — will sweep at end of arc.
- Next: E8 — per-user directed contact lists with add/remove/list.
- Covers: REQ-MESSAGE-EDIT-DELETE, REQ-TYPED-PROTO, REQ-TYPED-ERRORS, REQ-CHAT-FANOUT, REQ-PERSISTENCE

## Contacts (E8) (gate: pass)

- Timestamp: 2026-04-20T13:32:28+00:00
- Delivered: New server/server/services/contacts.py ContactsService: directed per-user contact list keyed by owner_user_id. InMemoryState.contacts: dict[owner_user_id -> list[target_user_id]] persisted as-is + loaded with default empty dict. Four new message types: CONTACT_ADD / CONTACT_REMOVE / CONTACT_LIST_REQUEST / CONTACT_LIST_RESPONSE. ContactDescriptor (user_id + display_name + online) uses PresenceService.is_user_online for real-time online flag. Three new typed error codes: CONTACT_SELF_NOT_ALLOWED, CONTACT_ALREADY_ADDED, CONTACT_NOT_PRESENT. Dispatch branches: add returns updated list, remove returns updated list, list_request returns current list.
- Verified: validate_contacts.py 8/8: add-then-list shows contact + display_name, duplicate add rejected, self add rejected, unknown user rejected, remove without presence rejected then add+remove works, directed semantics (alice adds bob; bob's list stays empty), online flag flips with presence TTL (via injected FakeClock), contacts persist across state-file restart.
- Next: E3 — attachments: binary-capable messages with filename/mime/base64 body + size cap, persisted server-side, fetched via ATTACHMENT_FETCH.
- Covers: REQ-CONTACTS, REQ-TYPED-PROTO, REQ-TYPED-ERRORS, REQ-PERSISTENCE, REQ-PRESENCE-HEARTBEAT

## Attachments (E3) (gate: pass)

- Timestamp: 2026-04-20T13:34:54+00:00
- Delivered: AttachmentRecord in state (attachment_id, conversation_id, uploader_user_id, filename, mime_type, size_bytes, content_b64) + InMemoryState.attachments persisted. MessageDescriptor + MessageDeliverPayload gain attachment_id (plus filename/mime/size on delivery so recipients know what to fetch); MESSAGE_DELIVER wire payload intentionally omits the body — receivers issue ATTACHMENT_FETCH_REQUEST to pull the bytes. Three new message types: MESSAGE_SEND_ATTACHMENT / ATTACHMENT_FETCH_REQUEST / ATTACHMENT_FETCH_RESPONSE. Four new typed error codes: ATTACHMENT_TOO_LARGE, INVALID_ATTACHMENT_PAYLOAD, UNKNOWN_ATTACHMENT, ATTACHMENT_ACCESS_DENIED. ChatService.send_attachment_message validates: participant access, filename non-empty, declared size 0..1MB, base64 decodes cleanly (strict validate=True), actual decoded length matches declared size_bytes; stores record + creates linked message with attachment_id. ChatService.fetch_attachment gates access to conversation participants only. MAX_ATTACHMENT_SIZE_BYTES=1_048_576.
- Verified: validate_attachments.py 8/8: send+fanout (push has attachment_id but no content_b64) + fetch round-trip byte-exact, size cap enforced, declared/actual size mismatch rejected, invalid base64 rejected, non-participant fetch denied, unknown attachment rejected, content persists across restart (byte-exact round trip), message_descriptor in CONVERSATION_SYNC exposes attachment_id + caption as text.
- Next: Full E-series done. Optional next direction: D9 (media-plane AEAD — needs crypto-library choice), rest of F-series, or polish / bug-fix round.
- Covers: REQ-ATTACHMENTS, REQ-TYPED-PROTO, REQ-TYPED-ERRORS, REQ-PERSISTENCE, REQ-CHAT-FANOUT

## C++ net/ abstraction layer (B1) (gate: pass)

- Timestamp: 2026-04-20T14:11:59+00:00
- Delivered: New client/src/net/ module: platform.h (NativeSocket alias, is_valid, close_native_socket, set_recv_timeout_ms, native_send/recv/sendto/recvfrom — all with #ifdef _WIN32 vs POSIX branches), socket_error.h/.cpp (NetErrorCode enum + last_native_error + map_native_error for WSAE* and errno), socket_subsystem.h/.cpp (refcounted WSAStartup/WSACleanup on Win, no-op on POSIX), socket_raii.h (move-only Socket wrapper). Refactored session_gateway_client.cpp / udp_media_probe.cpp / udp_frame_stream.cpp to route all socket calls through net/. Removed per-file WSAStartup calls (3 scattered -> 1 shared SocketSubsystem with refcount). CMakeLists: splits ws2_32 (WIN32) vs Threads::Threads (non-Win); added 2 new net/*.cpp sources. POSIX branch is structural only — compile-tested by shape, not yet exercised on a Linux/macOS box (first real port will validate).
- Verified: cmake --build build --config Debug green. Python server-side UDP validators unchanged: validate_udp_media 5/5 and validate_udp_media_auth 5/5. End-to-end app_shell against python server on 8787 (+ --udp-port 8787 --screen-source gradient:24x16) prints 'udp probe ack=yes bytes=39 text=ack:sess_1:hello from alice media plane' and 5 frame_chunks at 24x16 codec=1, ts=33/66/99/132/165ms body_bytes=1156 — byte-identical to pre-refactor behavior.
- Next: A1 — TcpLineClient primitive built on net/: async reader thread + thread-safe writer + wait_for(correlation_id|type, timeout) inbox.
- Covers: REQ-NET-ABSTRACTION, REQ-CPP-FRAME-CONSUMER, REQ-MEDIA-BYTE-CHANNEL

## TcpLineClient primitive (A1) (gate: pass)

- Timestamp: 2026-04-20T14:16:52+00:00
- Delivered: client/src/net/tcp_line_client.h/.cpp: async TCP JSON-line client built on net/. Background reader thread drains '\n'-delimited frames into std::deque<std::string> behind mutex + condvar. send_line() is thread-safe with a separate write mutex. wait_for(predicate, timeout_ms) blocks until a frame matching predicate arrives; unmatched frames stay in original order in the queue. Predicate builders: match_correlation_id(id) (naive scan of envelope JSON for '"correlation_id":"<id>"') and match_any. drain() returns everything buffered non-blocking. Destructor calls shutdown(SD_BOTH/SHUT_RDWR) to unblock recv() then joins reader. Uses SocketSubsystem so refcount plays nicely with any other net/ user in the same process. Threads::Threads linked PUBLIC from CMakeLists so downstream binaries get pthread automatically.
- Verified: cmake --build build --config Debug — compiles clean on MSVC /W4 /permissive-. Runtime exercised through ControlPlaneClient (A2) and app_chat (A3) which depend on it.
- Next: A2 — ControlPlaneClient: typed RPC wrapper with login/sync/send/read/edit/delete/contacts/presence/heartbeat + background push dispatcher.
- Covers: REQ-TCP-LINE-CLIENT, REQ-NET-ABSTRACTION

## ControlPlaneClient (A2) (gate: pass)

- Timestamp: 2026-04-20T14:17:06+00:00
- Delivered: client/src/transport/control_plane_client.h/.cpp: typed RPC wrapper over TcpLineClient. Each RPC gets a fresh correlation_id ('rpc_<n>') and blocks via tcp_.wait_for on that exact id. Supports login / conversation_sync / send_message / mark_read / edit_message / delete_message / list_contacts / add_contact / remove_contact / presence_query / heartbeat_ping. JSON composed by string concatenation with proper escaping (quote helper); responses parsed via existing transport::JsonParser + extract_string/bool/number helpers. Background dispatcher thread pulls frames whose correlation_id starts with 'push_' and invokes a single PushHandler callback (registered via set_push_handler). Optional start_heartbeat(interval_ms) spawns a heartbeat_ping thread. Typed result structs (LoginResult, MessageResult, SyncResult with SyncedConversation + SyncedMessage (incl edited/deleted/attachment_id), ContactListResult, PresenceResult, AckResult) always carry {ok, error_code, error_message} for consistent failure handling.
- Verified: cmake --build build --config Debug — compiles clean after fixing (a) atomic fetch_add needing non-const method and (b) dead parse call discarding [[nodiscard]] return. Runtime exercised by app_chat (A3) end-to-end.
- Next: A3 — app_chat interactive C++ binary with slash-command UX matching chat_cli.py; two instances exchange live messages.
- Covers: REQ-CPP-CONTROL-CLIENT, REQ-TYPED-PROTO, REQ-CHAT-FANOUT, REQ-PRESENCE-HEARTBEAT

## C++ interactive chat demo (A3) (gate: pass)

- Timestamp: 2026-04-20T14:22:03+00:00
- Delivered: client/src/app_chat/main.cpp: standalone executable that mirrors the Python chat_cli.py UX in native C++. Parses --user/--password/--device/--host/--port/--conversation/--heartbeat. On login, registers a PushHandler with ControlPlaneClient that prints MESSAGE_DELIVER / MESSAGE_EDITED / MESSAGE_DELETED / MESSAGE_READ_UPDATE / CONVERSATION_UPDATED in a readable format. Main loop reads stdin; slash commands: /sync /read /edit /del /contacts /add /presence /q. Non-slash lines are sent as messages. JSON field extraction in the push printer uses a whitespace-tolerant json_find_string (handles both Python's default ', ' + ': ' separators and compact). CMakeLists adds app_chat executable target. scripts/validate_cpp_chat_e2e.py drives the whole stack: free-port Python server + 2 real app_chat.exe subprocesses + stdin drivers + stdout assertions.
- Verified: validate_cpp_chat_e2e.py 3/3 — bob's push handler receives 'hello bob from C++ chat demo' sent by alice, both clients log in + show initial conv_alice_bob sync, /presence reports both users online. Full server-side regression 129/129 across 20 Python validators unchanged. cmake --build green.
- Next: Open space: a real 2nd platform (Qt/GTK/Android/iOS) to validate POSIX branch of net/; D9 media-plane AEAD still deferred; attachments/groups not yet surfaced in C++ client (Python chat_cli has them via /create; scope for future milestone).
- Covers: REQ-CPP-CHAT-DEMO, REQ-CPP-CONTROL-CLIENT, REQ-TCP-LINE-CLIENT, REQ-NET-ABSTRACTION, REQ-CHAT-FANOUT

## Qt desktop chat baseline (C1) (gate: pass)

- Timestamp: 2026-04-24T14:10:20+00:00
- Delivered: Added app_desktop Qt Widgets target with host/port/conversation controls, login form, transcript view, message composer, live push rendering, heartbeat startup, and a --smoke path that exercises connect/login/conversation_sync/message_send without manual UI. CMake now builds app_desktop when Qt6 Widgets is available; README/current-state/roadmap document the C1-C5 chat completion arc.
- Verified: Configured build-codex with Qt6 prefix, built all Debug targets, ran validate_desktop_smoke.py 1/1, validate_cpp_chat_e2e.py 3/3, validate_message_fanout.py 4/4, and validate_typed_errors.py 11/11.
- Next: C2 client state and local cache: introduce a GUI-facing conversation/message store, sync cursor, unread counts, and reconnect reconciliation.
- Covers: REQ-C1-DESKTOP-GUI, REQ-CPP-CONTROL-CLIENT, REQ-CHAT-FANOUT

## Desktop in-memory chat store (C2a) (gate: partial)

- Timestamp: 2026-04-24T14:19:16+00:00
- Delivered: Added DesktopChatStore as a GUI-facing in-memory conversation/message model. The store applies conversation_sync snapshots, local send responses, and push envelopes for message_deliver/message_edited/message_deleted; tracks selected conversation and unread counts for unselected conversations; renders transcript and conversation summary snapshots. app_desktop now renders from this store instead of appending raw sync/push text directly. Added app_desktop_store_test C++ test target.
- Verified: cmake --build build-codex --config Debug passed. app_desktop_store_test.exe passed 4/4. validate_desktop_smoke.py passed 1/1. validate_cpp_chat_e2e.py passed 3/3. validate_message_fanout.py passed 4/4.
- Next: Continue C2 with durable local cache and reconnect reconciliation: add sync cursor/last-seen message tracking, selected conversation state, and missed-message recovery after reconnect.
- Covers: REQ-C2A-INMEMORY-STORE, REQ-C2-CLIENT-CACHE, REQ-C1-DESKTOP-GUI

## Desktop persistent cache and reconnect reconciliation (C2b) (gate: partial)

- Timestamp: 2026-04-24T14:26:00+00:00
- Delivered: Extended DesktopChatStore with JSON save/load for current user, selected conversation, conversations, messages, edit/delete flags, attachment ids, participants and unread counts. app_desktop now accepts --cache-file, loads cached state before network sync, renders cached transcript immediately, and saves after sync/send/push. Reconnect reconciliation is implemented as cache-first display followed by full conversation_sync replacement from the server as source of truth.
- Verified: cmake --build build-codex --config Debug passed. app_desktop_store_test.exe passed 6/6 including cache round-trip and reconnect reconciliation. validate_desktop_smoke.py passed 1/1. validate_cpp_chat_e2e.py passed 3/3. validate_message_fanout.py passed 4/4.
- Next: Finish remaining C2 maturity with incremental update cursor/server update offsets and a real conversation list widget; then move to C3 production attachment path.
- Covers: REQ-C2B-PERSISTENT-CACHE, REQ-C2-CLIENT-CACHE, REQ-C2A-INMEMORY-STORE, REQ-C1-DESKTOP-GUI

## Desktop conversation list and local cursor (C2c) (gate: partial)

- Timestamp: 2026-04-24T14:29:36+00:00
- Delivered: Added a real Qt QListWidget conversation list to app_desktop. The list is rendered from DesktopChatStore, shows title/id/unread/last-message cursor, and selecting a row updates the selected conversation, composer target, transcript and cache. DesktopChatStore now maintains per-conversation last_message_id as a local sync cursor foundation, persists it in the JSON cache, restores it on load, and advances it on sync/send/push. Store test now covers cursor advance and persistence.
- Verified: cmake --build build-codex --config Debug passed. app_desktop_store_test.exe passed 7/7. validate_desktop_smoke.py passed 1/1. validate_cpp_chat_e2e.py passed 3/3. validate_message_fanout.py passed 4/4.
- Next: Move to C3 production attachment path unless we decide to add a server-side incremental sync API first. C2 client-side cache/list/cursor foundation is in place; true incremental sync still requires protocol/server work.
- Covers: REQ-C2C-CONVERSATION-LIST, REQ-C2-CLIENT-CACHE, REQ-C2B-PERSISTENT-CACHE, REQ-C2A-INMEMORY-STORE, REQ-C1-DESKTOP-GUI

## Production attachment path (C3) (gate: partial)

- Timestamp: 2026-04-24T14:39:32+00:00
- Delivered: Introduced AttachmentBlobStore as a filesystem-backed object-store-ready boundary. ChatService now validates base64/size as before, writes attachment bytes to the blob store when configured, persists metadata plus storage_key in runtime state, and fetches content from blob storage while preserving legacy inline content_b64 compatibility. server.main exposes --attachment-dir with default <state-file>.attachments. ControlPlaneClient now supports send_attachment and fetch_attachment. app_desktop has an Attach button and --smoke-attachment round-trip.
- Verified: cmake --build build-codex --config Debug passed. validate_attachments.py passed 11/11 including metadata-vs-blob separation, blob restart, and legacy inline migration. validate_desktop_smoke.py passed 1/1 with attachment send/fetch. validate_cpp_chat_e2e.py passed 3/3. validate_message_fanout.py passed 4/4. app_desktop_store_test.exe passed 7/7.
- Next: Move to C4 durable server persistence: replace JSON runtime state with a database-backed repository boundary, starting with SQLite/PostgreSQL-compatible schema and migration from current JSON state.
- Covers: REQ-C3A-BLOB-ATTACHMENTS, REQ-C3-ATTACHMENT-PATH, REQ-ATTACHMENTS, REQ-C1-DESKTOP-GUI

## SQLite durable persistence boundary (C4a) (gate: partial)

- Timestamp: 2026-04-24T14:44:29+00:00
- Delivered: Added SQLite --db-file persistence backend to InMemoryState while preserving JSON --state-file mode. The SQLite schema persists users, devices, sessions, conversations, remote_sessions, contacts and attachment metadata; state save/load now chooses SQLite when db_file is configured. ServerApplication, create_app, serve_tcp and server.main accept db_file/--db-file, with attachment-dir defaulting from the selected persistence anchor. Added validate_sqlite_persistence.py covering restart recovery for sessions, messages, contacts, remote sessions and attachments plus JSON regression.
- Verified: validate_sqlite_persistence.py passed 2/2. validate_session_persistence.py passed 5/5. validate_attachments.py passed 11/11. validate_registration.py passed 7/7. validate_desktop_smoke.py passed 1/1. validate_cpp_chat_e2e.py passed 3/3. validate_message_fanout.py passed 4/4. validate_typed_errors.py passed 11/11.
- Next: Move to C5 device management completeness: expose device list in the Qt desktop, then add session revoke/trusted-device state as protocol/server work.
- Covers: REQ-C4A-SQLITE-PERSISTENCE, REQ-C4-DURABLE-PERSISTENCE, REQ-PERSISTENCE, REQ-SESSION-PERSIST

## Desktop device management completeness (C5) (gate: pass)

- Timestamp: 2026-04-24T14:55:55+00:00
- Delivered: Added control-plane device revoke and trust update payloads, server dispatch and PresenceService mutations, C++ ControlPlaneClient device management RPCs, Qt desktop device panel actions, and a dedicated validator for trust/untrust, revoke denial and SQLite persistence.
- Verified: Built Debug with cmake --build build-codex --config Debug; ran app_desktop_store_test 7/7, validate_device_management 3/3, validate_desktop_smoke 1/1, validate_presence_heartbeat 6/6, validate_sqlite_persistence 2/2, validate_attachments 11/11, validate_cpp_chat_e2e 3/3, validate_message_fanout 4/4 and validate_typed_errors 11/11.
- Next: Acceptance sweep for the C1-C5 chat completion arc, then choose whether to close remaining partial gaps: server incremental sync API, attachment download/save UI, PostgreSQL/Redis productionization, or richer last-seen/audit policy.
- Covers: REQ-C5-DEVICE-MANAGEMENT, REQ-PRESENCE-HEARTBEAT, REQ-C4A-SQLITE-PERSISTENCE

## C1-C5 acceptance sweep (gate: pass)

- Timestamp: 2026-04-24T15:00:19+00:00
- Delivered: Ran the full validator suite after C5 and fixed a real TCP fanout login race by registering a session's push writer before emitting login_response. Updated current-state docs to reflect the C1-C5 acceptance status and validator counts.
- Verified: Full sweep passed: all scripts/validate_*.py validators green, 24 scripts / 141 scenarios. Targeted regressions also passed for validate_message_fanout 4/4, validate_cpp_chat_e2e 3/3, validate_desktop_smoke 1/1 and validate_device_management 3/3 after the race fix.
- Next: Choose the next production-hardening slice: server incremental sync API, attachment download/save UI, PostgreSQL/Redis productionization, or richer last-seen/audit/policy for device management.
- Covers: REQ-CHAT-FANOUT, REQ-C1-DESKTOP-GUI, REQ-C2-CLIENT-CACHE, REQ-C3-ATTACHMENT-PATH, REQ-C4-DURABLE-PERSISTENCE, REQ-C5-DEVICE-MANAGEMENT

## Incremental conversation sync (C6a) (gate: pass)

- Timestamp: 2026-04-25T09:07:47+00:00
- Delivered: Added ConversationSyncRequestPayload cursors, ChatService.sync_for_user_since, server dispatch for cursor-based conversation_sync, ControlPlaneClient.conversation_sync_since, desktop cache cursor export and incremental merge, smoke coverage for incremental sync, and a dedicated validate_incremental_sync.py validator.
- Verified: Built Debug with cmake --build build-codex --config Debug; ran validate_incremental_sync 4/4, app_desktop_store_test 8/8, validate_desktop_smoke 1/1, validate_cpp_chat_e2e 3/3, validate_message_fanout 4/4, validate_typed_errors 11/11, validate_sqlite_persistence 2/2, and a full scripts/validate_*.py sweep: 25 scripts / 145 scenarios all passed.
- Next: Continue C6 with durable edit/delete/read-marker delta logs and paging/windowing, or switch to C3 download/save UI if user-visible attachment completeness is preferred.
- Covers: REQ-C6A-INCREMENTAL-SYNC, REQ-C2-CLIENT-CACHE, REQ-C2B-PERSISTENT-CACHE, REQ-C2C-CONVERSATION-LIST, REQ-CHAT-CORE

## Durable conversation delta log (C6b) (gate: pass)

- Timestamp: 2026-04-25T09:17:54+00:00
- Delivered: Added per-conversation change_seq and durable changes to runtime state, JSON and SQLite persistence; extended conversation_sync with versions and ConversationChangeDescriptor deltas; recorded edit/delete/read-marker changes in ChatService; parsed sync changes in ControlPlaneClient; persisted desktop sync_version and applied edit/delete deltas on incremental sync; expanded validate_incremental_sync coverage.
- Verified: Built Debug with cmake --build build-codex --config Debug; ran validate_incremental_sync 6/6, app_desktop_store_test 9/9, validate_desktop_smoke 1/1, validate_message_edit_delete 8/8, validate_read_receipts 6/6, validate_sqlite_persistence 2/2, validate_session_persistence 5/5, and a full scripts/validate_*.py sweep: 25 scripts / 147 scenarios all passed.
- Next: Continue C6 with membership/title delta application plus paging/windowing and delta compaction, or switch to user-visible C3 attachment download/save UI.
- Covers: REQ-C6B-DURABLE-DELTA-LOG, REQ-C6A-INCREMENTAL-SYNC, REQ-READ-RECEIPTS, REQ-MESSAGE-EDIT-DELETE, REQ-C2-CLIENT-CACHE

## Conversation metadata delta and compaction (C6c) (gate: pass)

- Timestamp: 2026-04-25T09:32:20+00:00
- Delivered: Recorded conversation_updated deltas for participant add/remove, added compacted change-log fallback to full conversation sync for stale versions, expanded incremental sync validation for membership metadata and compaction, and taught the desktop store test to verify metadata delta application.
- Verified: Built Debug with cmake --build build-codex --config Debug; ran validate_incremental_sync 8/8, app_desktop_store_test 10/10, validate_group_conversations 6/6, validate_desktop_smoke 1/1, validate_message_edit_delete 8/8, validate_read_receipts 6/6, validate_sqlite_persistence 2/2, and a full scripts/validate_*.py sweep: 25 scripts / 149 scenarios all passed.
- Next: Either continue C6 with production paging/windowing and explicit conflict metadata, or switch to C3 attachment download/save UI for more user-visible completeness.
- Covers: REQ-C6C-METADATA-DELTA-COMPACTION, REQ-C6B-DURABLE-DELTA-LOG, REQ-GROUP-CONVERSATIONS, REQ-C2-CLIENT-CACHE

## Desktop attachment save UI (C3b) (gate: pass)

- Timestamp: 2026-04-25T09:40:06+00:00
- Delivered: Added Qt desktop Attachment ID + Save Attachment control, implemented fetch_attachment-to-file save flow, preserved attachment_id for locally sent attachment messages and cache reloads, and extended desktop smoke validation with --smoke-save-dir content verification.
- Verified: Built Debug with cmake --build build-codex --config Debug; ran app_desktop_store_test 11/11, validate_desktop_smoke 1/1 including attachment save marker and saved file byte check, validate_attachments 11/11, validate_cpp_chat_e2e 3/3, validate_incremental_sync 8/8, validate_sqlite_persistence 2/2, and a full scripts/validate_*.py sweep: 25 scripts / 149 scenarios all passed.
- Next: Continue C3 with attachment previews/thumbnails and upload/download progress, or switch to registration UI for another visible Telegram-like gap.
- Covers: REQ-C3B-ATTACHMENT-SAVE-UI, REQ-C3-ATTACHMENT-PATH, REQ-C3A-BLOB-ATTACHMENTS, REQ-ATTACHMENTS

## Desktop attachment metadata preview (C3c) (gate: pass)

- Timestamp: 2026-04-25T09:48:21+00:00
- Delivered: Extended attachment message descriptors and C++ sync parsing with filename/mime/size metadata, preserved metadata in DesktopChatStore cache/local send paths, rendered filename/size in the desktop transcript, defaulted save dialogs to known filenames, and expanded attachment/store validation coverage.
- Verified: Built Debug with cmake --build build-codex --config Debug; ran app_desktop_store_test 11/11, validate_attachments 11/11, validate_desktop_smoke 1/1, and a full scripts/validate_*.py sweep: 25 scripts / 149 scenarios all passed.
- Next: Continue C3 with real thumbnails/previews and upload/download progress, or switch to registration UI for another visible Telegram-like gap.
- Covers: REQ-C3C-ATTACHMENT-METADATA-PREVIEW, REQ-C3B-ATTACHMENT-SAVE-UI, REQ-C3-ATTACHMENT-PATH, REQ-C3A-BLOB-ATTACHMENTS, REQ-ATTACHMENTS

## Desktop attachment transfer status (C3d) (gate: pass)

- Timestamp: 2026-04-25T09:54:44+00:00
- Delivered: Added a desktop transfer status row with progress bar for attachment read/upload/download/save stages, emitted verifiable upload/download/save stage markers from app_desktop --smoke, and extended validate_desktop_smoke.py to guard those markers.
- Verified: Built Debug with cmake --build build-codex --config Debug; ran validate_desktop_smoke 1/1 with transfer-status markers, app_desktop_store_test 11/11, validate_attachments 11/11 and validate_incremental_sync 8/8.
- Next: Continue C3 with thumbnail/preview rendering, or switch to registration UI for another visible Telegram-like gap.
- Covers: REQ-C3D-ATTACHMENT-TRANSFER-STATUS, REQ-C3C-ATTACHMENT-METADATA-PREVIEW, REQ-C3B-ATTACHMENT-SAVE-UI, REQ-C3-ATTACHMENT-PATH, REQ-C3A-BLOB-ATTACHMENTS, REQ-ATTACHMENTS

## Desktop attachment type previews (C3e) (gate: pass)

- Timestamp: 2026-04-25T10:02:29+00:00
- Delivered: Added preview_text to attachment message results and desktop cache records, generated short local text previews for text/* uploads, rendered text/image preview affordances in the desktop transcript, inferred basic MIME types from selected filenames, and expanded app_desktop_store_test coverage for preview rendering and cache round-trip.
- Verified: Built Debug with cmake --build build-codex --config Debug; ran app_desktop_store_test 11/11 with preview assertions, validate_desktop_smoke 1/1, validate_attachments 11/11 and validate_incremental_sync 8/8.
- Next: Continue with registration UI or real decoded image thumbnails; avoid byte-level attachment progress until chunked upload/download exists.
- Covers: REQ-C3E-ATTACHMENT-TYPE-PREVIEWS, REQ-C3D-ATTACHMENT-TRANSFER-STATUS, REQ-C3C-ATTACHMENT-METADATA-PREVIEW, REQ-C3B-ATTACHMENT-SAVE-UI, REQ-C3-ATTACHMENT-PATH, REQ-C3A-BLOB-ATTACHMENTS, REQ-ATTACHMENTS

## Desktop registration UI (gate: pass)

- Timestamp: 2026-04-25T10:35:35+00:00
- Delivered: Added ControlPlaneClient::register_user for register_request/register_response, added Display Name plus Register controls to the Qt desktop login row, reused the connect/sync path after registration, added --smoke-register to app_desktop, and extended validate_desktop_smoke.py to verify native desktop registration.
- Verified: Built Debug with cmake --build build-codex --config Debug; ran validate_desktop_smoke 1/1 with desktop register smoke marker, validate_registration 7/7 and app_desktop_store_test 11/11.
- Next: Continue visible Telegram-like completion with basic profile/account surface or contact/group creation in the desktop UI.
- Covers: REQ-DESKTOP-REGISTRATION-UI, REQ-USER-REGISTRATION, REQ-PASSWORD-HASH, REQ-C1-DESKTOP-GUI, REQ-CPP-CONTROL-CLIENT

## Desktop contacts and groups UI (gate: pass)

- Timestamp: 2026-04-26T04:50:59+00:00
- Delivered: Added ControlPlaneClient group conversation RPCs, Qt desktop contacts list/add/remove controls, group creation controls, selected-conversation member add/remove controls, desktop smoke coverage for contacts and group creation, and a human-readable execution log for the phase.
- Verified: Built Debug with cmake --build build-codex --config Debug; ran validate_contacts 8/8, validate_group_conversations 6/6, validate_desktop_smoke 1/1 with contacts/groups markers, app_desktop_store_test 11/11, and a full scripts/validate_*.py sweep: 25 scripts / 149 scenarios all passed.
- Next: Continue Telegram-like desktop polish with message timeline status/timestamps/bubble-like rendering, or add profile/account surface.
- Covers: REQ-DESKTOP-CONTACTS-GROUPS-UI, REQ-CONTACTS, REQ-GROUP-CONVERSATIONS, REQ-CPP-CONTROL-CLIENT, REQ-C1-DESKTOP-GUI

## Desktop message timeline polish (gate: pass)

- Timestamp: 2026-04-26T05:00:37+00:00
- Delivered: Added server created_at_ms propagation, C++ timestamp/read-marker parsing, desktop cache read-marker persistence, message_read_update handling and bubble-style timestamp/status transcript rendering.
- Verified: Built Debug; ran app_desktop_store_test 12/12, validate_desktop_smoke 1/1, validate_read_receipts 6/6, validate_incremental_sync 8/8, validate_message_fanout 4/4, validate_attachments 11/11 and validate_message_edit_delete 8/8.
- Next: Continue profile/account polish or richer desktop navigation; timeline-specific follow-up is pending/failed send states and a custom rich message list widget.
- Covers: REQ-DESKTOP-MESSAGE-TIMELINE-POLISH, REQ-READ-RECEIPTS, REQ-C2-CLIENT-CACHE, REQ-C2A-INMEMORY-STORE, REQ-C2B-PERSISTENT-CACHE, REQ-C1-DESKTOP-GUI

## Desktop timeline completion gaps (gate: pass)

- Timestamp: 2026-04-26T05:09:47+00:00
- Delivered: Closed timeline leftovers with local pending/failed text and attachment send lifecycle, group per-member read details, QTextBrowser rich HTML bubble rendering and explicit legacy timestamp fallback.
- Verified: Built Debug; ran app_desktop_store_test 16/16, validate_desktop_smoke 1/1, validate_read_receipts 6/6, validate_incremental_sync 8/8, validate_message_fanout 4/4 and validate_attachments 11/11.
- Next: Run full validator sweep and then move to profile/account polish or richer desktop navigation/search.
- Covers: REQ-DESKTOP-TIMELINE-COMPLETION, REQ-DESKTOP-MESSAGE-TIMELINE-POLISH, REQ-READ-RECEIPTS, REQ-C2-CLIENT-CACHE, REQ-C2A-INMEMORY-STORE, REQ-C2B-PERSISTENT-CACHE, REQ-C1-DESKTOP-GUI

## Profile/account and user discovery (gate: pass)

- Timestamp: 2026-04-26T06:00:00+00:00
- Delivered: Added authenticated profile_get_request/profile_update_request and user_search_request/user_search_response protocol flows, display-name validation/persistence, online/contact flags for search results, C++ ControlPlaneClient profile/search RPCs, Qt desktop profile refresh/save controls, Qt desktop user search panel, desktop smoke markers and a dedicated validate_profile_search.py validator.
- Verified: Built Debug with cmake --build build-codex --config Debug; ran validate_profile_search 5/5, validate_desktop_smoke 1/1 with profile/search markers, validate_contacts 8/8, validate_registration 7/7, app_desktop_store_test 16/16, and a full scripts/validate_*.py sweep: 26 scripts / 154 scenarios all passed.
- Next: Desktop navigation/search: chat list filtering, selected-conversation message search and keyboard-friendly navigation.
- Covers: REQ-DESKTOP-PROFILE-SEARCH, REQ-DESKTOP-REGISTRATION-UI, REQ-CONTACTS, REQ-PRESENCE-HEARTBEAT, REQ-CPP-CONTROL-CLIENT, REQ-C1-DESKTOP-GUI

## Desktop navigation/search (gate: pass)

- Timestamp: 2026-04-26T06:20:00+00:00
- Delivered: Added local chat-list filtering, selected-conversation message search result records, rich timeline search match/focused highlighting, Qt search controls with previous/next navigation and match-count status, plus smoke/store coverage for navigation search.
- Verified: Built Debug with cmake --build build-codex --config Debug; ran app_desktop_store_test 17/17 and validate_desktop_smoke 1/1 with navigation/search marker.
- Next: Message actions: replies, forwards, reactions and pinned messages.
- Covers: REQ-DESKTOP-NAVIGATION-SEARCH, REQ-DESKTOP-TIMELINE-COMPLETION, REQ-C2-CLIENT-CACHE, REQ-C1-DESKTOP-GUI
## Message actions (gate: pass)

- Timestamp: 2026-04-26T15:11:43+00:00
- Delivered: Added replies, forwards, reaction toggles and pin/unpin state across protocol payloads, server message records, fan-out pushes, incremental sync deltas, C++ ControlPlaneClient APIs, DesktopChatStore cache/rendering and Qt desktop controls.
- Verified: Built Debug with cmake --build build-codex --config Debug; ran validate_message_actions 3/3, app_desktop_store_test 18/18, validate_desktop_smoke 1/1, targeted regressions and a full scripts/validate_*.py sweep: 27 scripts / 157 scenarios passed.
- Next: Polish message-action UX with selectable message rows, reply/forward preview cards, pinned banner/list and reaction picker, or move to production paging/global search.
- Covers: REQ-DESKTOP-MESSAGE-ACTIONS, REQ-C1-DESKTOP-GUI, REQ-C2-CLIENT-CACHE, REQ-C6B-DURABLE-DELTA-LOG, REQ-CHAT-FANOUT, REQ-TYPED-PROTO

## Backlog tasks 1-5 verified slices (gate: pass)

- Timestamp: 2026-04-26T15:34:30+00:00
- Delivered: Advanced the remaining task list with five verified slices: clickable message ids and Use Match/Use Latest targeting for message actions; server-side message_search_request/message_search_response with optional conversation scope; C++ ControlPlaneClient search_messages and desktop smoke coverage; attachment filename search validation plus SQLite persistence coverage for action metadata; and a Qt revoke-device confirmation dialog.
- Verified: Built Debug with cmake --build build-codex --config Debug; ran validate_message_search 5/5, validate_message_actions 4/4, validate_desktop_smoke 1/1, app_desktop_store_test 19/19, validate_incremental_sync 8/8 and validate_typed_errors 11/11.
- Next: Continue production search/history with paging windows and richer result cards, then move into attachment thumbnails/streaming progress and broader backend repository hardening.
- Covers: REQ-DESKTOP-MESSAGE-ACTION-UX, REQ-SERVER-MESSAGE-SEARCH, REQ-DESKTOP-MESSAGE-ACTIONS, REQ-DESKTOP-NAVIGATION-SEARCH, REQ-C3C-ATTACHMENT-METADATA-PREVIEW, REQ-C4A-SQLITE-PERSISTENCE, REQ-DESKTOP-DEVICE-POLISH, REQ-C5-DEVICE-MANAGEMENT, REQ-CPP-CONTROL-CLIENT

## Production history paging and Linux Docker boundary (gate: partial)

- Timestamp: 2026-04-27T01:47:06+00:00
- Delivered: Added bounded conversation history paging to conversation_sync, offset paging to server-side message search, C++ ControlPlaneClient history-page/search paging parsing, desktop smoke coverage for history pages, TELEGRAM_* server environment configuration and deploy/docker Linux server compose files with persistent /data plus an optional PostgreSQL profile.
- Verified: Built Debug with cmake; ran validate_history_paging 2/2, validate_desktop_smoke 1/1 with history-page marker, validate_message_search 5/5, validate_incremental_sync 8/8, app_desktop_store_test 19/19, validate_typed_errors 11/11 and validate_message_actions 4/4. WSL Docker Compose config passed for default and postgres profile; image build was blocked by Docker Hub timeout resolving python:3.12-slim.
- Next: Wire the desktop UI to load older history pages and richer search result cards, then start the PostgreSQL repository boundary once the Docker registry/base image is available.
- Covers: REQ-PRODUCTION-HISTORY-PAGING, REQ-SERVER-MESSAGE-SEARCH, REQ-CPP-CONTROL-CLIENT, REQ-LINUX-DOCKER-DEPLOYMENT, REQ-C4A-SQLITE-PERSISTENCE

## WSL Docker deployment smoke (gate: pass)

- Timestamp: 2026-04-27T02:29:19+00:00
- Delivered: Configured WSL Docker daemon proxy for the current 10.20.11.30:10809 proxy, forwarded proxy variables through compose build/runtime environment, added scripts/deploy_wsl_docker.ps1 as a one-command deployment entry, kept SQLite as the default /data/runtime.sqlite local-test backend, verified optional PostgreSQL profile startup, and added validate_docker_deploy.py for a real TCP login smoke against the container.
- Verified: Docker Hub pulls now succeed through the daemon proxy; docker compose build telegram-server passed; docker compose up -d telegram-server produced a healthy container; validate_docker_deploy.py passed; deploy_wsl_docker.ps1 -NoBuild passed; deploy_wsl_docker.ps1 -Mode postgres -NoBuild -NoSmoke passed with postgres and telegram-server running.
- Next: Start the PostgreSQL repository boundary while keeping SQLite as the local/default test backend, or wire desktop UI to load older history pages first.
- Covers: REQ-LINUX-DOCKER-DEPLOYMENT, REQ-C4A-SQLITE-PERSISTENCE

## PostgreSQL repository boundary first slice (gate: pass)

- Timestamp: 2026-04-27T02:44:48+00:00
- Delivered: Added PostgresStateRepository, normalized users/devices/sessions into PostgreSQL tables, retained remaining runtime domains in a JSONB compatibility snapshot, wired InMemoryState/ServerApplication/server CLI to --pg-dsn and TELEGRAM_PG_DSN, added a PostgreSQL-backed Docker server on port 8788 while preserving SQLite on 8787, installed psycopg in the Docker image, fixed login new-device persistence ordering, and added validate_postgres_repository.py.
- Verified: Built and started telegram-server-postgres with Docker Compose; ran container validate_postgres_repository.py 1/1; ran docker deploy smoke against port 8788 and SQLite port 8787; built Debug with CMake; ran validate_desktop_smoke 1/1, validate_registration 7/7, validate_device_management 3/3, validate_sqlite_persistence 2/2 and validate_typed_errors 11/11.
- Next: Migrate conversations/messages/change logs to dedicated PostgreSQL tables with transactional message write boundaries, while keeping SQLite as the local/default test backend.
- Covers: REQ-POSTGRES-REPOSITORY-BOUNDARY, REQ-LINUX-DOCKER-DEPLOYMENT, REQ-C4A-SQLITE-PERSISTENCE, REQ-SESSION-PERSIST, REQ-PERSISTENCE

## PostgreSQL conversation repository and desktop paging/search polish (gate: pass)

- Timestamp: 2026-04-27T03:15:52+00:00
- Delivered: Migrated PostgreSQL persistence for conversations, messages and conversation change logs into dedicated tables with single-transaction repository saves; preserved SQLite/default behavior; added desktop Load Older history paging and server message-search result cards backed by DesktopChatStore history-page merging.
- Verified: Built Debug with CMake; ran history paging 2/2, message search 5/5, desktop store 20/20, desktop smoke 1/1, incremental sync 8/8, SQLite persistence 2/2, typed errors 11/11, message actions 4/4, Docker PG deploy smoke on 8788 and container validate_postgres_repository 2/2.
- Next: Migrate contacts, attachments and remote sessions to dedicated PostgreSQL tables, add migrations, then continue richer message-action cards and conflict recovery metadata.
- Covers: REQ-POSTGRES-REPOSITORY-BOUNDARY, REQ-PRODUCTION-HISTORY-PAGING, REQ-SERVER-MESSAGE-SEARCH, REQ-C2-CLIENT-CACHE, REQ-C4A-SQLITE-PERSISTENCE

## PostgreSQL remaining domain repository migration (gate: pass)

- Timestamp: 2026-04-27T09:36:56+00:00
- Delivered: Migrated contacts, attachment metadata and remote sessions from the PostgreSQL compatibility snapshot into dedicated PostgreSQL tables while preserving the single-transaction repository save and snapshot fallback for older databases.
- Verified: Ran py_compile for repository and PG validator; ran validate_sqlite_persistence 2/2, validate_contacts 8/8, validate_attachments 11/11, validate_rendezvous 6/6, rebuilt/restarted Docker telegram-server-postgres and ran validate_postgres_repository 3/3, plus Docker PG deploy smoke on 8788, desktop smoke 1/1, incremental sync 8/8, typed errors 11/11 and session persistence 5/5.
- Next: Add PostgreSQL schema migrations/versioning, backup/restore checks, then move into TLS/session hardening and installation packaging.
- Covers: REQ-POSTGRES-REPOSITORY-BOUNDARY, REQ-C4-DURABLE-PERSISTENCE, REQ-C4A-SQLITE-PERSISTENCE, REQ-CONTACTS, REQ-ATTACHMENTS, REQ-REMOTE-LIFECYCLE

## PostgreSQL schema/versioning, backup/restore, session TTL and package staging (gate: pass)

- Timestamp: 2026-04-27T10:10:52+00:00
- Delivered: Added PostgreSQL schema_migrations version marker and schema_version check, backup/restore repository validator, configurable login-session TTL with heartbeat refresh, and Windows desktop package staging script.
- Verified: py_compile passed; Docker PostgreSQL repository validator 3/3; Docker PostgreSQL backup/restore validator 1/1; session hardening 3/3; session persistence 5/5; typed errors 11/11; package staging smoke created a Windows desktop artifact directory.
- Next: Implement TLS termination/native TLS configuration and move package staging toward signed/checksummed installer delivery.
- Covers: REQ-POSTGRES-REPOSITORY-BOUNDARY, REQ-C4-DURABLE-PERSISTENCE, REQ-POSTGRES-SCHEMA-BACKUP, REQ-PRODUCTION-SESSION-TTL, REQ-SESSION-PERSIST, REQ-WINDOWS-PACKAGE-STAGING, REQ-VALIDATION

## Native TLS control-plane configuration (gate: pass)

- Timestamp: 2026-04-27T10:14:34+00:00
- Delivered: Added optional native TLS wrapping for the Python TCP control plane, CLI/env certificate and key configuration, and TLS config guard validation.
- Verified: py_compile passed; validate_tls_config.py passed 3/3; validate_session_hardening.py passed 3/3.
- Next: Add C++ TLS client support or an external TLS termination recipe, then move package staging toward signed/checksummed installer output.
- Covers: REQ-TLS-CONTROL-PLANE, REQ-VALIDATION

## Checksummed Windows package output and TLS delivery notes (gate: pass)

- Timestamp: 2026-04-27T10:21:45+00:00
- Delivered: Enhanced Windows desktop package staging with SHA256SUMS.txt, zip checksum output, package-shape validation, and TLS deployment notes that document native server TLS plus the remaining C++ TLS client gap.
- Verified: validate_windows_package.ps1 passed and produced package directory, zip and .sha256; validate_tls_config.py passed 3/3; validate_session_hardening.py passed 3/3; py_compile passed for Python validators.
- Next: Add C++ TLS client transport behind the existing control-plane boundary or add a concrete reverse-proxy TLS termination compose profile.
- Covers: REQ-WINDOWS-PACKAGE-STAGING, REQ-WINDOWS-PACKAGE-CHECKSUMS, REQ-TLS-CONTROL-PLANE, REQ-VALIDATION

## TLS handshake smoke and Docker TLS termination profile (gate: pass)

- Timestamp: 2026-04-27T10:32:56+00:00
- Delivered: Added a real TLS login smoke validator, Docker nginx TLS termination profile on 8443, static deployment config validation, and TLS deployment documentation.
- Verified: py_compile passed; validate_tls_handshake.py passed 1/1; validate_tls_deployment_config.py passed 2/2; validate_tls_config.py passed 3/3.
- Next: Implement C++ TLS client transport parity or add automated cert generation/dev-run script for Docker TLS profile.
- Covers: REQ-TLS-CONTROL-PLANE, REQ-TLS-HANDSHAKE-SMOKE, REQ-TLS-TERMINATION-PROFILE, REQ-VALIDATION

## Dev cert generation and live TLS proxy smoke (gate: pass)

- Timestamp: 2026-04-27T11:03:05+00:00
- Delivered: Added local dev TLS cert generation, ignored cert material path, TLS dev cert validator, TLS proxy smoke validator, and corrected nginx to stream TLS termination for the raw JSON-over-TCP protocol.
- Verified: py_compile passed; validate_tls_dev_cert.py 2/2; validate_tls_handshake.py 1/1; validate_tls_deployment_config.py 2/2; docker compose --profile tls config passed; docker compose --profile tls up for telegram-server and telegram-tls-proxy passed; validate_tls_proxy_smoke.py passed; validate_docker_deploy.py passed on 8787.
- Next: Implement C++ TLS client transport parity or add TLS proxy coverage for PostgreSQL-backed server profile.
- Covers: REQ-TLS-CONTROL-PLANE, REQ-TLS-TERMINATION-PROFILE, REQ-TLS-DEV-CERT, REQ-TLS-PROXY-SMOKE, REQ-VALIDATION

## PostgreSQL TLS proxy coverage (M66) (gate: pass)

- Timestamp: 2026-04-28T02:35:00+00:00
- Delivered: Established the Atlas task library and delivery plan, added a PostgreSQL-backed nginx stream TLS proxy profile on host port 8444, documented the run/smoke commands, and extended the TLS deployment validator to cover both SQLite and PostgreSQL proxy wiring. Live Docker actions were recorded as pending actions instead of executed.
- Verified: python -m py_compile scripts\\validate_tls_deployment_config.py scripts\\validate_tls_proxy_smoke.py passed; python scripts\\validate_tls_deployment_config.py passed 4/4 scenarios.
- Next: Implement C++ direct TLS client transport parity, or execute the pending PostgreSQL TLS proxy live smoke after user confirmation.
- Covers: REQ-ATLAS-TASK-LIBRARY, REQ-TLS-PG-PROXY, REQ-TLS-TERMINATION-PROFILE, REQ-VALIDATION

## C++ direct TLS client transport parity (M67) (gate: partial)

- Timestamp: 2026-04-28T02:53:23+00:00
- Delivered: Added Windows Schannel-backed TcpLineClient::connect_tls, ControlPlaneClient::connect_tls, CLI flags for app_chat, desktop TLS controls, and a validate_cpp_tls_client.py runtime validator. Updated docs and Atlas task status to show the runtime blocker.
- Verified: python -m py_compile scripts\\validate_cpp_tls_client.py passed; cmake configure/build in build-verify passed; validate_cpp_chat_e2e.py passed 3/3; app_desktop_store_test.exe passed 20/20; validate_cpp_tls_client.py reached Schannel but failed with SEC_E_NO_CREDENTIALS before TLS login.
- Next: Resolve Schannel credential acquisition or switch to a different local TLS backend, then rerun validate_cpp_tls_client.py.
- Covers: REQ-TLS-CPP-CLIENT, REQ-CPP-CONTROL-CLIENT, REQ-TCP-LINE-CLIENT, REQ-TLS-CONTROL-PLANE, REQ-VALIDATION

## C++ direct TLS Schannel credential fix (M68) (gate: pass)

- Timestamp: 2026-04-28T04:51:18+00:00
- Delivered: tcp_line_client.cpp tls_handshake now passes an explicit SCHANNEL_CRED (SCH_CRED_NO_DEFAULT_CREDS|SCH_USE_STRONG_CRYPTO + SCH_CRED_MANUAL_CRED_VALIDATION when insecure) so AcquireCredentialsHandleW no longer returns SEC_E_NO_CREDENTIALS on hosts without default outbound creds
- Verified: validate_cpp_tls_client.py 2/2; validate_cpp_chat_e2e.py 3/3; app_desktop_store_test.exe 20/20; validate_tls_deployment_config.py 4/4; bundle verify ok 72 reqs
- Next: Run deployment hardening acceptance sweep across remaining validators (TLS proxy live smoke pending PA-001/PA-002 confirmation), then resume M70 remote-control runtime
- Covers: REQ-TLS-CPP-CLIENT, REQ-TLS-CONTROL-PLANE, REQ-VALIDATION

## JSON Unicode + non-ASCII frame fix (M72) (gate: pass)

- Timestamp: 2026-04-28T05:15:49+00:00
- Delivered: json_value.cpp parse_string now handles \uXXXX (incl. surrogate pairs) plus \b/\f via a new parse_hex4+append_utf8 pair; control_plane.py emits json.dumps(..., ensure_ascii=False) so non-ASCII goes out as UTF-8; new json_parser_test.exe covers ascii/CJK/BMP-escape/mixed/ASCII-range/emoji-surrogate/\b\f and rejects unpaired surrogates
- Verified: json_parser_test 9/9; validate_cpp_chat_e2e.py 3/3; app_desktop_store_test.exe 20/20; validate_cpp_tls_client.py 2/2
- Next: M73 Telegram-style desktop UI redesign
- Covers: REQ-CHAT-CORE, REQ-TYPED-PROTO, REQ-VALIDATION

## Telegram-style desktop UI redesign (M73) (gate: pass)

- Timestamp: 2026-04-28T05:24:28+00:00
- Delivered: app_desktop main.cpp restructured into a 3-pane QSplitter shell (sidebar with chat search + chat list + Settings toggle, center chat pane with chat header / in-chat search / timeline / composer / message-action row, collapsible right details panel grouping all admin controls into QGroupBox sections); Telegram-like Qt stylesheet covers chat list rows, header, composer, primary blue buttons, ghost links, status bar, group boxes; desktop_chat_store timeline palette swapped to Telegram light theme (#e6ebee app bg, #eeffde outgoing mint, white incoming, #3390ec accent); store_test assertion updated to match the new outgoing color
- Verified: build clean; app_desktop_store_test 20/20; validate_desktop_smoke 1/1 with all 16 smoke sub-stages green; live GUI launch survives >2s; cpp_chat_e2e 3/3; cpp_tls_client 2/2; tls_deployment_config 4/4; bundle verify ok 72 reqs
- Next: M69 deployment hardening acceptance sweep, OR M70 Windows installer/signing, OR pivot to mobile/i18n/account-recovery per release-readiness gap report
- Covers: REQ-CHAT-CORE, REQ-VALIDATION

## Auto-deploy Qt runtime so app_desktop.exe double-click works (M73a) (gate: pass)

- Timestamp: 2026-04-28T05:32:15+00:00
- Delivered: client/src/CMakeLists.txt: post-build add_custom_command on app_desktop runs windeployqt (auto-detects debug/release from binary, --no-translations --no-system-d3d-compiler --no-opengl-sw); skippable via -DTELEGRAM_LIKE_SKIP_WINDEPLOYQT=ON for installer pipelines that prefer scripts/package_windows_desktop.ps1. Also updated scripts/validate_desktop_smoke.py to look in build-verify before build-codex/build so the canonical dev build dir is exercised.
- Verified: windeployqt deployed Qt6Cored/Guid/Networkd/Svgd/Widgetsd + platforms/qwindowsd.dll + tls/qschannelbackendd next to app_desktop.exe; clean-PATH probe (only System32/Windows on PATH) launches app_desktop.exe successfully; validate_desktop_smoke.py passes 1/1 with clean PATH (no Qt bin)
- Next: M69 deployment hardening acceptance sweep / M70 Windows installer signing / mobile arc per release-readiness gap report
- Covers: REQ-VALIDATION, REQ-WINDOWS-PACKAGE-STAGING

## Settings panel redesign + functional audit (M74) (gate: pass)

- Timestamp: 2026-04-28T05:45:15+00:00
- Delivered: Replaced flat scrollable groupbox stack with Settings header bar (title + close) + QListWidget category nav (Profile/Account/Connection/Devices/Contacts/Find Users/Groups/Attachments) + QStackedWidget per-page views; each page now has a clear heading, subtitle, and per-field uppercase labels; Profile page shows a 96px QPainter-rendered avatar disc with deterministic Telegram-style palette + initial(s) plus a 2-line identity label refreshed on every profile_get; render_profile feeds both helpers; Qt stylesheet extended with settingsHeader/settingsNav/pageHeading/fieldLabel/profileIdentity styles. Audited all 8 settings handlers (connect/register/refresh-save profile/refresh-manage devices/refresh-manage contacts/search users/create-manage group/save attachment) — every handler follows the same correct detach->API->QMetaObject::invokeMethod pattern with shutting_down_ guard; no bugs found.
- Verified: build clean; validate_desktop_smoke 1/1 (16 sub-stages); GUI launches with clean PATH and stays up; bundle verify ok 72 reqs
- Next: M69 deployment hardening sweep / M70 Windows installer / mobile arc per release-readiness gap report
- Covers: REQ-CHAT-CORE, REQ-VALIDATION

## Parity gap A: conversation_updated push + Edit/Delete UI (M75) (gate: pass)

- Timestamp: 2026-04-28T05:59:55+00:00
- Delivered: DesktopChatStore::apply_push gained conversation_updated branch (parses payload via JsonParser, refreshes title + participant_user_ids on the local conversation). Promoted apply_message_edited / apply_message_deleted to public so the actor's UI can apply locally on RPC success. app_desktop main.cpp adds Edit + Delete buttons to the message-action row (inline with Reply/Forward/React/Pin/Unpin), wired to ControlPlaneClient::edit_message / delete_message; Edit pops a QInputDialog for the new text, Delete pops a QMessageBox confirmation; both gated by set_message_action_enabled.
- Verified: build clean; validate_desktop_smoke 1/1 (16 sub-stages); app_desktop_store_test 20/20
- Next: B remote-control RPCs on ControlPlaneClient
- Covers: REQ-CHAT-CORE, REQ-MESSAGE-EDIT-DELETE, REQ-GROUP-CONVERSATIONS, REQ-VALIDATION

## Parity gap B: remote-control RPCs on ControlPlaneClient (M76) (gate: pass)

- Timestamp: 2026-04-28T06:07:51+00:00
- Delivered: Added 5 new result structs (RemoteSessionStateResult / RemoteRelayAssignmentResult / RemoteSessionTerminatedResult / RemoteRendezvousResult + RemoteRendezvousCandidate / RemoteInputAckResult) and 8 RPC methods (remote_invite / remote_approve / remote_reject / remote_cancel / remote_terminate / remote_disconnect / remote_rendezvous_request / remote_input_event) to client/src/transport/control_plane_client.{h,cpp}; new test exe remote_session_smoke + CMake target + scripts/validate_cpp_remote_session.py wrapper that pre-registers alice/dev_remote_smoke and drives 8 negative-path round-trips to verify request envelope serialization and typed-error parsers. legacy session_gateway_client.cpp is left untouched (still drives app_shell scripted demo).
- Verified: build clean for all targets; new validate_cpp_remote_session.py PASS 8/8 (each new RPC returns typed error code through the new parser); validate_rendezvous 6/6, validate_terminate_disconnect 8/8, validate_input_injection 9/9 still green on server; validate_cpp_chat_e2e 3/3, validate_desktop_smoke 1/1 still green on existing client paths
- Next: C drop dead enums + empty controllers
- Covers: REQ-REMOTE-LIFECYCLE, REQ-TYPED-PROTO, REQ-VALIDATION

## Parity gap C: drop dead enums + empty controllers (M77) (gate: pass)

- Timestamp: 2026-04-28T06:12:35+00:00
- Delivered: Removed two dead MessageType enum values (SESSION_REFRESH and MESSAGE_ACK — neither dispatched, emitted, nor sent by any client). PRESENCE_UPDATE retained for D. Deleted four empty C++ controller folders (client/src/{auth,chat,contacts,devices}) along with their CMakeLists entries; trimmed the matching describe() noise out of app_shell.cpp. Updated validate_typed_errors.py UNSUPPORTED_MESSAGE_TYPE probe to use MessageType.HEARTBEAT_ACK (a valid response-direction enum that has no inbound dispatch) since SESSION_REFRESH no longer exists.
- Verified: validate_typed_errors 11/11; validate_cpp_chat_e2e 3/3; validate_cpp_remote_session 8/8; validate_desktop_smoke 1/1; validate_rendezvous 6/6; validate_terminate_disconnect 8/8; build clean across chat_client_core / app_chat / app_desktop / telegram_like_client / app_desktop_store_test / json_parser_test / remote_session_smoke
- Next: D real PRESENCE_UPDATE push fan-out
- Covers: REQ-TYPED-PROTO, REQ-VALIDATION

## Parity gap D: PRESENCE_UPDATE push fan-out (M78) (gate: pass)

- Timestamp: 2026-04-28T06:24:50+00:00
- Delivered: Server now actively pushes online state changes instead of only answering pull queries. protocol.py has a new PresenceUpdatePayload (user_id, online, last_seen_at_ms). PresenceService accepts a transition_handler callback and exposes notify_session_started + a private _is_user_online_excluding helper; touch() detects offline->online by checking other sessions; revoke_device fires offline transition when removing the last fresh session. ServerApplication.__init__ wires PresenceService.set_transition_handler(self._fanout_presence_transition) which fans PRESENCE_UPDATE to every user sharing at least one conversation with the transitioning user via _fanout_to_users. LOGIN_REQUEST and REGISTER_REQUEST dispatch paths call presence_service.notify_session_started after the auth service creates the session. New validator scripts/validate_presence_push.py covers 6 scenarios via an in-process RecordingRegistry stub: login fan-out, no double-push for already-online user, stale->heartbeat re-online, transient revoke stays online, no false offline transition during multi-revoke, and shared-conversation gating (carol registered fresh sees no alice-presence push).
- Verified: validate_presence_push 6/6; validate_presence_heartbeat 6/6 (no regression); validate_typed_errors 11/11; validate_cpp_chat_e2e 3/3; validate_cpp_remote_session 8/8; validate_desktop_smoke 1/1; validate_rendezvous 6/6; validate_terminate_disconnect 8/8; validate_message_fanout 4/4; validate_incremental_sync 8/8; validate_message_search 5/5; validate_attachments 11/11; validate_contacts 8/8; validate_group_conversations 6/6; bundle verify ok 72 reqs
- Next: Move to release-readiness arc: M69 deployment hardening sweep / M70 Windows installer / mobile arc
- Covers: REQ-PRESENCE-HEARTBEAT, REQ-TYPED-PROTO, REQ-VALIDATION

## Deployment hardening acceptance sweep (M79) (gate: pass)

- Timestamp: 2026-04-28T06:42:50+00:00
- Delivered: Added scripts/_sweep_validators.py one-shot helper that runs every validate_*.py and tags 4 external-state validators (docker_deploy, postgres_repository, postgres_backup_restore, tls_proxy_smoke) as SKIP_EXTERNAL since they need live Docker/PostgreSQL/TLS-proxy stacks (PA-001/PA-002/PA-003 still gating). Confirmed full local regression coverage.
- Verified: 37/37 in-process validators PASS (~190 individual scenarios across attachments/contacts/cpp_chat_e2e/cpp_remote_session/cpp_tls_client/desktop_smoke/device_management/empty_state_file/group_conversations/history_paging/incremental_sync/input_injection/media_frames/message_actions/message_edit_delete/message_fanout/message_search/presence_heartbeat/presence_push/profile_search/read_receipts/registration/reliable_stream/rendezvous/screen_source/session_hardening/session_persistence/sqlite_persistence/terminate_disconnect/tls_config/tls_deployment_config/tls_dev_cert/tls_handshake/typed_errors/udp_media/udp_media_auth/udp_relay); plus 9/9 json_parser_test + 20/20 app_desktop_store_test C++ binaries. 4 external-state validators skipped pending PA-001/PA-002/PA-003.
- Next: M80 Windows installer + signing plan
- Covers: REQ-VALIDATION, REQ-LINUX-DOCKER-DEPLOYMENT

## Windows installer with Inno Setup (M80) (gate: pass)

- Timestamp: 2026-04-28T06:46:53+00:00
- Delivered: deploy/windows/telegram_like_desktop.iss.template — Inno Setup script template with placeholders for version/publisher/URL/source-stage/output, x64 architecture, lowest privileges (override-allowed), recursive [Files] copy of the staged windeployqt tree, [Icons] for Start Menu / desktop shortcut, [Run] post-install launch, and a documented (commented-out) SignTool= directive ready for Authenticode once a cert lands. scripts/package_windows_desktop.ps1 gains -Installer / -AppVersion / -AppPublisher / -AppUrl / -IsccPath switches; substitutes placeholders, drops a generated .iss in the stage dir, invokes ISCC.exe, writes installer + .sha256 to artifacts/windows-desktop/installers/. New scripts/validate_windows_installer.py covers 5 static scenarios (template placeholders, app_desktop.exe target, SignTool directive presence, package-script wiring, optional checksum verification when an installer build is present). Real installer build produced telegram_like_desktop_setup_<timestamp>.exe (~2.1 MB) + matching SHA256.
- Verified: powershell scripts/package_windows_desktop.ps1 -BuildDir build-verify -Installer succeeds end-to-end with ISCC.exe; validate_windows_installer.py 5/5 (including the checksum re-hash of the produced .exe matches the .sha256 file)
- Next: M81 mobile (Android via Qt for Android)
- Covers: REQ-WINDOWS-PACKAGE-STAGING, REQ-WINDOWS-PACKAGE-CHECKSUMS, REQ-VALIDATION

## Blocker at 2026-04-28T06:50:19+00:00

- Reason: Android APK build requires Android SDK Platform 33+, NDK 26.x, Build-Tools 34+, and JDK 17 to be installed locally. Current environment has ANDROID_HOME pointing at a path that does not exist on disk and only JDK 1.8 (too old for Qt for Android). Static prep landed and is verified by validate_android_prep.py 6/6, but no APK can be produced without the toolchain.
- Needed to proceed: User approval + multi-GB toolchain install (Android Studio or cmdline-tools-only bundle, NDK 26.x via SDK manager, JDK 17 from Temurin/Adoptium); PA-007 in 08-atlas-task-library has the exact qt-cmake invocation to run once installed.

## Android (Qt for Android) prep + PA-007 toolchain block (M81) (gate: partial)

- Timestamp: 2026-04-28T06:50:39+00:00
- Delivered: deploy/android/AndroidManifest.xml — minimal Qt for Android manifest with INTERNET + ACCESS_NETWORK_STATE permissions and the QtActivity LAUNCHER entry. deploy/android/README.md documents the missing toolchain (ANDROID_HOME path is dead, only JDK 1.8 installed) and the exact qt-cmake invocation to use once SDK Platform 33+ / NDK 26.x / JDK 17 are installed. New scripts/validate_android_prep.py covers 6 static scenarios (POSIX socket branch in net/platform.h, Schannel TLS gated on _WIN32 in tcp_line_client header AND .cpp, manifest INTERNET+QtActivity+LAUNCHER, README PA-007 reference + qt-cmake + JDK 17, CMakeLists ws2_32/secur32 only inside if(WIN32)). 08-atlas-task-library.md gains PA-005 (Authenticode cert) + PA-007 (Android toolchain install) Pending Actions and ATLAS-M81 partial entry.
- Verified: validate_android_prep.py 6/6; existing build-verify Windows build still clean; 37/37 in-process validators stay green (M79 sweep unchanged); Inno Setup installer + checksum still produce-able (M80 unchanged). Static prep proves chat_client_core POSIX paths are reachable; actual APK build gated on PA-007 toolchain install.
- Next: Resume after PA-007 toolchain install OR pivot to release-readiness items (PA-001/PA-002 PostgreSQL TLS live smoke, push notifications protocol, mobile UI redesign as Qt Quick)
- Covers: REQ-VALIDATION

## Unblocked at 2026-04-28T07:35:01+00:00

- Resolution: PA-001/PA-002 resolved (Docker proxy configured + Dockerfile ARG plumbing + live PostgreSQL TLS smoke green). Android toolchain (PA-007) remains a documented Pending Action but does not gate the rest of the arc — tracked in 08-atlas-task-library.md instead of bundle-level block.

## Live PostgreSQL TLS proxy smoke (M82, PA-001+PA-002+PA-003 resolved) (gate: pass)

- Timestamp: 2026-04-28T07:35:25+00:00
- Delivered: Brought up the 3-container PostgreSQL TLS stack via WSL Docker (postgres + telegram-server-postgres + telegram-tls-proxy-postgres on 8444). Required two infrastructure fixes to make it work: (a) wrote /etc/systemd/system/docker.service.d/http-proxy.conf with HTTP_PROXY=http://10.20.11.30:10809 + HTTPS_PROXY + NO_PROXY then daemon-reload + restart docker so the daemon's image pulls reach docker.io; (b) added explicit ARG HTTP_PROXY/HTTPS_PROXY/NO_PROXY (upper- and lower-case) plus matching ENV lines at the top of deploy/docker/server.Dockerfile so RUN pip install reaches pypi.org through the same proxy that's already plumbed via docker-compose build args. After containers were healthy, exercised the full PG-backed deployment surface: validate_tls_proxy_smoke.py --port 8444 (PASS, sess_1 issued through nginx stream TLS termination); validate_postgres_repository --pg-dsn=...:5432 (PASS 3/3 — installed psycopg[binary]>=3.2 on host first); validate_postgres_backup_restore --pg-dsn (PASS 1/1); validate_docker_deploy --port 8788 (PASS, plaintext path through PostgreSQL backend). Tore the stack down with docker compose down (volumes preserved). Updated 08-atlas-task-library.md to mark PA-001/PA-002/PA-003 DONE and rewrite the Notes section.
- Verified: Live: tls proxy smoke ok user=u_alice session=sess_1 (port 8444); docker deploy smoke ok user=u_alice session=sess_2 (port 8788); validate_postgres_repository.py 3/3; validate_postgres_backup_restore.py 1/1. Stack: 3 containers up (postgres, telegram-server-postgres, telegram-tls-proxy-postgres), all healthy. Tore down cleanly.
- Next: Resume with PA-005 (Authenticode cert) / PA-007 (Android toolchain) / push notifications protocol / mobile UI redesign
- Covers: REQ-LINUX-DOCKER-DEPLOYMENT, REQ-POSTGRES-REPOSITORY-BOUNDARY, REQ-POSTGRES-SCHEMA-BACKUP, REQ-TLS-PG-PROXY, REQ-TLS-TERMINATION-PROFILE, REQ-VALIDATION

## Push notification protocol surface (M84) (gate: pass)

- Timestamp: 2026-04-28T10:49:20+00:00
- Delivered: Added 5 new MessageType values (PUSH_TOKEN_REGISTER / PUSH_TOKEN_UNREGISTER / PUSH_TOKEN_LIST_REQUEST / PUSH_TOKEN_LIST_RESPONSE / PUSH_TOKEN_ACK) plus typed payloads (PushTokenRegisterRequestPayload / PushTokenUnregisterRequestPayload / PushTokenAckPayload / PushTokenDescriptor / PushTokenListResponsePayload) in protocol.py with parse_request_payload coverage. New PushTokenRecord in state.py + InMemoryState.push_tokens flat list (in-memory only; SQLite/PG persistence is PA-008 follow-up). New services/push_tokens.py provides register / unregister / tokens_for_user / notify_offline_recipient / drain_pending plus a PendingDelivery dataclass — the mock queue is what a real FCM/APNs worker would drain. ServerApplication wires PushTokenService, dispatches the 3 RPCs (register/unregister/list), and adds _enqueue_mock_pushes_for_offline_recipients hook that fires after MESSAGE_SEND for participants whose presence_service.is_user_online() is False. New validate_push_tokens.py covers 6 scenarios (register+list round-trip, offline recipient enqueues mock push, online recipient short-circuits, unregister, empty-payload rejection, token rotation idempotency).
- Verified: validate_push_tokens.py 6/6; full sweep 40/40 in-process validators (37 → 40 with android_prep + windows_installer + push_tokens added across M81/M80/M84). 4 external-state validators (docker/postgres x2/tls_proxy_smoke) remain SKIP_EXTERNAL.
- Next: M85 mobile UI redesign / drain real FCM (PA-008) once cred/transport ready
- Covers: REQ-CHAT-CORE, REQ-TYPED-PROTO, REQ-VALIDATION

## Real Android APK build (M83, PA-007 resolved) (gate: pass)

- Timestamp: 2026-04-28T10:54:15+00:00
- Delivered: Found Android SDK at D:\android\sdk (NDK 30.0.14904198, build-tools 37.0.0, platform android-37.0, cmdline-tools/latest) and JDK 21.0.11 at C:\Program Files\Java\jdk-21.0.11. Three infrastructure fixes to land the APK: (1) created junction D:\android\sdk\platforms\android-37 -> android-37.0 because androiddeployqt expects standard naming; (2) wrote ~/.gradle/gradle.properties with systemProp.https.proxyHost=10.20.11.30 + Port 10809 so the gradle wrapper can pull dependencies through the corporate egress proxy; (3) trimmed deploy/android/AndroidManifest.xml to a modern minimal Qt for Android shape — dropped the legacy qt_sources/qt_libs/bundled_libs resource-array meta-data lines that newer Qt for Android (>=6.5) injects via gradle plugin. client/src/CMakeLists.txt switched to qt_add_executable for app_desktop with QT_ANDROID_PACKAGE_SOURCE_DIR + QT_ANDROID_MIN_SDK_VERSION 26 + QT_ANDROID_TARGET_SDK_VERSION 33 + QT_ANDROID_VERSION_NAME/CODE properties (Android-only). New scripts/build_android_apk.ps1 wraps the qt-cmake configure + cmake --target apk dance with all the env plumbing. validate_android_prep.py extended to 9 scenarios (added qt_add_executable check, build_android_apk.ps1 script existence, optional APK size sanity check).
- Verified: qt-cmake configure succeeded against Qt 6.11.0 android_arm64_v8a; chat_client_core compiles clean for arm64-v8a Bionic libc (POSIX branches in net/* compile through unchanged); libapp_desktop_arm64-v8a.so links; cmake --build --target apk produced android-build-release-unsigned.apk = 11,360,200 bytes (11.4 MB) at build-android/client/src/android-build/build/outputs/apk/release/. validate_android_prep.py 9/9. Full sweep 41/41 in-process validators stay green.
- Next: M85 mobile UI redesign (Qt Quick / QML phone-shaped chat); installer signing PA-005 covers Android keystore + Windows Authenticode together
- Covers: REQ-VALIDATION, REQ-CHAT-CORE

## Mobile UI redesign — Qt Quick / QML phone shell (M85) (gate: pass)

- Timestamp: 2026-04-28T11:08:17+00:00
- Delivered: New app_mobile target: a Qt Quick / QML phone-shaped client built on top of the same chat_client_core. New global-namespace MobileChatBridge (mobile_chat_bridge.h/.cpp) is the QML facade exposing connectAndLogin/selectChat/sendMessage/conversationList/selectedMessages as Q_INVOKABLE plus identityChanged/storeChanged/connectedChanged/errorReported signals; threads RPCs off-UI with QMetaObject::invokeMethod marshalling and shutting_down_ guards (same shape as desktop). Four QML pages under client/src/app_mobile/qml/: Main.qml (StackView shell + Connections to nav between pages), LoginPage.qml (host/port/user/password/device form with Telegram-style avatar disc + accent-blue Connect button), ChatListPage.qml (conversation rows with deterministic-color initial avatars + unread badges, Telegram-blue header), ChatPage.qml (header with back button, message timeline with mint outgoing + white incoming bubbles + pending/failed states, rounded composer + circular blue Send). CMakeLists.txt wires qt_add_executable + qt_add_qml_module(URI TelegramLikeMobile) with AUTOMOC + qt_policy(SET QTP0001 NEW) + QT_ANDROID_* properties for mobile APK + windeployqt POST_BUILD with --qmldir for Windows preview.
- Verified: validate_mobile_ui.py 6/6 (bridge header surface, marshalled invokes, all 4 QML pages reference ChatBridge correctly, CMake wiring, optional binary size sanity); Windows app_mobile.exe builds + launches cleanly with clean PATH (no Qt on PATH); Android app_mobile.apk builds (20.0 MB unsigned, arm64-v8a) via cmake --target app_mobile_make_apk; full sweep 41/41 in-process validators (was 40 before mobile_ui added).
- Next: PA-008 real FCM/APNs HTTP transport / PA-005 Android keystore + Authenticode signing / device emulator install for live mobile UI smoke
- Covers: REQ-CHAT-CORE, REQ-VALIDATION

## Atlas task library cleanup (M86) (gate: pass)

- Timestamp: 2026-04-28T12:00:15+00:00
- Delivered: Rewrote 08-atlas-task-library.md: dropped the stale Current Delivery Plan list (M66-M68 wording), replaced with a Recent shipped milestones rollup (M66->M85), and recreated the Open Task Backlog as M71 (remote-control), M87 (CI), M88 (chunked upload), M89 (Linux/macOS desktop), M90 (phone OTP), M91 (real FCM transport), M92 (observability), M93 (rate limiting), M94 (2FA), M95 (account delete + export). Updated Notes to reflect 83 milestones / 72 REQs / 0 blockers and the two remaining external Pending Actions (PA-005 signing, PA-008 FCM credential).
- Verified: manage_delivery_bundle verify ok, 72 reqs, 0 problems
- Next: M87 CI/CD via GitHub Actions
- Covers: REQ-VALIDATION

## CI/CD via GitHub Actions (M87) (gate: pass)

- Timestamp: 2026-04-28T12:11:03+00:00
- Delivered: .github/workflows/ci.yml with 3 jobs: (1) validators — runs scripts/_sweep_validators.py on ubuntu-latest with python 3.12 + cryptography for the TLS dev cert helper; (2) linux-cpp — installs build-essential/cmake/ninja, configures CMake with TELEGRAM_LIKE_SKIP_WINDEPLOYQT=ON, builds the 6 portable targets (chat_client_core, telegram_like_client, app_chat, app_desktop_store_test, json_parser_test, remote_session_smoke) Qt-free, runs json_parser_test + app_desktop_store_test inline, then re-runs the validator sweep with the just-built binaries to pick up cpp_chat_e2e / cpp_remote_session / desktop_smoke; (3) bundle-verify — vendored minimal status.json invariant check (every REQ has a covering milestone, no fail gates, required artifact files exist). Concurrency group cancels in-progress runs of the same branch. scripts/_sweep_validators.py extended with NEEDS_BINARY map + _has_built_binary probe so C++-binary-dependent validators report SKIP_NO_BINARY (vs FAIL) when their .exe / ELF is absent — makes the sweep CI-portable. New scripts/validate_ci_workflow.py covers 7 static scenarios (workflow parses, 3 expected jobs, sweep invocation, portable C++ targets, inline test exe runs, concurrency declaration, sweep skip-no-binary plumbing).
- Verified: ci.yml YAML parses; validate_ci_workflow.py 7/7; full sweep 42/42 in-process validators (added ci_workflow); bundle-verify inline script reads status.json correctly (72 reqs, 0 missing, 0 fail gates).
- Next: M88 chunked attachment upload
- Covers: REQ-VALIDATION

## Chunked attachment upload (M88) (gate: pass)

- Timestamp: 2026-04-28T12:19:34+00:00
- Delivered: 5 new MessageType values: ATTACHMENT_UPLOAD_INIT_REQUEST/INIT_RESPONSE/CHUNK_REQUEST/CHUNK_ACK/COMPLETE_REQUEST. 5 new typed payloads in protocol.py + parse_request_payload coverage. 5 new ErrorCodes (UNKNOWN_UPLOAD/UPLOAD_TOO_LARGE/UPLOAD_CHUNK_OUT_OF_ORDER/UPLOAD_SIZE_MISMATCH/UPLOAD_LIMIT_REACHED) with human messages. Server services/chat.py gains _UploadSession state-machine class + ChatService.init_upload / accept_upload_chunk / complete_upload methods. complete_upload writes through AttachmentBlobStore when configured, falls back to inline base64 (same contract as send_attachment_message), then reuses the existing message_deliver fan-out path so receivers see chunked uploads identically to small-file inline uploads. Tunables: DEFAULT_CHUNK_SIZE_BYTES=1MB, MAX_CHUNKED_UPLOAD_BYTES=64MB, MAX_ACTIVE_UPLOADS_PER_USER=8. ServerApplication dispatches the 3 new RPCs with ServiceError → typed-error mapping; complete also runs _enqueue_mock_pushes_for_offline_recipients so push notifications flow on chunked sends too. New scripts/validate_chunked_upload.py covers 5 scenarios: 5MB round-trip with byte-exact fetch, >64MB rejected at init, out-of-order chunk rejected, short complete rejected, 9th concurrent upload rejected.
- Verified: validate_chunked_upload.py 5/5; full sweep 43/43 in-process validators (added chunked_upload + ci_workflow this round); bundle verify ok 72 reqs 0 problems.
- Next: Linux desktop port (M89), real FCM transport (M91/PA-008), or signing certs (PA-005)
- Covers: REQ-ATTACHMENTS, REQ-CHAT-CORE, REQ-VALIDATION

## Linux desktop build path (M89) (gate: pass)

- Timestamp: 2026-04-28T12:42:21+00:00
- Delivered: Real Linux build verified end-to-end on Ubuntu 24.04 (WSL2): apt-installed Qt 6.4.2 + qt6-declarative-dev + Qt Quick QML modules; cmake -GNinja Release configure clean; all 8 targets compile (chat_client_core, telegram_like_client, app_chat, app_desktop_store_test, json_parser_test, remote_session_smoke, app_desktop, app_mobile); json_parser_test 9/9 + app_desktop_store_test 20/20 run green on Linux x86_64. Two source-level Qt-version compatibility fixes: (1) client/src/CMakeLists.txt guards qt_policy(SET QTP0001 NEW) behind if(COMMAND qt_policy) since Qt 6.4 doesn't ship that command; (2) client/src/app_mobile/main.cpp falls back to engine.load(QUrl("qrc:/qt/qml/TelegramLikeMobile/Main.qml")) under #if QT_VERSION < 6.5.0 since loadFromModule is Qt 6.5+. New deploy/linux/README.md documents apt deps + cmake invocation + Qt-version notes; deploy/linux/telegram-like.desktop is an XDG launcher entry. ci.yml gains a linux-desktop job that installs the Qt apt packages and builds + tests the same set; existing validate_ci_workflow.py updated to expect 4 jobs. New scripts/validate_linux_desktop.py covers 5 static scenarios (README, .desktop XDG entry, qt_policy guard, app_mobile fallback, CI job presence).
- Verified: validate_linux_desktop.py 5/5; validate_ci_workflow.py 7/7; full sweep 44/44 in-process validators (added linux_desktop). Real WSL Linux build: 8 targets compile, json_parser_test 9/9 + app_desktop_store_test 20/20 pass on Ubuntu 24.04. Bundle verify ok 72 reqs.
- Next: M91 real FCM/APNs delivery worker
- Covers: REQ-VALIDATION, REQ-CHAT-CORE

## Push delivery worker with pluggable transports (M91) (gate: pass)

- Timestamp: 2026-04-28T12:47:39+00:00
- Delivered: New server/server/services/push_dispatch.py: PushDispatchWorker drains PushTokenService.pending_deliveries and routes batches per platform via a Transport protocol. Three concrete transports — FakeTransport (records calls, used by tests), LogOnlyTransport (writes one line per delivery to any stream — safe default with no creds), and FCMHttpTransport (FCM v1 message-send shape; uses stdlib urllib so no extra dependency; dry_run=True by default and forced True when bearer_token is empty so CI never accidentally hits Google). PushDispatchWorker.tick() returns a DeliveryReport with successful/failed splits so future retry logic has a hook. ServerApplication wires a default LogOnlyTransport-backed worker as self.push_dispatch_worker so the pieces are reachable from outside without further setup. New scripts/validate_push_dispatch.py covers 5 scenarios — empty queue no-op, per-platform routing (fcm batch=2 + apns batch=1), default fallback when platform has no specific transport, FCMHttpTransport.dry_run records payload without POSTing, end-to-end offline send -> mock queue -> worker -> FakeTransport. PA-008 narrows from 'wire transport + creds' to just 'plumb bearer-token credential'.
- Verified: validate_push_dispatch.py 5/5; full sweep 45/45 in-process validators (added push_dispatch). Existing validate_push_tokens 6/6 still green; presence_push 6/6; cpp_chat_e2e 3/3; chunked_upload 5/5. Bundle ok 72 reqs.
- Next: Phone-number OTP (M90) / FCM bearer token wiring (PA-008) / 2FA / observability
- Covers: REQ-CHAT-CORE, REQ-VALIDATION

## Phone-number + OTP login with mock SMS (M90) (gate: pass)

- Timestamp: 2026-04-28T14:18:44+00:00
- Delivered: 4 new MessageType + 4 typed payloads (PHONE_OTP_REQUEST/REQUEST_RESPONSE/VERIFY_REQUEST/VERIFY_RESPONSE). 6 new ErrorCodes (INVALID_PHONE_NUMBER/PHONE_OTP_RATE_LIMITED/INVALID_OTP_CODE/OTP_EXPIRED/OTP_ATTEMPTS_EXHAUSTED/RATE_LIMITED). New server/server/services/phone_otp.py with PhoneOtpService + Sender protocol + MockSender default (records every code in outbox + writes to stream — perfect for first-party clients during dev; tests just call sender.latest_for(phone)). Tunables: 6-digit codes, 5-min TTL, 30-second resend cooldown, 5 verify attempts before exhaustion. verify_code mints a SessionRecord shaped exactly like AuthService.login does + creates a synthetic 'phone:<E.164>' user transparently (so phone-OTP-only accounts can't password-login but the rest of the codebase reads .username/.user_id deterministically). ServerApplication wires the service, dispatches the 2 RPCs as pre-authenticated branches (alongside LOGIN/REGISTER), calls presence_service.notify_session_started after verify so the same offline->online transition push fires. New scripts/validate_phone_otp.py covers 5 scenarios: request->verify->new account + idempotent return for repeat phone, INVALID_PHONE_NUMBER for non-E.164, wrong-code 5x -> OTP_ATTEMPTS_EXHAUSTED + subsequent correct code still rejected, PHONE_OTP_RATE_LIMITED inside 30s + lifts after, OTP_EXPIRED past TTL.
- Verified: validate_phone_otp.py 5/5; bundle verify ok 72 reqs.
- Next: M92 observability (structured logs + /metrics + health)
- Covers: REQ-CHAT-CORE, REQ-VALIDATION, REQ-TYPED-PROTO

## Observability — structured logs + Prometheus + healthz (M92) (gate: pass)

- Timestamp: 2026-04-28T14:25:27+00:00
- Delivered: New server/server/services/observability.py — stdlib-only (json/threading/http.server). Three components: StructuredLogger (JSON-line emission, configurable stream), MetricsRegistry (counters + gauges + histograms with default latency-friendly buckets, label-sorted Prometheus exposition), HealthAggregator (pluggable checks). Sidecar HTTP server on its own thread serves GET /metrics (Prometheus text/plain v0.0.4) and GET /healthz (200 with all-ok JSON, 503 with failing-check JSON). Default counters declared up-front: dispatch_requests_total, dispatch_request_duration_seconds, messages_sent_total, attachments_uploaded_total, phone_otp_requests_total, phone_otp_verifications_total, rate_limited_total, active_sessions. ServerApplication wraps dispatch() in _dispatch_inner so every inbound message increments the counter (labelled by type + outcome ok|error|exception) and observes latency in the histogram. Default health checks registered: state_loaded + active_session_count. New scripts/validate_observability.py covers 6 scenarios (counter+histogram emission, /metrics endpoint shape, /healthz 200, /healthz 503 on failing check, structured JSON-line logger, ok-vs-error outcome separation). NO_PROXY workaround for corporate-egress proxies that hairpin localhost traffic.
- Verified: validate_observability.py 6/6; bundle ok 72 reqs.
- Next: M93 rate limiting
- Covers: REQ-VALIDATION, REQ-CHAT-CORE

## Per-session / per-key rate limiting (M93) (gate: pass)

- Timestamp: 2026-04-28T14:32:12+00:00
- Delivered: New server/server/services/rate_limiter.py — thread-safe TokenBucket store keyed by (op, key). RateConfig has rate (tokens/sec) + burst (capacity) + per_minute() helper. DEFAULT_LIMITS covers message_send (5/s burst 10), register_request (3/min burst 5), phone_otp_request (2/min burst 3), phone_otp_verify_request (20/min burst 20), presence_query_request (5/s burst 10), message_send_attachment (2/s burst 4). Configurable at runtime via RateLimiter.configure(op, rate, burst). ServerApplication wires the limiter, exposes _rate_check helper that increments rate_limited_total{type=op} on rejection and returns a typed RATE_LIMITED ServiceError response. Hooks added pre-payload-handling on 6 dispatch sites: REGISTER_REQUEST (key=username), PHONE_OTP_REQUEST (key=phone), PHONE_OTP_VERIFY_REQUEST (key=phone), MESSAGE_SEND (key=session_id), MESSAGE_SEND_ATTACHMENT (key=session_id), PRESENCE_QUERY_REQUEST (key=session_id). New scripts/validate_rate_limiting.py covers 5 scenarios: message_send 10-burst then refill via FakeMonoClock, phone_otp per-phone isolation across both rate-limiter + OTP cooldown defenses, register_request burst per username, presence_query per-session bucket isolation, rate_limited_total counter increments per rejection.
- Verified: validate_rate_limiting.py 5/5; bundle ok 72 reqs.
- Next: M94 TOTP 2FA
- Covers: REQ-VALIDATION, REQ-CHAT-CORE

## TOTP 2FA (M94) (gate: pass)

- Timestamp: 2026-04-28T14:38:51+00:00
- Delivered: RFC 6238 TOTP 2FA, stdlib-only (hmac+hashlib+secrets+base64+struct). state.UserRecord gains two_fa_secret field (empty = disabled). New server/server/services/two_fa.py with TwoFAService.begin_enable / confirm_enable / verify_login_code / disable plus pure helpers generate_totp_code + verify_totp + provisioning_uri (otpauth://totp/...). 6 new MessageType (TWO_FA_ENABLE_REQUEST/RESPONSE, TWO_FA_VERIFY_REQUEST/RESPONSE, TWO_FA_DISABLE_REQUEST/RESPONSE) + 4 typed payloads + 4 ErrorCodes (TWO_FA_ALREADY_ENABLED, TWO_FA_NOT_ENABLED, INVALID_TWO_FA_CODE, TWO_FA_REQUIRED). LoginRequestPayload gains optional two_fa_code field. LOGIN_REQUEST dispatch verifies the password first, then if user has 2FA enabled requires + verifies the TOTP code with ±1 step (30s) tolerance — failed 2FA rolls back the freshly-issued session so the failed login doesn't pollute session counts. New scripts/validate_two_fa.py covers 4 scenarios: full enroll-verify-login-disable lifecycle (login flips between requires-code and not), double-enable rejected, disable without 2FA rejected, verify_enable without begin rejected.
- Verified: validate_two_fa.py 4/4; bundle ok 72 reqs.
- Next: M95 account delete + data export
- Covers: REQ-CHAT-CORE, REQ-VALIDATION, REQ-TYPED-PROTO

## Account export + delete (M95) (gate: pass)

- Timestamp: 2026-04-28T14:46:26+00:00
- Delivered: GDPR-style account lifecycle. 4 new MessageType (ACCOUNT_EXPORT_REQUEST/RESPONSE, ACCOUNT_DELETE_REQUEST/RESPONSE) + 3 typed payloads (AccountExportResponsePayload + AccountDeleteRequestPayload + AccountDeleteResponsePayload). New ErrorCode ACCOUNT_DELETE_AUTH_FAILED with human message. New server/server/services/account_lifecycle.py with AccountLifecycleService.export and .delete: export emits user-readable JSON snapshot of profile/devices/sessions/contacts/push_tokens/authored_messages; delete verifies password (constant-time hmac.compare_digest via verify_password) plus TOTP if 2FA is enabled, then revokes sessions, removes devices, drops push tokens, scrubs contacts in BOTH directions, removes user from all conversation participant lists, tombstones authored messages (sender_user_id->u_deleted, text='', deleted=true — preserves conversation history for other peers, mirroring Telegram), then drops the user record. Returns counts so clients can show 'we removed N messages' UX. ServerApplication wires the service + dispatches both RPCs. New scripts/validate_account_lifecycle.py covers 5 scenarios: export populates all sections, wrong-password delete rejected with account intact, full delete tombstones + cleans up both contact directions + bob's session unaffected, post-delete login returns INVALID_CREDENTIALS, 2FA-protected delete requires fresh TOTP. PA-009 added for real Twilio SMS transport.
- Verified: validate_account_lifecycle.py 5/5; full sweep 50/50 in-process validators (added phone_otp + observability + rate_limiting + two_fa + account_lifecycle this round); bundle ok 72 reqs.
- Next: Push 3 commits + commit M86b-M95 / pick next direction (iOS, voice/video, E2E, Web client, etc.)
- Covers: REQ-CHAT-CORE, REQ-VALIDATION, REQ-PERSISTENCE

## macOS + iOS build path scaffolding (M96) (gate: pass)

- Timestamp: 2026-04-28T15:41:31+00:00
- Delivered: Strict additive Apple build path. New deploy/macos/Info.plist.in (configure_file template with @MACOSX_BUNDLE_*@ tokens, LSMinimumSystemVersion 11.0, NSHighResolutionCapable, dev TLS-friendly NSAppTransportSecurity). New deploy/ios/Info.plist.in (UIDeviceFamily 1+2 = iPhone+iPad, MinimumOSVersion 14.0, arm64 UIRequiredDeviceCapabilities, supported orientations, ATS allowing self-signed dev TLS). deploy/macos/README.md documents Homebrew Qt 6 install + cmake + targets; deploy/ios/README.md openly states the iOS path is untested-by-CI (Qt for iOS only ships in macOS Qt installer, not Homebrew, so GH Actions can't pull it without licensing/image-size cost) and gives the full xcodebuild + qt-cmake -G Xcode procedure for a future macOS host. client/src/CMakeLists.txt gains FOUR new strictly-guarded blocks (zero changes to existing target/source/link lines): if(APPLE AND NOT IOS) on app_desktop sets MACOSX_BUNDLE + bundle name/identifier/version/copyright/Info.plist; same on app_mobile; if(IOS) on app_mobile sets MACOSX_BUNDLE_INFO_PLIST -> ios plist + XCODE_ATTRIBUTE_TARGETED_DEVICE_FAMILY 1,2 + PRODUCT_BUNDLE_IDENTIFIER. Existing if(ANDROID), if(WIN32), if(MSVC) blocks untouched. .github/workflows/ci.yml gains a 4th job macos-build (macos-latest runner, brew install qt@6, configure with CMAKE_PREFIX_PATH=, build chat_client_core + portable targets + app_desktop + app_mobile, run json_parser_test + app_desktop_store_test, assert .app bundles materialised) so every push validates the macOS path automatically. New scripts/validate_apple_build_path.py covers 8 static scenarios: Info.plist templating, READMEs document untested-iOS, CMake has Apple+iOS blocks for both targets, Apple-only properties (MACOSX_BUNDLE_INFO_PLIST + XCODE_ATTRIBUTE_*) ONLY appear inside if(APPLE...)/if(IOS) guards (regex-verified for leak-protection), no Cocoa/Foundation/UIKit/AppKit headers leaked into shared cross-platform sources without #if defined(__APPLE__) guard, ci.yml has macos-build job. validate_ci_workflow.py extended to expect 5 jobs (was 4).
- Verified: validate_apple_build_path.py 8/8; validate_ci_workflow.py 7/7; full sweep 51/51 in-process (added apple_build_path); Windows full reconfigure + 8-target build clean; json_parser_test 9/9 + app_desktop_store_test 20/20 on Win + Linux; WSL Ubuntu 24.04 full reconfigure + 8-target build clean (gates verified: APPLE blocks invisible to Linux, IOS block invisible everywhere); Android arm64 reconfigure + chat_client_core + app_desktop + app_mobile shared libs all build clean (verifies APPLE/IOS blocks don't leak to NDK build either). APK build in flight.
- Next: Live macOS / iOS build acceptance once a macOS host is available; until then the macos-build CI job is the ground-truth check on every push.
- Covers: REQ-VALIDATION, REQ-CHAT-CORE

## macOS + iOS build path scaffolding (M96, post-review) (gate: pass)

- Timestamp: 2026-04-28T16:02:51+00:00
- Delivered: Strict additive Apple build path with three audit-driven refinements vs the dropped first-pass commit. (1) Replaced bare 'if(IOS)' / 'if(APPLE AND NOT IOS)' guards with a local TELEGRAM_LIKE_TARGET_IS_IOS boolean computed from CMAKE_SYSTEM_NAME STREQUAL iOS OR IOS — works whether the toolchain wrapper is Qt's qt-cmake (sets IOS=TRUE) or a hand-rolled toolchain that only sets CMAKE_SYSTEM_NAME=iOS. (2) Extended validate_apple_build_path.py leak-check to include XCODE_ATTRIBUTE_PRODUCT_BUNDLE_IDENTIFIER alongside MACOSX_BUNDLE_INFO_PLIST + XCODE_ATTRIBUTE_TARGETED_DEVICE_FAMILY, with a depth-tracking _find_blocks helper that handles nested if() correctly. (3) Documented macdeployqt as a pending milestone in deploy/macos/README.md — the .app emitted today depends on system Qt staying at the same path; for distribution to non-developer Macs macdeployqt must run POST_BUILD as the macOS analogue of the existing windeployqt step. New static scenario cmake_has_local_ios_boolean asserts the canonical detection. Plus original deliverables: deploy/macos/Info.plist.in + deploy/ios/Info.plist.in templates, deploy/macos/README.md + deploy/ios/README.md, .github/workflows/ci.yml macos-build job, validate_ci_workflow.py expects 5 jobs.
- Verified: validate_apple_build_path.py 9/9 (was 8); validate_ci_workflow.py 7/7; full sweep 51/51 in-process. Triple-platform reconfigure-and-build regression repeated POST review: Windows MSVC + Qt 6.11 8/8 targets clean + json_parser 9/9 + store 20/20; WSL Ubuntu 24.04 + Qt 6.4 8/8 targets clean + same C++ tests 9/9 + 20/20; Android NDK 30 + Qt 6.11 for Android full reconfigure + apk = 20,873,294 bytes (BYTE-IDENTICAL size to both pre-review build AND pre-Apple build, definitive proof the new local-boolean Apple guards stay invisible to NDK).
- Next: Pick next direction; macOS-build runs on first push to GitHub
- Covers: REQ-VALIDATION, REQ-CHAT-CORE

## Concurrency + leak fixes (M97) (gate: pass)

- Timestamp: 2026-04-28T16:24:12+00:00
- Delivered: Five M97 fixes from the post-Apple audit. (1) PhoneOtpService gets a threading.Lock guarding request_code (with opportunistic purge of expired entries) AND verify_code (atomic attempts increment + secret consume) — eliminates over-attempt-cap on parallel verify and bounds _codes growth at active-flow size. (2) TwoFAService gets a threading.Lock guarding _pending mutations (begin_enable + confirm_enable + new discard_pending_enrollment hook). (3) PushTokenService gets a threading.Lock guarding pending_deliveries appends (notify_offline_recipient) AND drain (drain_pending) — no lost entries when worker drains while message_send enqueues. (4) AccountLifecycleService.delete now optionally takes a TwoFAService and calls discard_pending_enrollment(user_id) before dropping the user — closes the leak where an unconfirmed 2FA secret would dangle in _pending after delete. (5) ServerApplication wires the new dependency. New scripts/validate_concurrency_fixes.py covers 5 scenarios: 8 parallel verify-with-wrong-code never overshoots MAX_VERIFY_ATTEMPTS and accounts for every attempt; request_code purges expired entries; parallel confirm_enable produces consistent final user.two_fa_secret state with no torn writes; 200 enqueue/drain race produces 200 drained (zero lost); account delete leaves _pending empty for the deleted user_id.
- Verified: validate_concurrency_fixes.py 5/5; validate_phone_otp 5/5; validate_two_fa 4/4; validate_push_tokens 6/6; validate_push_dispatch 5/5; validate_account_lifecycle 5/5; full sweep 52/52 in-process.
- Next: M98 block user + per-chat mute
- Covers: REQ-CHAT-CORE, REQ-VALIDATION

## Block user + per-conversation mute (M98) (gate: pass)

- Timestamp: 2026-04-28T16:35:37+00:00
- Delivered: Two related but independent surfaces. Block: 5 new MessageType (BLOCK_USER_REQUEST/UNBLOCK_USER_REQUEST/BLOCKED_USERS_LIST_REQUEST/_RESPONSE/BLOCK_USER_ACK), 4 typed payloads, 3 ErrorCodes (BLOCKED_BY_RECIPIENT/ALREADY_BLOCKED/NOT_BLOCKED). Per-(blocker, target) entries stored in state.blocked_users. ChatService.send_message dispatch path now checks: 1:1 conversation (exactly 2 participants) where the OTHER participant has the sender on their block list -> typed BLOCKED_BY_RECIPIENT, no message persisted, no fan-out. Group sends (>=3 members) unaffected — Telegram parity. Mute: 2 new MessageType (CONVERSATION_MUTE_UPDATE_REQUEST/_RESPONSE) + typed payloads. Per-(user, conversation) entries in state.conversation_mutes; muted_until_ms semantics 0=unmuted, -1=forever, N=ms-epoch with auto-clear when expired. New server/server/services/block_mute.py (threading.Lock, BlockMuteService.block/unblock/list_blocked/is_blocked_by/set_mute/get_mute). state.py adds BlockedUserEntry + ConversationMuteEntry + dict storage. ServerApplication wires the service + 4 dispatch branches + the 1:1 send-time block check. New scripts/validate_block_mute.py covers 6 scenarios: block round-trip, ALREADY_BLOCKED + NOT_BLOCKED idempotency, 1:1 DM rejected with BLOCKED_BY_RECIPIENT (no persistence), 3-member group send unaffected by 1:1 block, mute -1/future/0 round-trip, mute on unknown conversation rejected.
- Verified: validate_block_mute.py 6/6; full sweep 53/53 in-process; bundle ok 72 reqs.
- Next: M99 server-side drafts
- Covers: REQ-CHAT-CORE, REQ-VALIDATION

## M99 - server-side drafts (gate: pass)

- Timestamp: 2026-04-28T16:44:56+00:00
- Delivered: DraftsService + 6 protocol types + 3 dispatch branches; auto-clear on empty text + MESSAGE_SEND; participant validation
- Verified: scripts/validate_drafts.py 7/7; full sweep 54/54 (4 SKIP_EXTERNAL)
- Next: M100 - pinned + archived chats
- Covers: REQ-D2

## M100 - pinned + archived chats (gate: pass)

- Timestamp: 2026-04-28T16:50:23+00:00
- Delivered: ConversationFlagsService + 4 protocol types + 2 dispatch branches; conversation_sync injects per-user pinned/archived
- Verified: scripts/validate_pin_archive.py 6/6; full sweep 55/55 (4 SKIP_EXTERNAL)
- Next: M101 - profile + group avatars
- Covers: REQ-D3

## M101 - profile + group avatars (gate: pass)

- Timestamp: 2026-04-28T16:55:38+00:00
- Delivered: avatar_attachment_id on UserRecord/ConversationRecord; 4 protocol types; 2 dispatch branches; profile_response + conversation_sync surface the pointer
- Verified: scripts/validate_avatars.py 4/4; full sweep 56/56 (4 SKIP_EXTERNAL)
- Next: M102 - polls
- Covers: REQ-D4

## M102 - polls (gate: pass)

- Timestamp: 2026-04-28T17:02:46+00:00
- Delivered: PollsService + 4 protocol types + 5 error codes; messages can carry poll dict; conversation_sync surfaces poll tallies; POLL_UPDATED fanout on create/vote/close
- Verified: scripts/validate_polls.py 10/10; full sweep 57/57 (4 SKIP_EXTERNAL)
- Next: M103 - group permissions + admin roles
- Covers: REQ-D5

## M103 - group permissions + admin roles (gate: pass)

- Timestamp: 2026-04-28T17:14:06+00:00
- Delivered: ConversationRecord.roles + 1 protocol type + 3 error codes; chat.set_role/add_participant/remove_participant gated; ConversationDescriptor.roles surfaced; backwards compat for legacy 1:1
- Verified: scripts/validate_group_roles.py 10/10; full sweep 58/58 (4 SKIP_EXTERNAL, no regression in incremental_sync)
- Next: End of immediate ROI batch — review for next priorities
- Covers: REQ-D6

## M104 - Release-readiness verification gate sweep (gate: pass)

- Timestamp: 2026-04-29T01:00:44+00:00
- Delivered: Ran scripts/_sweep_validators.py across all 58 in-process validators after the M97-M103 chat-completeness gap-fill landed; no code change — pure regression gate. Bundle verify also re-run.
- Verified: scripts/_sweep_validators.py: 58 passed | 0 failed | 4 SKIP_EXTERNAL (docker_deploy, postgres_repository, postgres_backup_restore, tls_proxy_smoke — those four were last green at PA-001/002/003 live run on 2026-04-28). manage_delivery_bundle.py verify: ok=true, 77 REQs, 0 problems, 0 blockers.
- Next: M105 — ATLAS-M71: wire ReliableChannel into media_plane.py UDP transport and add Qt invite/approve UI in app_desktop.
- Covers: REQ-VALIDATION

## M105 - ReliableChannel wired into UDP relay (ATLAS-M71 part 1) (gate: pass)

- Timestamp: 2026-04-29T01:06:34+00:00
- Delivered: Added server/server/relay_peer.py exposing RelayPeerSession, which composes media_plane.frame + RELAY: prefix with reliable_stream.ReliableChannel. The relay server stays a dumb forwarder; reliability lives in the peers (REL/NAK/ACK packets ride inside the RELAY: body). Background reader thread per peer; lossy path injection via tx_loss/rx_loss filters for tests.
- Verified: scripts/validate_reliable_relay.py 5/5 (lossless 10+5, mid-seq drop NAK-recovered, reorder buffered+drained, tail-loss recovered via tick_retransmit, bidirectional 1-in-3 drop both directions delivered in order). Full sweep regression: 59 passed | 0 failed | 4 SKIP_EXTERNAL.
- Next: M106 — D9 media-plane AEAD: AES-GCM wrap on RELAY bodies via cryptography library.
- Covers: REQ-UDP-RELIABILITY, REQ-UDP-RELAY

## M106 - D9 media-plane AEAD (AES-256-GCM) (gate: pass)

- Timestamp: 2026-04-29T01:14:49+00:00
- Delivered: Added server/server/media_crypto.py (AES-256-GCM facade: 12-byte nonce || ct || 16-byte tag, base64 key wire format). Extended RelayPeerSession to seal/unseal at the RELAY: boundary so every REL/NAK/ACK packet is encrypted end-to-end (server stays opaque relay; control-plane treated as already-trusted, key rides in rendezvous payload). RemoteSessionRecord + SQLite remote_sessions gained relay_key_b64 column with idempotent ALTER TABLE migration. RemoteRendezvousInfoPayload extended with relay_key_b64 (default ''); RemoteSessionService.request_rendezvous lazily mints AES-256 key on first call so both peers retrieve the same key. Updated docs/architecture/current-state.md to remove the D9 + ReliableChannel-integration gap.
- Verified: scripts/validate_media_aead.py 5/5: shared-key round-trip + plaintext-leak guard (5 secret strings asserted absent from captured wire bytes), wrong-key silent drop with sender unacked stuck, keyed-vs-plain mutual drop, server-minted stable per-session key, legacy plaintext path. Full sweep regression: 60 passed | 0 failed | 4 SKIP_EXTERNAL — including validate_rendezvous.py 6/6 and validate_cpp_remote_session.py 8/8 (proves the additive payload field doesn't break existing parsers). cryptography 47.0.0 was already on PATH so no install step.
- Next: M107 — phase summary + finalize prep; mark Qt remote-control UI, PA-005/008/009, iOS/voice/web/prod-DB as deferred.
- Covers: REQ-MEDIA-AUTH, REQ-MEDIA-RENDEZVOUS

## M107 - Release-readiness phase summary (gate: pass)

- Timestamp: 2026-04-29T01:16:00+00:00
- Delivered: Updated 07-execution-log.md with the full phase summary (M104-M107): goal, requirement understanding, completed tasks, file/layer table, test flow, results, acceptance conclusion PASS, deferred work split into external-credential vs engineering-future-phase. Bundle stays in_progress; finalize NOT called (waiting on user direction on PA procurement / Qt UI / iOS / etc.).
- Verified: Final bundle verify: ok=true, 79 REQs covered, 0 problems, 0 blockers. Final sweep regression: 60 passed | 0 failed | 4 SKIP_EXTERNAL. Phase summary visible in .idea-to-code/telegram-platform/07-execution-log.md.
- Next: Awaiting user direction: (a) procure PA-005/008/009, (b) build Qt remote-control UI (M71-UI), (c) start iOS/voice/web/prod-DB phase, or (d) finalize the bundle if user accepts current scope.
- Covers: REQ-VALIDATION

## M108 - Qt remote-control UI (ATLAS-M71 part 2) (gate: pass)

- Timestamp: 2026-04-29T01:33:19+00:00
- Delivered: Added a 'Remote' page to app_desktop's settings panel: target device input, Invite button, remote_session_id input, Approve/Reject/Cancel/Terminate/Rendezvous buttons, RPC results log. All wired to the existing ControlPlaneClient remote-RPC surface; threaded so the GUI stays responsive. Also extended RemoteRendezvousResult with relay_key_b64 (so the C++ side observes M106's per-session AEAD key) and updated control_plane_client.cpp's parser. Extended remote_session_smoke.cpp with a positive invite -> approve -> rendezvous scenario gated on --peer-* flags; validate_cpp_remote_session.py now pre-registers Bob and passes --peer-* args.
- Verified: Build clean (cmake --build build-verify --config Debug --target app_desktop and remote_session_smoke — no warnings). validate_cpp_remote_session.py 9/9 (positive flow asserts relay_key_b64 non-empty AND matches across both peers via two ControlPlaneClient instances). Full sweep regression: 60 passed | 0 failed | 4 SKIP_EXTERNAL.
- Next: M109 — Voice/video call signaling + media skeleton: CALL_INVITE/ACCEPT/DECLINE/END RPCs, CallSessionService, audio-frame transport over relay, validator.
- Covers: REQ-CPP-CONTROL-CLIENT, REQ-C1-DESKTOP-GUI, REQ-REMOTE-LIFECYCLE

## M109 - Voice/video call signaling + AEAD media skeleton (gate: pass)

- Timestamp: 2026-04-29T01:42:49+00:00
- Delivered: Added CALL_INVITE/ACCEPT/DECLINE/END/RENDEZVOUS RPCs + CALL_STATE/CALL_RENDEZVOUS_INFO push types in server/server/protocol.py, with parsers and 6 typed ErrorCodes (UNKNOWN_CALL, CALL_PARTICIPANT_DENIED, CALL_NOT_RINGING, CALL_ALREADY_TERMINAL, CALL_NOT_ACTIVE, CALL_INVALID_KIND). New CallRecord in state.py (in-memory only). New CallSessionService implements the ringing -> accepted -> ended/declined/canceled FSM, mints an AES-256-GCM relay_key on accept (reuses M106 media_crypto), and exposes rendezvous. Wired 4 dispatch arms in app.py. Extended _build_session_authorizer in server/main.py so accepted calls also authorize the media plane (mirrors how active remote_sessions do).
- Verified: scripts/validate_call_session.py 6/6: full happy path with shared relay_key across both peers, decline by callee terminal, caller cancels while ringing, stranger denied across all 4 actions, invalid kind rejected, and AEAD-sealed PCM frames round-trip via M105/M106 RelayPeerSession over the relay using the per-call key. Full sweep regression: 61 passed | 0 failed | 4 SKIP_EXTERNAL.
- Next: M110 — Web client (HTTP+WS bridge to ServerApplication.dispatch) + minimal HTML/JS chat client.
- Covers: REQ-CHAT-CORE, REQ-MEDIA-AUTH

## M110 - Web client bridge (HTTP + WebSocket) (gate: pass)

- Timestamp: 2026-04-29T01:48:04+00:00
- Delivered: Stdlib-only RFC-6455 WebSocket bridge in server/server/web_bridge.py — each WS connection becomes a thin client of ServerApplication.dispatch (same JSON envelope format as the TCP control plane). Serves index.html + app.js as static assets at / and /app.js. server/web/index.html is a minimal single-page chat client with sign-in form, conversation log and composer; server/web/app.js handles the WS lifecycle, login round-trip, conversation_sync hydration, message_send and push handling (message_deliver, presence_update, conversation_updated).
- Verified: scripts/validate_web_bridge.py 5/5: GET / + /app.js serve correct content with right Content-Type; /nope returns 404; WS handshake honors RFC-6455 Sec-WebSocket-Accept; login over WS returns u_alice session; message_send -> conversation_sync round-trip lands; malformed JSON returns invalid_envelope error and the connection survives. Full sweep regression: 62 passed | 0 failed | 4 SKIP_EXTERNAL.
- Next: M111 — Redis hot-state cache bridge with FakeRedisTransport default + RedisHttpTransport stub gated on PA-010.
- Covers: REQ-CHAT-CORE, REQ-NET-ABSTRACTION

## M111 - Redis hot-state cache bridge (FakeRedis default + HTTP stub) (gate: pass)

- Timestamp: 2026-04-29T01:52:00+00:00
- Delivered: Added server/server/redis_cache.py with RedisCacheBridge over a Protocol-typed RedisTransport. FakeRedisTransport is a thread-safe in-memory dict with TTL semantics (default for tests + dev). RedisHttpTransport stubs the Upstash-shaped REST gateway path: in dry_run logs + records calls, otherwise raises PermissionError citing PA-010 (Redis endpoint + token). Bridge surface covers presence (5-minute TTL) and session (1-hour TTL); future PresenceService / Auth path opt-in via state.bind_redis_cache (deferred — keeps this milestone non-disruptive).
- Verified: scripts/validate_redis_cache.py 6/6: presence/session round-trip + TTL expiry + invalidate, corrupted JSON defensive, dry_run logs+records, missing-creds raises PermissionError mentioning PA-010, concurrent writes don't corrupt. Full sweep regression: 63 passed | 0 failed | 4 SKIP_EXTERNAL.
- Next: M112 — iOS UI scaffold (Info.plist + CMake guard, no compile env).
- Covers: REQ-PERSISTENCE, REQ-CHAT-CORE

## M112 - iOS UI scaffold validator (gate: pass)

- Timestamp: 2026-04-29T01:54:18+00:00
- Delivered: Existing scaffold from f10e238 (deploy/ios/Info.plist.in + client/src/CMakeLists.txt iOS guards + deploy/ios/README.md) was not regression-validated. Added scripts/validate_ios_scaffold.py — static-shape check covering Info.plist well-formedness + required keys (CFBundle*, MinimumOSVersion, UIDeviceFamily, UIRequiredDeviceCapabilities), CMake iOS guard presence, no-regression on Windows/Apple-non-iOS/Android guards, README documents PA-005 + PA-010 (Apple Developer cert + macOS host), and that the mobile entry point + QML root exist for the iOS build to compile against. Bumped my own Redis bridge from PA-010 -> PA-011 to avoid clashing with the iOS macOS-host PA-010 already documented in deploy/ios/README.md.
- Verified: scripts/validate_ios_scaffold.py 5/5; full sweep regression about to follow with M113. No code is compiled here — that will happen when a real macOS host picks up the scaffold (CI macos-build job exists but iOS isn't enabled yet).
- Next: M113 — macOS scaffold validator + macdeployqt POST_BUILD wiring.
- Covers: REQ-VALIDATION

## M113 - macOS UI scaffold + macdeployqt POST_BUILD (gate: pass)

- Timestamp: 2026-04-29T01:58:53+00:00
- Delivered: Wired the macOS analogue of windeployqt into client/src/CMakeLists.txt: when on Apple-non-iOS and macdeployqt is on PATH, both app_desktop.app and app_mobile.app get Qt frameworks (and QML modules for the Quick target) embedded automatically; opt out with -DTELEGRAM_LIKE_SKIP_MACDEPLOYQT=ON. Updated deploy/macos/README.md to mark the macdeployqt gap as resolved (M113). Added scripts/validate_macos_scaffold.py — 5 scenarios covering Info.plist shape, MACOSX_BUNDLE_* identifiers on both targets, M113 macdeployqt POST_BUILD presence + opt-out flag, no-regression on Windows windeployqt, README-PA-005 documentation.
- Verified: scripts/validate_macos_scaffold.py 5/5. Windows build still clean (cmake --build build-verify --config Debug --target app_desktop -> no warnings/errors after the macOS-only additions, since they're inside if(APPLE AND NOT TELEGRAM_LIKE_TARGET_IS_IOS) blocks). Full sweep: 65 passed | 0 failed | 4 SKIP_EXTERNAL.
- Next: M114 — Phase summary, memory update; do NOT call finalize.
- Covers: REQ-VALIDATION

## M114 - Release-readiness phase 2 summary (gate: pass)

- Timestamp: 2026-04-29T02:00:21+00:00
- Delivered: Updated 07-execution-log.md with the full M108-M114 phase summary: goal, completed tasks, file/layer table, results, acceptance conclusion PASS, deferred work split into external-credential vs engineering-future-phase. Bundle stays in_progress; finalize NOT called (waiting on user direction on PA procurement / next phase / iOS device / Redis cluster).
- Verified: Final bundle verify: ok=true, 77 REQs covered, 0 problems, 0 blockers. Final sweep: 65 passed | 0 failed | 4 SKIP_EXTERNAL. Phase summary visible in .idea-to-code/telegram-platform/07-execution-log.md.
- Next: User direction: (a) procure PA-005/008/009/010/011, (b) wire Redis bridge into PresenceService (1-milestone follow-up), (c) voice/video real codecs (Opus/VP8/H.264), (d) finalize the bundle if user accepts current scope.
- Covers: REQ-VALIDATION

## M115 - Production deploy 档1 (Docker + nginx + Prometheus, no app rewrite) (gate: pass)

- Timestamp: 2026-04-29T04:01:38+00:00
- Delivered: Added a production deployment stack that does NOT touch the application code path. server/main.py grows --metrics-port + --metrics-host so the M92 observability sidecar can run as a real entry point. deploy/docker/docker-compose.yml adds a production profile: telegram-server-prod (TCP 8787 + web bridge 8080 + sidecar 9100, postgres-backed, restart=always, healthchecked against /healthz, depends_on healthchecked postgres) and nginx-web (TLS termination + WS upgrade reverse proxy on 80/443, mounts new deploy/tls/nginx-web.conf with map   + /ws location + /healthz passthrough). Optional monitoring profile adds prometheus scraping the sidecar via deploy/docker/prometheus.yml. deploy/docker/production.env.example documents every prod env knob + PA-008/009/011 procurement placeholders. deploy/docker/README.md gets a full production runbook (one-shot bring-up, PA injection table, TLS cert swap, day-2 ops, dev-still-works callout).
- Verified: scripts/validate_production_compose.py 8/8 (compose parse, prod service command flags, healthcheck wiring, nginx mounts + ports, nginx WS upgrade headers + /healthz passthrough, prometheus scrape, env example coverage incl. PA-008/009/011, README runbook). docker compose --profile production --profile monitoring config (via WSL Docker) parses with 0 errors/warnings. --metrics-port smoke: curl http://127.0.0.1:9101/metrics + /healthz both 200, healthz returns ok=true with state_loaded + active_session_count. Existing dev profile untouched. Full sweep regression: 66 passed | 0 failed | 4 SKIP_EXTERNAL.
- Next: Optional follow-up: M116 wire Redis bridge into PresenceService (1-milestone, M111 bridge already in place); or档2 asyncio rewrite when concurrency really demands it.
- Covers: REQ-VALIDATION, REQ-PERSISTENCE

## M116 - Redis cache wired into PresenceService (gate: pass)

- Timestamp: 2026-04-29T04:14:51+00:00
- Delivered: PresenceService gains an optional redis_cache parameter. is_user_online / last_seen_ms / query_users now flow through a single _resolve_user_presence() that hits the cache first, falling back to a state.sessions scan + write-back on miss. Hot writes (touch, notify_session_started, revoke_device, transitions) refresh or invalidate the cached entry so the next read doesn't see a stale online/offline answer. Cache TTL is bounded by the presence TTL so the cached online answer can't outlive the underlying session-staleness window. Transport failures (get/set/delete throwing) fall back to the state scan and don't propagate. RedisCacheBridge.set_presence accepts a per-call ttl_override so PresenceService can pin the cache TTL to its own staleness window. ServerApplication + create_app gain a redis_cache kwarg. server/main.py adds --redis-url / --redis-token (RedisHttpTransport gated on PA-011) and --redis-fake (FakeRedisTransport in-memory, dev only).
- Verified: scripts/validate_presence_cache.py 8/8 — no-cache regression, miss-then-hit, touch refresh, notify_session_started write, revoke invalidate + recompute, TTL bounded by presence TTL with FakeRedis sharing the manual clock, transport-failure fallback, ServerApplication kwarg propagation. --redis-fake startup smoke (curl /healthz returns ok=true). Linux WSL re-run validate_presence_cache.py 8/8. Full sweep regression: 67 passed | 0 failed | 4 SKIP_EXTERNAL.
- Next: Optional follow-up: M117 wire Redis cache into AuthService session lookup (same pattern); or档2 asyncio rewrite when concurrency demands it.
- Covers: REQ-CHAT-CORE, REQ-PERSISTENCE

## M117 - Redis cache wired into AuthService session lookup (gate: pass)

- Timestamp: 2026-04-29T04:26:22+00:00
- Delivered: AuthService gains an optional redis_cache kwarg + bind_redis_cache(). resolve_session checks the cache first, reconstructing the SessionRecord from cached fields and applying the TTL freshness check on the cached last_seen_at; on miss it falls through to state.sessions and writes the result back. login + register write-through to the cache after persisting state. The TTL eviction path evicts both the in-memory session and the cached entry. Unknown sessions invalidate any (possibly stale) cached entry. Transport failures (get/set/delete raising) fall back to the state path without propagating. Cache TTL = configured session_ttl_seconds, with a 60s default when session_ttl is 0 so a stale cached entry can't outlive a touch-driven refresh by more than the cap. ServerApplication threads redis_cache through to AuthService alongside the M116 PresenceService binding.
- Verified: scripts/validate_auth_cache.py 9/9 on Windows + WSL Linux: no-cache regression, login + register write-through, cache hit short-circuits state lookup (proven by clearing state.sessions and confirming resolve still returns the session), TTL expiry double-evicts, unknown session invalidates, transport-down fallback, cache TTL default 60s when session_ttl=0, ServerApplication kwarg propagation. Full sweep regression: 68 passed | 0 failed | 4 SKIP_EXTERNAL.
- Next: Optional: cross-service touch-fanout (PresenceService.touch refreshes auth cache too) for tighter horizontal-scale staleness. Or档2 asyncio rewrite when concurrency demands it.
- Covers: REQ-CHAT-CORE, REQ-PERSISTENCE

## M118 - CI hardening: macdeployqt non-fatal + cpp validator POSIX paths (gate: pass)

- Timestamp: 2026-04-29T05:14:46+00:00
- Delivered: Three real bugs surfaced by GitHub Actions CI run: (1) M113 macdeployqt POST_BUILD passed -qmldir="..." with literal embedded quotes, qmlimportscanner received a path wrapped in extra quotes and failed; (2) Homebrew Qt on the runner doesn't include QtPdf/QtSvg/QtVirtualKeyboard/libwebp/libsharpyuv/libbrotlicommon, macdeployqt couldn't resolve those rpaths and failed the entire build (the .app was actually produced fine, only embedding failed); (3) validate_cpp_chat_e2e.py, validate_cpp_remote_session.py, validate_cpp_tls_client.py only listed Windows-style binary paths (build-{verify,codex,}/client/src/Debug/<stem>.exe) — sweep harness's _has_built_binary glob saw the macOS/Linux binaries and ran the validators, which then printed [FAIL] not built. Fix: (1) use single-token "-qmldir=PATH" form with no embedded quotes, (2) wrap macdeployqt invocation in sh -c '... || echo WARN...' so missing optional deps emit a warning instead of failing the build, (3) add shared _binary_candidates(stem) helper to the 3 cpp validators that enumerates the same path tree the sweep harness searches (build-{verify,codex,,macos,linux,wsl,android}/client/src/{,Debug,Release}/<stem>{,.exe}).
- Verified: Windows: 3 fixed cpp validators 3/3 + 9/9 + 2/2; full sweep 68 passed | 0 failed | 4 SKIP_EXTERNAL. WSL Linux: same 3 cpp validators 3/3 + 9/9 + 2/2 (find binaries at build-wsl/client/src/<stem>). validate_macos_scaffold.py still 5/5 (the ${TELEGRAM_LIKE_MACDEPLOYQT} variable expansion that the static check looks for survives inside the new sh -c wrapper).
- Next: Optional: M119 update GitHub Actions workflow to make the macOS build pass DTELEGRAM_LIKE_SKIP_MACDEPLOYQT=ON for explicit Qt-on-PATH builds, or install QtPdf/QtSvg/etc. via Homebrew so macdeployqt can succeed end-to-end.
- Covers: REQ-VALIDATION

## M119 - cpp_tls_client skip on non-Windows + sweep NEEDS_PLATFORM (gate: pass)

- Timestamp: 2026-04-29T05:40:38+00:00
- Delivered: GitHub Actions linux-validators job still failed validate_cpp_tls_client.py after M118 because the test forces app_chat --tls --tls-insecure but C++ TLS support is gated on _WIN32 (Schannel-only); on Linux app_chat ignores the TLS path and just fails to connect. The local WSL run masked this because the validator's binary candidate list put Windows-built build-verify/.../app_chat.exe first and WSL ran the Windows binary via interop. Fix: (a) add NEEDS_PLATFORM dict to scripts/_sweep_validators.py keyed by validator filename and a set of allowed sys.platform values; the sweep harness emits SKIP_PLATFORM and counts the validator as skipped on disallowed platforms. (b) validate_cpp_tls_client.py self-checks sys.platform != 'win32' at the top of main() and exits 0 with a SKIP_PLATFORM marker so direct invocation on Linux/macOS doesn't print misleading [FAIL] either. Also added validate_windows_installer.py to NEEDS_PLATFORM=['win32'] for the same reason.
- Verified: WSL Linux sweep: validate_cpp_tls_client.py + validate_windows_installer.py both emit SKIP_PLATFORM (linux not in ['win32']) and count toward 'skipped' rather than 'failed'. Windows sweep: 68 passed | 0 failed | 4 SKIP_EXTERNAL — unchanged (NEEDS_PLATFORM gate doesn't fire on win32 for win32-required validators). The unrelated WSL-only validate_desktop_smoke.py attachment-save failure was confirmed pre-existing and not in scope (GitHub linux-validators correctly SKIPs it via NEEDS_BINARY because Qt isn't installed there).
- Next: Push the four release-readiness commits (M115-M117 + M118 + M119). Optional follow-up: investigate the WSL desktop_smoke attachment-save failure (Linux-specific path / permission); not on the CI critical path.
- Covers: REQ-VALIDATION

