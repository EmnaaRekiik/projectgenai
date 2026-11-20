"""Argon2id hashing (passwords are never encrypted or stored in plaintext)."""
from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

# OWASP-aligned Argon2id parameters for the student project. Benchmark before production rollout.
_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2, hash_len=32, salt_len=16, type=Type.ID)
_DUMMY_HASH = _hasher.hash("nobody-has-this-password-17394")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def check_password(stored_hash: str | None, password: str) -> bool:
    # A dummy hash limits trivial username-enumeration timing differences.
    try:
        return _hasher.verify(stored_hash or _DUMMY_HASH, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
