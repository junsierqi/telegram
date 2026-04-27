from __future__ import annotations

import threading
from typing import Any, Callable


Writer = Callable[[dict[str, Any]], None]


class ConnectionRegistry:
    """Tracks which session_id maps to which live control-plane connection.

    Lets the dispatcher push unsolicited envelopes (message_deliver fan-out,
    presence updates, etc.) onto a specific session's socket. Writers are
    per-connection callables owned by the handler; the handler is responsible
    for serializing concurrent writes with its own lock.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._writers: dict[str, Writer] = {}

    def register(self, session_id: str, writer: Writer) -> None:
        if not session_id:
            return
        with self._lock:
            self._writers[session_id] = writer

    def unregister(self, session_id: str) -> None:
        if not session_id:
            return
        with self._lock:
            self._writers.pop(session_id, None)

    def push(self, session_id: str, message: dict[str, Any]) -> bool:
        with self._lock:
            writer = self._writers.get(session_id)
        if writer is None:
            return False
        try:
            writer(message)
            return True
        except Exception:
            with self._lock:
                self._writers.pop(session_id, None)
            return False

    def active_sessions(self) -> list[str]:
        with self._lock:
            return list(self._writers.keys())
