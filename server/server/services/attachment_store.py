from __future__ import annotations

import re
from pathlib import Path


class AttachmentBlobStore:
    """Filesystem-backed attachment content store.

    The control plane still accepts/returns base64 for now, but durable runtime
    state stores only metadata plus a blob key. This boundary is intentionally
    small so it can later be replaced by object storage without changing
    ChatService's validation or protocol handling.
    """

    _SAFE_KEY = re.compile(r"^[A-Za-z0-9_.-]+$")

    def __init__(self, root_dir: str | Path | None) -> None:
        self._root_dir = Path(root_dir).resolve() if root_dir else None

    @property
    def enabled(self) -> bool:
        return self._root_dir is not None

    def put(self, attachment_id: str, content: bytes) -> str:
        if self._root_dir is None:
            return ""
        key = f"{attachment_id}.bin"
        self._validate_key(key)
        self._root_dir.mkdir(parents=True, exist_ok=True)
        (self._root_dir / key).write_bytes(content)
        return key

    def get(self, key: str) -> bytes:
        self._validate_key(key)
        if self._root_dir is None:
            raise FileNotFoundError(key)
        path = (self._root_dir / key).resolve()
        if not path.is_relative_to(self._root_dir):
            raise FileNotFoundError(key)
        return path.read_bytes()

    def _validate_key(self, key: str) -> None:
        if not key or not self._SAFE_KEY.match(key):
            raise FileNotFoundError(key)
