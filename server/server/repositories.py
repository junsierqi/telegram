from __future__ import annotations

import json
from typing import Any

POSTGRES_SCHEMA_VERSION = 3


class PostgresStateRepository:
    """PostgreSQL persistence boundary for the first production repository slice.

    Users, devices, sessions, conversations, messages, change logs, contacts,
    attachments and remote sessions are normalized so they can move toward real
    service repositories incrementally.
    """

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def _connect(self):
        try:
            import psycopg  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "PostgreSQL persistence requires the optional psycopg package. "
                "Install psycopg[binary] or use --db-file for SQLite."
            ) from exc
        return psycopg.connect(self._dsn)

    def ensure_schema(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS schema_migrations (
                      version INTEGER PRIMARY KEY,
                      description TEXT NOT NULL,
                      applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS users (
                      user_id TEXT PRIMARY KEY,
                      username TEXT NOT NULL UNIQUE,
                      password_hash TEXT NOT NULL,
                      display_name TEXT NOT NULL
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS devices (
                      device_id TEXT PRIMARY KEY,
                      user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                      label TEXT NOT NULL,
                      platform TEXT NOT NULL,
                      trusted BOOLEAN NOT NULL,
                      active BOOLEAN NOT NULL,
                      can_host BOOLEAN NOT NULL,
                      can_view BOOLEAN NOT NULL
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS sessions (
                      session_id TEXT PRIMARY KEY,
                      user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                      device_id TEXT NOT NULL REFERENCES devices(device_id) ON DELETE CASCADE,
                      last_seen_at DOUBLE PRECISION NOT NULL
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS conversations (
                      conversation_id TEXT PRIMARY KEY,
                      title TEXT NOT NULL,
                      participant_user_ids JSONB NOT NULL,
                      read_markers JSONB NOT NULL,
                      change_seq INTEGER NOT NULL
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS conversation_messages (
                      conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id) ON DELETE CASCADE,
                      message_index INTEGER NOT NULL,
                      message_id TEXT NOT NULL,
                      payload JSONB NOT NULL,
                      PRIMARY KEY (conversation_id, message_id),
                      UNIQUE (conversation_id, message_index)
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_conversation_messages_order
                    ON conversation_messages (conversation_id, message_index)
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS conversation_changes (
                      conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id) ON DELETE CASCADE,
                      change_index INTEGER NOT NULL,
                      version INTEGER NOT NULL,
                      payload JSONB NOT NULL,
                      PRIMARY KEY (conversation_id, change_index)
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_conversation_changes_version
                    ON conversation_changes (conversation_id, version)
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS contacts (
                      owner_user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                      target_user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                      PRIMARY KEY (owner_user_id, target_user_id)
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS attachments (
                      attachment_id TEXT PRIMARY KEY,
                      conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id) ON DELETE CASCADE,
                      uploader_user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                      filename TEXT NOT NULL,
                      mime_type TEXT NOT NULL,
                      size_bytes INTEGER NOT NULL,
                      content_b64 TEXT NOT NULL,
                      storage_key TEXT NOT NULL
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS remote_sessions (
                      remote_session_id TEXT PRIMARY KEY,
                      requester_user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                      requester_device_id TEXT NOT NULL REFERENCES devices(device_id) ON DELETE CASCADE,
                      target_user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                      target_device_id TEXT NOT NULL REFERENCES devices(device_id) ON DELETE CASCADE,
                      state TEXT NOT NULL,
                      relay_endpoint TEXT NOT NULL,
                      relay_region TEXT NOT NULL
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS runtime_snapshots (
                      snapshot_key TEXT PRIMARY KEY,
                      payload JSONB NOT NULL
                    )
                    """
                )
                cur.execute(
                    """
                    INSERT INTO schema_migrations (version, description)
                    VALUES (%s, %s)
                    ON CONFLICT (version) DO NOTHING
                    """,
                    (
                        POSTGRES_SCHEMA_VERSION,
                        "normalized runtime domain repository",
                    ),
                )

    def schema_version(self) -> int:
        self.ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COALESCE(MAX(version), 0) FROM schema_migrations")
                row = cur.fetchone()
                return int(row[0] if row else 0)

    def save(self, payload: dict[str, Any]) -> None:
        self.ensure_schema()
        rest_payload: dict[str, Any] = {}
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM remote_sessions")
                cur.execute("DELETE FROM attachments")
                cur.execute("DELETE FROM contacts")
                cur.execute("DELETE FROM sessions")
                cur.execute("DELETE FROM devices")
                cur.execute("DELETE FROM users")
                cur.execute("DELETE FROM conversation_changes")
                cur.execute("DELETE FROM conversation_messages")
                cur.execute("DELETE FROM conversations")
                cur.executemany(
                    """
                    INSERT INTO users (user_id, username, password_hash, display_name)
                    VALUES (%s, %s, %s, %s)
                    """,
                    [
                        (u["user_id"], u["username"], u["password_hash"], u["display_name"])
                        for u in payload.get("users", [])
                    ],
                )
                cur.executemany(
                    """
                    INSERT INTO devices
                    (device_id, user_id, label, platform, trusted, active, can_host, can_view)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    [
                        (
                            d["device_id"],
                            d["user_id"],
                            d.get("label", ""),
                            d.get("platform", "unknown"),
                            bool(d.get("trusted", True)),
                            bool(d.get("active", True)),
                            bool(d.get("can_host", True)),
                            bool(d.get("can_view", True)),
                        )
                        for d in payload.get("devices", [])
                    ],
                )
                cur.executemany(
                    """
                    INSERT INTO sessions (session_id, user_id, device_id, last_seen_at)
                    VALUES (%s, %s, %s, %s)
                    """,
                    [
                        (
                            s["session_id"],
                            s["user_id"],
                            s["device_id"],
                            float(s.get("last_seen_at", 0.0)),
                        )
                        for s in payload.get("sessions", [])
                    ],
                )
                conversations = payload.get("conversations", [])
                cur.executemany(
                    """
                    INSERT INTO conversations
                    (conversation_id, title, participant_user_ids, read_markers, change_seq)
                    VALUES (%s, %s, %s::jsonb, %s::jsonb, %s)
                    """,
                    [
                        (
                            c["conversation_id"],
                            c.get("title", ""),
                            json.dumps(c.get("participant_user_ids", [])),
                            json.dumps(c.get("read_markers", {})),
                            int(c.get("change_seq", 0)),
                        )
                        for c in conversations
                    ],
                )
                cur.executemany(
                    """
                    INSERT INTO conversation_messages
                    (conversation_id, message_index, message_id, payload)
                    VALUES (%s, %s, %s, %s::jsonb)
                    """,
                    [
                        (
                            c["conversation_id"],
                            index,
                            str(message.get("message_id", "")),
                            json.dumps(message),
                        )
                        for c in conversations
                        for index, message in enumerate(c.get("messages", []))
                    ],
                )
                cur.executemany(
                    """
                    INSERT INTO conversation_changes
                    (conversation_id, change_index, version, payload)
                    VALUES (%s, %s, %s, %s::jsonb)
                    """,
                    [
                        (
                            c["conversation_id"],
                            index,
                            int(change.get("version", 0)),
                            json.dumps(change),
                        )
                        for c in conversations
                        for index, change in enumerate(c.get("changes", []))
                    ],
                )
                contacts = payload.get("contacts", {})
                cur.executemany(
                    """
                    INSERT INTO contacts (owner_user_id, target_user_id)
                    VALUES (%s, %s)
                    """,
                    [
                        (owner, target)
                        for owner, targets in contacts.items()
                        for target in targets
                    ],
                )
                cur.executemany(
                    """
                    INSERT INTO attachments
                    (attachment_id, conversation_id, uploader_user_id, filename, mime_type,
                     size_bytes, content_b64, storage_key)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    [
                        (
                            a["attachment_id"],
                            a["conversation_id"],
                            a["uploader_user_id"],
                            a.get("filename", ""),
                            a.get("mime_type", "application/octet-stream"),
                            int(a.get("size_bytes", 0)),
                            a.get("content_b64", ""),
                            a.get("storage_key", ""),
                        )
                        for a in payload.get("attachments", [])
                    ],
                )
                cur.executemany(
                    """
                    INSERT INTO remote_sessions
                    (remote_session_id, requester_user_id, requester_device_id, target_user_id,
                     target_device_id, state, relay_endpoint, relay_region)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    [
                        (
                            r["remote_session_id"],
                            r["requester_user_id"],
                            r["requester_device_id"],
                            r["target_user_id"],
                            r["target_device_id"],
                            r["state"],
                            r.get("relay_endpoint", ""),
                            r.get("relay_region", ""),
                        )
                        for r in payload.get("remote_sessions", [])
                    ],
                )
                cur.execute(
                    """
                    INSERT INTO runtime_snapshots (snapshot_key, payload)
                    VALUES ('main', %s::jsonb)
                    ON CONFLICT (snapshot_key)
                    DO UPDATE SET payload = EXCLUDED.payload
                    """,
                    (json.dumps(rest_payload),),
                )

    def load(self) -> dict[str, Any] | None:
        self.ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT user_id, username, password_hash, display_name FROM users")
                users = [
                    {
                        "user_id": row[0],
                        "username": row[1],
                        "password_hash": row[2],
                        "display_name": row[3],
                    }
                    for row in cur.fetchall()
                ]
                if not users:
                    return None
                cur.execute(
                    """
                    SELECT device_id, user_id, label, platform, trusted, active, can_host, can_view
                    FROM devices
                    """
                )
                devices = [
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
                    for row in cur.fetchall()
                ]
                cur.execute("SELECT session_id, user_id, device_id, last_seen_at FROM sessions")
                sessions = [
                    {
                        "session_id": row[0],
                        "user_id": row[1],
                        "device_id": row[2],
                        "last_seen_at": float(row[3]),
                    }
                    for row in cur.fetchall()
                ]
                cur.execute(
                    """
                    SELECT conversation_id, title, participant_user_ids, read_markers, change_seq
                    FROM conversations
                    ORDER BY conversation_id
                    """
                )
                conversations = []
                for row in cur.fetchall():
                    participant_user_ids = row[2]
                    if isinstance(participant_user_ids, str):
                        participant_user_ids = json.loads(participant_user_ids)
                    read_markers = row[3]
                    if isinstance(read_markers, str):
                        read_markers = json.loads(read_markers)
                    conversations.append(
                        {
                            "conversation_id": row[0],
                            "title": row[1],
                            "participant_user_ids": list(participant_user_ids),
                            "read_markers": dict(read_markers),
                            "change_seq": int(row[4]),
                            "messages": [],
                            "changes": [],
                        }
                    )
                conversations_by_id = {
                    conversation["conversation_id"]: conversation
                    for conversation in conversations
                }
                cur.execute(
                    """
                    SELECT conversation_id, payload
                    FROM conversation_messages
                    ORDER BY conversation_id, message_index
                    """
                )
                for conversation_id, message_payload in cur.fetchall():
                    if isinstance(message_payload, str):
                        message_payload = json.loads(message_payload)
                    if conversation_id in conversations_by_id:
                        conversations_by_id[conversation_id]["messages"].append(dict(message_payload))
                cur.execute(
                    """
                    SELECT conversation_id, payload
                    FROM conversation_changes
                    ORDER BY conversation_id, change_index
                    """
                )
                for conversation_id, change_payload in cur.fetchall():
                    if isinstance(change_payload, str):
                        change_payload = json.loads(change_payload)
                    if conversation_id in conversations_by_id:
                        conversations_by_id[conversation_id]["changes"].append(dict(change_payload))
                cur.execute("SELECT payload FROM runtime_snapshots WHERE snapshot_key = 'main'")
                snapshot_row = cur.fetchone()
                snapshot = snapshot_row[0] if snapshot_row else {}
                if isinstance(snapshot, str):
                    snapshot = json.loads(snapshot)
                if not conversations:
                    conversations = snapshot.get("conversations", [])
                cur.execute(
                    """
                    SELECT owner_user_id, target_user_id
                    FROM contacts
                    ORDER BY owner_user_id, target_user_id
                    """
                )
                contacts: dict[str, list[str]] = {}
                for owner, target in cur.fetchall():
                    contacts.setdefault(owner, []).append(target)
                if not contacts:
                    contacts = snapshot.get("contacts", {})
                cur.execute(
                    """
                    SELECT attachment_id, conversation_id, uploader_user_id, filename,
                           mime_type, size_bytes, content_b64, storage_key
                    FROM attachments
                    ORDER BY attachment_id
                    """
                )
                attachments = [
                    {
                        "attachment_id": row[0],
                        "conversation_id": row[1],
                        "uploader_user_id": row[2],
                        "filename": row[3],
                        "mime_type": row[4],
                        "size_bytes": int(row[5]),
                        "content_b64": row[6],
                        "storage_key": row[7],
                    }
                    for row in cur.fetchall()
                ]
                if not attachments:
                    attachments = snapshot.get("attachments", [])
                cur.execute(
                    """
                    SELECT remote_session_id, requester_user_id, requester_device_id,
                           target_user_id, target_device_id, state, relay_endpoint, relay_region
                    FROM remote_sessions
                    ORDER BY remote_session_id
                    """
                )
                remote_sessions = [
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
                    for row in cur.fetchall()
                ]
                if not remote_sessions:
                    remote_sessions = snapshot.get("remote_sessions", [])
                return {
                    "users": users,
                    "devices": devices,
                    "sessions": sessions,
                    "conversations": conversations,
                    "remote_sessions": remote_sessions,
                    "contacts": contacts,
                    "attachments": attachments,
                }
