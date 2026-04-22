"""Master-key management + Fernet symmetric encryption for wallet secrets.

Master key resolution order:
    1. Keyfile at `app_config.MASTER_KEY_PATH` (e.g. `agent-data/master.key`).
       This is the primary persistence path — works identically bare-metal
       and in Docker (the agent-data/ directory is bind-mounted). Permissions
       enforced to 0600; world-readable keyfiles are rejected.
    2. OS Keychain via `keyring` library (macOS Keychain, GNOME Keyring,
       Windows Credential Manager). Service name from `KEYRING_SERVICE_NAME`,
       username `master`. Useful bare-metal when no keyfile is present.
    3. If neither yields a key:
         - If a keyfile PATH is configured (normal case): generate a fresh
           Fernet key, write to the keyfile with chmod 0600, return it.
         - If neither keyfile nor keychain is available (test fixtures that
           stub both): raise RuntimeError. This **never** silently generates
           a volatile in-memory key — that is the bug that stranded wallets
           in pre-2026-04-22 builds.

Encryption: Fernet (AES-128-CBC + HMAC-SHA256, URL-safe base64). Ciphertext
stored as a BLOB in SQLite.

Invariant: once a master key has been written somewhere persistent (keyfile
or keychain), future calls return THAT key, never a new one. If the DB has
ciphertext we can't decrypt, that's a configuration error the user must
resolve — we don't paper over it by inventing a new key.
"""
from __future__ import annotations

import os
import stat
from functools import lru_cache
from pathlib import Path

import keyring
from cryptography.fernet import Fernet, InvalidToken

from src.config import app_config
from src.shared.errors import SigningError
from src.shared.logging import get_logger

_KEYRING_USER = "master"
_log = get_logger(__name__)


class MasterKeySource:
    KEYFILE = "keyfile"
    KEYCHAIN = "keychain"
    GENERATED_KEYFILE = "generated_keyfile"


def _service_name() -> str:
    return str(app_config.KEYRING_SERVICE_NAME)


def _keyfile_path() -> Path | None:
    raw = getattr(app_config, "MASTER_KEY_PATH", None)
    if not raw:
        return None
    return Path(str(raw)).expanduser().resolve()


def _check_keyfile_permissions(path: Path) -> None:
    """Reject world- or group-readable keyfiles on POSIX systems.

    On Windows `stat.S_IRWXG` / `S_IRWXO` bits don't carry the same meaning,
    so we log-warn but don't reject — Windows ACLs do the protection.
    """
    if os.name != "posix":
        return
    st = path.stat()
    if st.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise SigningError(
            f"Master keyfile {path} is group- or world-readable (mode {oct(st.st_mode & 0o777)}).",
            suggestion=f"chmod 600 {path} and retry.",
        )


def _read_keyfile() -> tuple[bytes, str] | None:
    """Return (key_bytes, source_tag) or None if the keyfile path is unset / missing."""
    path = _keyfile_path()
    if path is None or not path.exists():
        return None
    _check_keyfile_permissions(path)
    data = path.read_bytes().strip()
    if len(data) != 44:
        raise SigningError(
            f"Master keyfile {path} has length {len(data)}, expected 44 (Fernet key).",
            suggestion="Delete the file and let the agent regenerate, OR restore a valid backup.",
        )
    return data, MasterKeySource.KEYFILE


def _read_keychain() -> tuple[bytes, str] | None:
    """Return (key_bytes, source_tag) from OS keychain, or None if missing / unavailable."""
    try:
        existing = keyring.get_password(_service_name(), _KEYRING_USER)
    except Exception as e:  # noqa: BLE001
        _log.warning("crypto.keychain_unavailable", error=str(e))
        return None
    if not existing:
        return None
    return existing.encode(), MasterKeySource.KEYCHAIN


def _generate_and_persist_keyfile() -> tuple[bytes, str]:
    path = _keyfile_path()
    if path is None:
        raise RuntimeError(
            "No master key found and MASTER_KEY_PATH is not configured. "
            "Set MASTER_KEY_PATH in local-config.json (recommended) or "
            "ensure the OS keychain is reachable."
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    key = Fernet.generate_key()
    # Write atomically: tmp + chmod + rename.
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(key)
    if os.name == "posix":
        os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    _log.info("crypto.master_key_generated", stored_in="keyfile", path=str(path))
    return key, MasterKeySource.GENERATED_KEYFILE


@lru_cache(maxsize=1)
def _get_master_key_with_source() -> tuple[bytes, str]:
    """Return (master_key_bytes, source_tag) — see MasterKeySource.

    Idempotent across process lifetime via lru_cache.
    """
    # 1. Keyfile (primary persistence path)
    res = _read_keyfile()
    if res is not None:
        return res

    # 2. Keychain (bare-metal fallback)
    res = _read_keychain()
    if res is not None:
        return res

    # 3. Generate + persist
    return _generate_and_persist_keyfile()


def get_master_key() -> bytes:
    """Return the Fernet master key as bytes (urlsafe-b64 encoded, 44 chars)."""
    return _get_master_key_with_source()[0]


def get_master_key_source() -> str:
    """Return a human-readable tag for where the master key currently lives.

    One of: 'keyfile', 'keychain', 'generated_keyfile'. Used by wallet
    responses so the user knows how their secret is protected.
    """
    return _get_master_key_with_source()[1]


def reset_master_key_cache() -> None:
    """Clear the cached master key (test helper)."""
    _get_master_key_with_source.cache_clear()


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
        path = _keyfile_path()
        raise SigningError(
            "Failed to decrypt wallet secret — master key mismatch or corrupt ciphertext.",
            suggestion=(
                f"Check that {path} hasn't been rotated or overwritten. "
                "If you rotated the master key, wallets encrypted with the "
                "previous key are unrecoverable agent-side; recover funds "
                "off-agent using the wallet's original secret backup."
            ),
        ) from e
