"""Stdlib-only password hashing (F2).

Format: ``pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>``

Uses ``hashlib.pbkdf2_hmac`` + ``os.urandom`` for the salt and
``hmac.compare_digest`` for constant-time comparison. No third-party crypto
dependency — intentional per user direction to skip external crypto libs.
"""
from __future__ import annotations

import hashlib
import hmac
import os

ALGORITHM = "pbkdf2_sha256"
DEFAULT_ITERATIONS = 120_000
SALT_BYTES = 16
DERIVED_BYTES = 32


def hash_password(plaintext: str, *, iterations: int = DEFAULT_ITERATIONS) -> str:
    if not isinstance(plaintext, str):
        raise TypeError("password must be a string")
    salt = os.urandom(SALT_BYTES)
    derived = hashlib.pbkdf2_hmac(
        "sha256", plaintext.encode("utf-8"), salt, iterations, dklen=DERIVED_BYTES
    )
    return f"{ALGORITHM}${iterations}${salt.hex()}${derived.hex()}"


def verify_password(plaintext: str, stored: str) -> bool:
    if not isinstance(stored, str) or not stored:
        return False
    try:
        algorithm, iteration_str, salt_hex, derived_hex = stored.split("$", 3)
    except ValueError:
        return False
    if algorithm != ALGORITHM:
        return False
    try:
        iterations = int(iteration_str)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(derived_hex)
    except ValueError:
        return False
    candidate = hashlib.pbkdf2_hmac(
        "sha256", plaintext.encode("utf-8"), salt, iterations, dklen=len(expected)
    )
    return hmac.compare_digest(candidate, expected)
