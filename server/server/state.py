from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .crypto import hash_password
from .repositories import PostgresStateRepository


class _ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        try:
            super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()
        return False


@dataclass(slots=True)
class UserRecord:
    user_id: str
    username: str
    password_hash: str
    display_name: str
    # M94: TOTP 2FA. Empty string = 2FA disabled. When set, login requires
    # `two_fa_code` to satisfy the time-based 6-digit code derived from
    # this base32-encoded secret (RFC 6238). Persisted alongside the user
    # so password + secret travel together.
    two_fa_secret: str = ""
    # M101: profile avatar. Empty string = default/no avatar. The actual
    # bytes live in the chunked-upload attachment store; this field just
    # points at whichever attachment the user picked. Clients fetch
    # bytes via the existing ATTACHMENT_FETCH RPC.
    avatar_attachment_id: str = ""


@dataclass(slots=True)
class DeviceRecord:
    device_id: str
    user_id: str
    label: str
    platform: str
    trusted: bool = True
    active: bool = True
    can_host: bool = True
    can_view: bool = True


@dataclass(slots=True)
class SessionRecord:
    session_id: str
    user_id: str
    device_id: str
    last_seen_at: float = 0.0


@dataclass(slots=True)
class ConversationRecord:
    conversation_id: str
    participant_user_ids: list[str] = field(default_factory=list)
    messages: list[dict[str, str]] = field(default_factory=list)
    title: str = ""
    read_markers: dict[str, str] = field(default_factory=dict)
    change_seq: int = 0
    changes: list[dict[str, object]] = field(default_factory=list)
    # M101: group avatar. Empty string = no custom avatar. Same model as
    # UserRecord.avatar_attachment_id — points at chunk-uploaded bytes.
    avatar_attachment_id: str = ""
    # M103: per-conversation roles. user_id -> "owner"|"admin"|"member".
    # The creator is the sole owner. Owners may promote/demote anyone;
    # admins may add/remove members but not other admins. Missing entries
    # default to "member" for backwards compatibility with old
    # conversations created before M103 (and seeded fixtures).
    roles: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class RemoteSessionRecord:
    remote_session_id: str
    requester_user_id: str
    requester_device_id: str
    target_user_id: str
    target_device_id: str
    state: str
    relay_endpoint: str = ""
    relay_region: str = ""


@dataclass(slots=True)
class AttachmentRecord:
    attachment_id: str
    conversation_id: str
    uploader_user_id: str
    filename: str
    mime_type: str
    size_bytes: int
    content_b64: str = ""
    storage_key: str = ""


@dataclass(slots=True)
class BlockedUserEntry:
    """M98: blocker_user_id put target_user_id on their block list at this
    timestamp. Stored as a flat list rather than a set so iteration order
    and JSON round-trip are deterministic."""
    target_user_id: str
    blocked_at_ms: int


@dataclass(slots=True)
class ConversationMuteEntry:
    """M98: per-(user, conversation) mute state.
       muted_until_ms == 0  -> not muted
       muted_until_ms == -1 -> muted forever (until explicit unmute)
       muted_until_ms == N  -> muted until wall-clock ms epoch N
    """
    user_id: str
    conversation_id: str
    muted_until_ms: int


@dataclass(slots=True)
class DraftRecord:
    """M99: per-(user, conversation) unsent message text. Updated on every
    DRAFT_SAVE; cleared on DRAFT_CLEAR or when the user sends the message
    via MESSAGE_SEND."""
    user_id: str
    conversation_id: str
    text: str
    reply_to_message_id: str
    updated_at_ms: int


@dataclass(slots=True)
class PushTokenRecord:
    """Mobile push registration: maps (user_id, device_id) to a platform-issued
    token (FCM/APNs/WNS). The server uses these to wake mobile clients when
    their TCP control plane is offline. Persisted in-memory for now; future
    work can add SQLite/Postgres rows alongside SessionRecord."""
    user_id: str
    device_id: str
    platform: str
    token: str
    registered_at_ms: int = 0


