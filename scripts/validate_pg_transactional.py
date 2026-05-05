"""M129 PostgreSQL per-entity transactional repository static check.

Live PG round-trips live behind PA-001 (already resolved on the dev host).
This validator inspects server/server/repositories.py to assert that:

- upsert_user / upsert_session / delete_session / upsert_remote_session
  exist on PostgresStateRepository.
- Each upsert uses INSERT ... ON CONFLICT ... DO UPDATE (so callers can
  call them without a separate "exists?" round-trip).
- The remote_sessions schema includes relay_key_b64 + has an idempotent
  ALTER TABLE ... ADD COLUMN IF NOT EXISTS migration matching M106's
  SQLite path.
- Each per-entity method opens its own self._connect() context so writes
  land in their own short transaction and don't share a snapshot lock
  with the legacy save() path.
- Legacy save() is preserved (no regression for callers that still use it).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REPOSITORIES = REPO / "server" / "server" / "repositories.py"
STATE = REPO / "server" / "server" / "state.py"
AUTH = REPO / "server" / "server" / "services" / "auth.py"
REMOTE = REPO / "server" / "server" / "services" / "remote_session.py"


def scenario(label: str) -> None:
    print(f"\n[scenario] {label}")


def run_methods_present():
    scenario("upsert_user / upsert_session / delete_session / upsert_remote_session exist")
    text = REPOSITORIES.read_text(encoding="utf-8")
    for needle in (
        "def upsert_user(self, record:",
        "def upsert_session(self, record:",
        "def delete_session(self, session_id:",
        "def upsert_remote_session(self, record:",
        "def save(self, payload:",  # legacy preserved
    ):
        assert needle in text, f"missing: {needle}"


def run_upserts_use_on_conflict():
    scenario("Each upsert uses ON CONFLICT ... DO UPDATE (idempotent)")
    text = REPOSITORIES.read_text(encoding="utf-8")
    for marker in (
        "ON CONFLICT (user_id) DO UPDATE",
        "ON CONFLICT (session_id) DO UPDATE",
        "ON CONFLICT (remote_session_id) DO UPDATE",
    ):
        assert marker in text, f"missing ON CONFLICT clause: {marker}"


def run_each_method_opens_own_transaction():
    scenario("Each per-entity method opens its own self._connect() context")
    text = REPOSITORIES.read_text(encoding="utf-8")
    # Slice each method body and require a `with self._connect()` inside.
    for name in ("upsert_user", "upsert_session", "delete_session", "upsert_remote_session"):
        pattern = re.compile(
            rf"def {name}\([^)]*\)[^:]*:\s*(?P<body>(?:\s+.+\n)+?)(?=\n(?:    def |\Z))",
            re.MULTILINE,
        )
        m = pattern.search(text)
        assert m is not None, f"could not parse {name} body"
        body = m.group("body")
        assert "with self._connect() as conn" in body, (
            f"{name} must open its own connection (own transaction)",
        )


def run_remote_sessions_schema_has_relay_key():
    scenario("remote_sessions CREATE TABLE includes relay_key_b64 + ALTER TABLE migration")
    text = REPOSITORIES.read_text(encoding="utf-8")
    assert "relay_key_b64 TEXT NOT NULL DEFAULT ''" in text, \
        "CREATE TABLE missing relay_key_b64"
    assert "ALTER TABLE remote_sessions" in text, "missing migration"
    assert "ADD COLUMN IF NOT EXISTS relay_key_b64" in text, \
        "migration must be idempotent (IF NOT EXISTS)"


def run_state_exposes_focused_persistence_helpers():
    scenario("InMemoryState exposes focused persistence helpers")
    text = STATE.read_text(encoding="utf-8")
    for needle in (
        "def persist_session(self, record: SessionRecord)",
        "self._pg_repository.upsert_session(asdict(record))",
        "def delete_session(self, session_id: str)",
        "self._pg_repository.delete_session(session_id)",
        "def persist_remote_session(self, record: RemoteSessionRecord)",
        "self._pg_repository.upsert_remote_session(asdict(record))",
    ):
        assert needle in text, f"missing focused state helper: {needle}"


def run_services_use_focused_persistence_where_available():
    scenario("Auth and remote-session services use focused PG writes where available")
    auth = AUTH.read_text(encoding="utf-8")
    remote = REMOTE.read_text(encoding="utf-8")
    assert "self._state.persist_session(self._state.sessions[session_id])" in auth, \
        "login should persist existing-device sessions through upsert_session"
    assert "existing_device is None" in auth and "self._state.save_runtime_state()" in auth, \
        "login must keep snapshot fallback for new-device writes"
    assert "save_runtime_state()" not in remote, \
        "remote_session.py should not use snapshot saves after per-entity helper wiring"
    assert remote.count("persist_remote_session(record)") >= 7, \
        "all remote-session state transitions should call persist_remote_session"


def main() -> int:
    scenarios = [
        run_methods_present,
        run_upserts_use_on_conflict,
        run_each_method_opens_own_transaction,
        run_remote_sessions_schema_has_relay_key,
        run_state_exposes_focused_persistence_helpers,
        run_services_use_focused_persistence_where_available,
    ]
    for fn in scenarios:
        fn()
    print(f"\nAll {len(scenarios)} scenarios passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
