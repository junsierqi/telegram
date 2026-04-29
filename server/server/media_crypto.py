"""AES-256-GCM wrap for media-plane payloads (D9 / M106).

Wire format of a sealed packet:

    [12-byte random nonce] || ciphertext || [16-byte GCM tag]

The key is base64-encoded externally so it can ride control-plane JSON
payloads without binary escaping. Nonce is fresh per packet — never reuse a
(key, nonce) pair, hence `os.urandom(12)`.

This module is a thin facade over `cryptography.hazmat.primitives.ciphers.aead.AESGCM`
so callers don't need to know the layout.
"""
from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


NONCE_LEN = 12   # AESGCM standard nonce length
KEY_BITS = 256   # AES-256
TAG_LEN = 16     # AES-GCM tag length


def generate_key_b64() -> str:
    """Generate a fresh AES-256 key and return it base64-encoded."""
    return base64.b64encode(AESGCM.generate_key(bit_length=KEY_BITS)).decode("ascii")


def encrypt(key_b64: str, plaintext: bytes, *, associated_data: bytes | None = None) -> bytes:
    key = base64.b64decode(key_b64.encode("ascii"))
    nonce = os.urandom(NONCE_LEN)
    aead = AESGCM(key)
    return nonce + aead.encrypt(nonce, plaintext, associated_data)


def decrypt(
    key_b64: str, sealed: bytes, *, associated_data: bytes | None = None
) -> bytes | None:
    """Return the recovered plaintext, or None if the packet is malformed
    or the tag fails — callers treat None as "drop silently".
    """
    if len(sealed) < NONCE_LEN + TAG_LEN:
        return None
    try:
        key = base64.b64decode(key_b64.encode("ascii"))
    except Exception:
        return None
    nonce = sealed[:NONCE_LEN]
    aead = AESGCM(key)
    try:
        return aead.decrypt(nonce, sealed[NONCE_LEN:], associated_data)
    except Exception:
        return None