class InMemoryState:
    def __init__(
        self,
        state_file: str | None = None,
        db_file: str | None = None,
        pg_dsn: str | None = None,
    ) -> None:
        self._state_file = Path(state_file).resolve() if state_file else None
        self._db_file = Path(db_file).resolve() if db_file else None
        self._pg_repository = PostgresStateRepository(pg_dsn) if pg_dsn else None
        self.users: dict[str, UserRecord] = {
            "u_alice": UserRecord(
                user_id="u_alice",
                username="alice",
                password_hash=hash_password("alice_pw"),
                display_name="Alice",
            ),
            "u_bob": UserRecord(
                user_id="u_bob",
                username="bob",
                password_hash=hash_password("bob_pw"),
                display_name="Bob",
            ),
        }
        self.devices: dict[str, DeviceRecord] = {
            "dev_alice_win": DeviceRecord(
                device_id="dev_alice_win",
                user_id="u_alice",
                label="Alice Desktop",
                platform="windows",
            ),
            "dev_bob_win": DeviceRecord(
                device_id="dev_bob_win",
                user_id="u_bob",
                label="Bob Desktop",
                platform="windows",
            ),
        }
        self.sessions: dict[str, SessionRecord] = {}
        self.conversations: dict[str, ConversationRecord] = {
            "conv_alice_bob": ConversationRecord(
                conversation_id="conv_alice_bob",
                participant_user_ids=["u_alice", "u_bob"],
                messages=[
                    {
                        "message_id": "msg_1",
                        "sender_user_id": "u_alice",
                        "text": "hello from alice",
                    }
                ],
            )
        }
        self.remote_sessions: dict[str, RemoteSessionRecord] = {}
        self.contacts: dict[str, list[str]] = {}
        self.attachments: dict[str, AttachmentRecord] = {}
        # Push tokens are kept in a flat list because (user_id, device_id) can
        # have multiple tokens (e.g., FCM rotates tokens) and we want fan-out
        # to be O(N) anyway. Not persisted to JSON/SQLite/PG yet — see M84
        # checkpoint and PA-008 in 08-atlas-task-library.md.
        self.push_tokens: list[PushTokenRecord] = []
        # M98: per-(blocker, target) block list + per-(user, conversation)
        # mute state. Held in-memory; serialised to disk only when JSON
        # state-file is enabled (covered by save_runtime_state's defensive
        # JSON path); SQLite/PG persistence can come later.
        self.blocked_users: dict[str, list[BlockedUserEntry]] = {}
        self.conversation_mutes: dict[tuple[str, str], ConversationMuteEntry] = {}
        # M99: per-(user, conversation) drafts.
        self.drafts: dict[tuple[str, str], DraftRecord] = {}
        # M100: per-user pinned/archived flag sets keyed by user_id.
        # Held as set[str] of conversation_ids — sets give O(1) toggle
        # and natural dedup. Per-user, so bob pinning conv_alice_bob
        # does NOT pin alice's view of the same conversation.
        self.pinned_conversations: dict[str, set[str]] = {}
        self.archived_conversations: dict[str, set[str]] = {}
        self._load_runtime_state()

    @property
    def state_file(self) -> Path | None:
        return self._state_file

    @property
    def db_file(self) -> Path | None:
        return self._db_file

    def save_runtime_state(self) -> None:
        if self._pg_repository is not None:
            self._pg_repository.save(self._runtime_payload())
            return
        if self._db_file is not None:
            self._save_sqlite_state()
            return
        if self._state_file is None:
            return
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        self._state_file.write_text(json.dumps(self._runtime_payload(), indent=2) + "\n", encoding="utf-8")

    def _runtime_payload(self) -> dict:
        return {
            "users": [asdict(user) for user in self.users.values()],
            "devices": [asdict(device) for device in self.devices.values()],
            "conversations": [asdict(conversation) for conversation in self.conversations.values()],
            "remote_sessions": [asdict(session) for session in self.remote_sessions.values()],
            "sessions": [asdict(session) for session in self.sessions.values()],
            "contacts": {owner: list(targets) for owner, targets in self.contacts.items()},
            "attachments": [asdict(att) for att in self.attachments.values()],
        }

    def _load_runtime_state(self) -> None:
        if self._pg_repository is not None:
            payload = self._pg_repository.load()
            if payload is not None:
                self._apply_payload(payload)
            return
        if self._db_file is not None:
            self._load_sqlite_state()
            return
        if self._state_file is None or not self._state_file.exists():
            return

        raw = self._state_file.read_text(encoding="utf-8")
        if not raw.strip():
            return

        self._apply_payload(json.loads(raw))

    def _apply_payload(self, payload: dict) -> None:
        users = payload.get("users", [])
        if users:
            self.users = {
                entry["user_id"]: UserRecord(
                    user_id=entry["user_id"],
                    username=entry["username"],
                    password_hash=entry.get("password_hash")
                    or hash_password(entry["password"]),
                    display_name=entry["display_name"],
                )
                for entry in users
            }

        devices = payload.get("devices", [])
        if devices:
            self.devices = {
                entry["device_id"]: DeviceRecord(
                    device_id=entry["device_id"],
                    user_id=entry["user_id"],
                    label=entry.get("label", ""),
                    platform=entry.get("platform", "unknown"),
                    trusted=bool(entry.get("trusted", True)),
                    active=bool(entry.get("active", True)),
                    can_host=bool(entry.get("can_host", True)),
                    can_view=bool(entry.get("can_view", True)),
                )
                for entry in devices
            }

        conversations = payload.get("conversations", [])
        if conversations:
            self.conversations = {
                entry["conversation_id"]: ConversationRecord(
                    conversation_id=entry["conversation_id"],
                    participant_user_ids=list(entry.get("participant_user_ids", [])),
                    messages=[
                        dict(message) for message in entry.get("messages", [])
                    ],
                    title=entry.get("title", ""),
                    read_markers=dict(entry.get("read_markers", {})),
                    change_seq=int(entry.get("change_seq", 0)),
                    changes=[dict(change) for change in entry.get("changes", [])],
                )
                for entry in conversations
            }

        remote_sessions = payload.get("remote_sessions", [])
        if remote_sessions:
            self.remote_sessions = {
                entry["remote_session_id"]: RemoteSessionRecord(
                    remote_session_id=entry["remote_session_id"],
                    requester_user_id=entry["requester_user_id"],
                    requester_device_id=entry["requester_device_id"],
                    target_user_id=entry["target_user_id"],
                    target_device_id=entry["target_device_id"],
                    state=entry["state"],
                    relay_endpoint=entry.get("relay_endpoint", ""),
                    relay_region=entry.get("relay_region", ""),
                )
                for entry in remote_sessions
            }

        sessions = payload.get("sessions", [])
        if sessions:
            self.sessions = {
                entry["session_id"]: SessionRecord(
                    session_id=entry["session_id"],
                    user_id=entry["user_id"],
                    device_id=entry["device_id"],
                    last_seen_at=float(entry.get("last_seen_at", 0.0)),
                )
                for entry in sessions
            }

        contacts = payload.get("contacts", {})
        if contacts:
            self.contacts = {
                owner: [str(t) for t in targets]
                for owner, targets in contacts.items()
            }

        attachments = payload.get("attachments", [])
        if attachments:
            self.attachments = {
                entry["attachment_id"]: AttachmentRecord(
                    attachment_id=entry["attachment_id"],
                    conversation_id=entry["conversation_id"],
                    uploader_user_id=entry["uploader_user_id"],
                    filename=entry["filename"],
                    mime_type=entry["mime_type"],
                    size_bytes=int(entry["size_bytes"]),
                    content_b64=entry.get("content_b64", ""),
                    storage_key=entry.get("storage_key", ""),
                )
                for entry in attachments
            }

    def sessions_for_user(self, user_id: str) -> list[SessionRecord]:
        return [session for session in self.sessions.values() if session.user_id == user_id]

    def _connect_sqlite(self) -> sqlite3.Connection:
        if self._db_file is None:
            raise RuntimeError("db_file is not configured")
        self._db_file.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_file), factory=_ClosingConnection)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _ensure_sqlite_schema(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
              user_id TEXT PRIMARY KEY,
              username TEXT NOT NULL,
              password_hash TEXT NOT NULL,
              display_name TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS devices (
              device_id TEXT PRIMARY KEY,
              user_id TEXT NOT NULL,
              label TEXT NOT NULL,
              platform TEXT NOT NULL,
              trusted INTEGER NOT NULL,
              active INTEGER NOT NULL,
              can_host INTEGER NOT NULL,
              can_view INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
              session_id TEXT PRIMARY KEY,
              user_id TEXT NOT NULL,
              device_id TEXT NOT NULL,
              last_seen_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS conversations (
              conversation_id TEXT PRIMARY KEY,
              participant_user_ids_json TEXT NOT NULL,
              messages_json TEXT NOT NULL,
              title TEXT NOT NULL,
              read_markers_json TEXT NOT NULL,
              change_seq INTEGER NOT NULL DEFAULT 0,
              changes_json TEXT NOT NULL DEFAULT '[]'
            );
            CREATE TABLE IF NOT EXISTS remote_sessions (
              remote_session_id TEXT PRIMARY KEY,
              requester_user_id TEXT NOT NULL,
              requester_device_id TEXT NOT NULL,
              target_user_id TEXT NOT NULL,
              target_device_id TEXT NOT NULL,
              state TEXT NOT NULL,
              relay_endpoint TEXT NOT NULL,
              relay_region TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS contacts (
              owner_user_id TEXT NOT NULL,
              target_user_id TEXT NOT NULL,
              PRIMARY KEY (owner_user_id, target_user_id)
            );
            CREATE TABLE IF NOT EXISTS attachments (
              attachment_id TEXT PRIMARY KEY,
              conversation_id TEXT NOT NULL,
              uploader_user_id TEXT NOT NULL,
              filename TEXT NOT NULL,
              mime_type TEXT NOT NULL,
              size_bytes INTEGER NOT NULL,
              content_b64 TEXT NOT NULL,
              storage_key TEXT NOT NULL
            );
            """
        )
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(conversations)").fetchall()
        }
        if "change_seq" not in columns:
            conn.execute("ALTER TABLE conversations ADD COLUMN change_seq INTEGER NOT NULL DEFAULT 0")
        if "changes_json" not in columns:
            conn.execute("ALTER TABLE conversations ADD COLUMN changes_json TEXT NOT NULL DEFAULT '[]'")

    def _save_sqlite_state(self) -> None:
        with self._connect_sqlite() as conn:
            self._ensure_sqlite_schema(conn)
            conn.executescript(
                """
                DELETE FROM users;
                DELETE FROM devices;
                DELETE FROM sessions;
                DELETE FROM conversations;
                DELETE FROM remote_sessions;
                DELETE FROM contacts;
                DELETE FROM attachments;
                """
            )
            conn.executemany(
                "INSERT INTO users (user_id, username, password_hash, display_name) VALUES (?, ?, ?, ?)",
                [(u.user_id, u.username, u.password_hash, u.display_name) for u in self.users.values()],
            )
            conn.executemany(
                """
                INSERT INTO devices
                (device_id, user_id, label, platform, trusted, active, can_host, can_view)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        d.device_id,
                        d.user_id,
                        d.label,
                        d.platform,
                        int(d.trusted),
                        int(d.active),
                        int(d.can_host),
                        int(d.can_view),
                    )
                    for d in self.devices.values()
                ],
            )
            conn.executemany(
                "INSERT INTO sessions (session_id, user_id, device_id, last_seen_at) VALUES (?, ?, ?, ?)",
                [(s.session_id, s.user_id, s.device_id, s.last_seen_at) for s in self.sessions.values()],
            )
            conn.executemany(
                """
                INSERT INTO conversations
                (conversation_id, participant_user_ids_json, messages_json, title, read_markers_json,
                 change_seq, changes_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        c.conversation_id,
                        json.dumps(c.participant_user_ids),
                        json.dumps(c.messages),
                        c.title,
                        json.dumps(c.read_markers),
                        c.change_seq,
                        json.dumps(c.changes),
                    )
                    for c in self.conversations.values()
                ],
            )
            conn.executemany(
                """
                INSERT INTO remote_sessions
                (remote_session_id, requester_user_id, requester_device_id, target_user_id,
                 target_device_id, state, relay_endpoint, relay_region)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        r.remote_session_id,
                        r.requester_user_id,
                        r.requester_device_id,
                        r.target_user_id,
                        r.target_device_id,
                        r.state,
                        r.relay_endpoint,
                        r.relay_region,
                    )
                    for r in self.remote_sessions.values()
                ],
            )
            conn.executemany(
                "INSERT INTO contacts (owner_user_id, target_user_id) VALUES (?, ?)",
                [(owner, target) for owner, targets in self.contacts.items() for target in targets],
            )
            conn.executemany(
                """
                INSERT INTO attachments
                (attachment_id, conversation_id, uploader_user_id, filename, mime_type,
                 size_bytes, content_b64, storage_key)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        a.attachment_id,
                        a.conversation_id,
                        a.uploader_user_id,
                        a.filename,
                        a.mime_type,
                        a.size_bytes,
                        a.content_b64,
                        a.storage_key,
                    )
                    for a in self.attachments.values()
                ],
            )

    def _load_sqlite_state(self) -> None:
        if self._db_file is None or not self._db_file.exists():
            return
        with self._connect_sqlite() as conn:
            self._ensure_sqlite_schema(conn)
            user_rows = conn.execute(
                "SELECT user_id, username, password_hash, display_name FROM users"
            ).fetchall()
            if not user_rows:
                return

            payload = {
                "users": [
                    {
                        "user_id": row[0],
                        "username": row[1],
                        "password_hash": row[2],
                        "display_name": row[3],
                    }
                    for row in user_rows
                ],
                "devices": [
                    {
                        "device_id": row[0],
                        "user_id": row[1],
                        "label": row[2],
                        "platform": row[3],
                        "trusted": bool(row[4]),
                        "active": bool(row[5]),
                        "can_host": bool(row[6]),
                        "can_view": bool(row[7]),
                    }
                    for row in conn.execute(
                        "SELECT device_id, user_id, label, platform, trusted, active, can_host, can_view FROM devices"
                    ).fetchall()
                ],
                "sessions": [
                    {
                        "session_id": row[0],
                        "user_id": row[1],
                        "device_id": row[2],
                        "last_seen_at": row[3],
                    }
                    for row in conn.execute(
                        "SELECT session_id, user_id, device_id, last_seen_at FROM sessions"
                    ).fetchall()
                ],
                "conversations": [
                    {
                        "conversation_id": row[0],
                        "participant_user_ids": json.loads(row[1]),
                        "messages": json.loads(row[2]),
                        "title": row[3],
                        "read_markers": json.loads(row[4]),
                        "change_seq": row[5],
                        "changes": json.loads(row[6]),
                    }
                    for row in conn.execute(
                        """
                        SELECT conversation_id, participant_user_ids_json, messages_json,
                               title, read_markers_json, change_seq, changes_json
                        FROM conversations
                        """
                    ).fetchall()
                ],
                "remote_sessions": [
                    {
                        "remote_session_id": row[0],
                        "requester_user_id": row[1],
                        "requester_device_id": row[2],
                        "target_user_id": row[3],
                        "target_device_id": row[4],
                        "state": row[5],
                        "relay_endpoint": row[6],
                        "relay_region": row[7],
                    }
                    for row in conn.execute(
                        """
                        SELECT remote_session_id, requester_user_id, requester_device_id,
                               target_user_id, target_device_id, state, relay_endpoint, relay_region
                        FROM remote_sessions
                        """
                    ).fetchall()
                ],
                "contacts": {},
                "attachments": [
                    {
                        "attachment_id": row[0],
                        "conversation_id": row[1],
                        "uploader_user_id": row[2],
                        "filename": row[3],
                        "mime_type": row[4],
                        "size_bytes": row[5],
                        "content_b64": row[6],
                        "storage_key": row[7],
                    }
                    for row in conn.execute(
                        """
                        SELECT attachment_id, conversation_id, uploader_user_id, filename,
                               mime_type, size_bytes, content_b64, storage_key
                        FROM attachments
                        """
                    ).fetchall()
                ],
            }
            contacts: dict[str, list[str]] = {}
            for owner, target in conn.execute(
                "SELECT owner_user_id, target_user_id FROM contacts ORDER BY owner_user_id, target_user_id"
            ).fetchall():
                contacts.setdefault(owner, []).append(target)
            payload["contacts"] = contacts
            self._apply_payload(payload)
