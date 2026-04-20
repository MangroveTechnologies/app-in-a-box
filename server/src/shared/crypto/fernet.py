"""Master-key management + Fernet symmetric encryption for wallet secrets.

Master key resolution order (per spec):
    1. OS Keychain via `keyring` library (macOS Keychain, GNOME Keyring,
       Windows Credential Manager). Service name comes from config
       (KEYRING_SERVICE_NAME, default "defi-agent"). Username "master".
    2. Config value MASTER_KEY_ENV_FALLBACK — for environments without a
       keychain (CI, Docker with no keychain shim).
    3. If neither is set, generate a new Fernet key, store it in the
       keychain (if available), and use it.

Encryption format: Fernet (AES-128-CBC + HMAC-SHA256, URL-safe base64).
We store the ciphertext as a bytes BLOB in SQLite.

Tests use a test-only keychain service name and stub `keyring` where needed.
"""
from __future__ import annotations

from functools import lru_cache

import keyring
from cryptography.fernet import Fernet, InvalidToken

from src.config import app_config
from src.shared.errors import SigningError
from src.shared.logging import get_logger

_KEYRING_USER = "master"
_log = get_logger(__name__)


def _service_name() -> str:
    return str(app_config.KEYRING_SERVICE_NAME)


def _env_fallback() -> str:
    value = app_config.MASTER_KEY_ENV_FALLBACK
    return str(value) if value else ""


@lru_cache(maxsize=1)
def get_master_key() -> bytes:
    """Return the Fernet master key as bytes (urlsafe-base64 encoded).

    Idempotent: first call may generate + store the key; subsequent calls
    hit the lru_cache.
    """
    # 1. Try the OS keychain.
    try:
        existing = keyring.get_password(_service_name(), _KEYRING_USER)
        if existing:
            return existing.encode()
    except Exception as e:  # noqa: BLE001 - keychain backends raise various things
        _log.warning("crypto.keychain_unavailable", error=str(e))

    # 2. Try the env/config fallback.
    fallback = _env_fallback()
    if fallback:
        return fallback.encode()

    # 3. Generate a fresh key and try to persist it to the keychain.
    key = Fernet.generate_key()
    try:
        keyring.set_password(_service_name(), _KEYRING_USER, key.decode())
        _log.info("crypto.master_key_generated", stored_in="keychain")
    except Exception as e:  # noqa: BLE001
        _log.warning(
            "crypto.master_key_generated_volatile",
            reason="keychain write failed; key lives for this process only",
            error=str(e),
        )
    return key


def reset_master_key_cache() -> None:
    """Clear the cached master key (test helper)."""
    get_master_key.cache_clear()


def _fernet() -> Fernet:
    return Fernet(get_master_key())


def encrypt(plaintext: bytes) -> bytes:
    """Encrypt bytes with the master key. Output is Fernet ciphertext."""
    if not isinstance(plaintext, (bytes, bytearray)):
        raise SigningError("encrypt() expects bytes; got " + type(plaintext).__name__)
    return _fernet().encrypt(bytes(plaintext))


def decrypt(ciphertext: bytes) -> bytes:
    """Decrypt Fernet ciphertext. Raises SigningError on invalid token."""
    try:
        return _fernet().decrypt(bytes(ciphertext))
    except InvalidToken as e:
        raise SigningError(
            "Failed to decrypt wallet secret — master key mismatch or corrupt ciphertext.",
            suggestion="Check that KEYRING_SERVICE_NAME is unchanged and the OS keychain still holds the original master key.",
        ) from e
