"""In-process ephemeral secret store used to keep wallet private keys out
of Claude Code's conversation context.

Why this exists:
    MCP tool responses flow back to the Claude client and become part of the
    conversation transcript — which is sent to Anthropic's API for the next
    LLM turn and persisted to `~/.claude/projects/**/*.jsonl` on disk. If a
    tool ever returns a plaintext private key in its response body, the key
    leaks to both transport and disk.

    SecretVault breaks that coupling: on wallet creation or import, the
    agent stashes the plaintext in memory keyed by a random `vault_token` and
    the MCP response carries ONLY the id. The user retrieves the plaintext
    out-of-band via a local bash/curl script that hits the localhost REST
    API — this subprocess never touches Claude's conversation context.

Semantics:
    - `stash(secret) -> vault_token`: store plaintext, return opaque id.
    - `reveal(vault_token) -> secret`: return AND immediately evict. Single-read.
    - TTL-bound: entries expire after `SECRET_VAULT_TTL_SECONDS` regardless
      of read. Sweep runs lazily on every stash/reveal + via a background
      task (started by the FastAPI lifespan hook).
    - In-process only: restart of the server wipes the vault. That's OK —
      the permanent record is the Fernet-encrypted row in `wallets`. The
      vault exists only as a side-channel for the backup-at-creation moment.

Thread-safety:
    A single `threading.Lock` guards the dict. Reads and writes are short.
    This is not a performance bottleneck; the vault sees at most a few ops
    per wallet operation.
"""
from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass

from src.config import app_config
from src.shared.logging import get_logger

_log = get_logger(__name__)

# How long an entry can live before it's purged, regardless of read.
# Read from config at import time; override in tests via monkeypatch.
_DEFAULT_TTL_SECONDS = 300


def _ttl() -> int:
    raw = getattr(app_config, "SECRET_VAULT_TTL_SECONDS", _DEFAULT_TTL_SECONDS)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return _DEFAULT_TTL_SECONDS


@dataclass
class _Entry:
    secret: str
    expires_at: float
    address: str | None  # optional tag for reveal-by-address lookup


class _Vault:
    def __init__(self) -> None:
        self._entries: dict[str, _Entry] = {}
        self._lock = threading.Lock()

    def _sweep_locked(self, now: float) -> None:
        """Drop expired entries. Caller must hold the lock."""
        expired = [sid for sid, e in self._entries.items() if e.expires_at <= now]
        for sid in expired:
            self._entries.pop(sid, None)
        if expired:
            _log.info("secret_vault.swept", count=len(expired))

    def stash(self, secret: str, *, address: str | None = None) -> str:
        """Store `secret` and return a random opaque id.

        `address` is optional metadata used by reveal-by-address. It is NOT
        part of the id — a caller asking for reveal-by-address must pass the
        address, not the id.
        """
        if not secret:
            raise ValueError("secret must be non-empty")
        sid = secrets.token_urlsafe(16)
        now = time.monotonic()
        with self._lock:
            self._sweep_locked(now)
            self._entries[sid] = _Entry(
                secret=secret,
                expires_at=now + _ttl(),
                address=address,
            )
        _log.info("secret_vault.stashed", vault_token=sid[:8] + "...", has_address=address is not None)
        return sid

    def reveal(self, vault_token: str) -> str:
        """Return the secret and evict the entry (single-read).

        Raises KeyError if the id is unknown or expired.
        """
        now = time.monotonic()
        with self._lock:
            self._sweep_locked(now)
            entry = self._entries.pop(vault_token, None)
        if entry is None:
            raise KeyError(f"vault_token unknown or expired: {vault_token[:8]}...")
        _log.info("secret_vault.revealed", vault_token=vault_token[:8] + "...")
        return entry.secret

    def stash_for_address(self, secret: str, address: str) -> str:
        """Convenience wrapper: stash with an address tag for reveal-by-address."""
        return self.stash(secret, address=address)

    def size(self) -> int:
        """Live count, useful for tests / health checks."""
        with self._lock:
            self._sweep_locked(time.monotonic())
            return len(self._entries)

    def clear(self) -> None:
        """Drop everything. Test helper."""
        with self._lock:
            self._entries.clear()


# Module-level singleton. Import as `from src.services.secret_vault import vault`.
vault = _Vault()
