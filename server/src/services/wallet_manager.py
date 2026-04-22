"""wallet_manager — local encrypted key storage + signing.

Responsibilities:
- Create wallets via mangrovemarkets.wallet.create(). Encrypt the returned
  seed/private_key with Fernet, persist the ciphertext in SQLite. Stash
  the plaintext in the in-process SecretVault and return only a secret_id
  in the MCP response — the plaintext never enters the Claude Code
  conversation context.
- Import externally-generated private keys via the stash-and-consume
  pattern: user's bash CLI posts the raw key to /internal/stash-secret
  and gets back a secret_id, then calls import_wallet with that id.
- List stored wallets (addresses + metadata only; never returns secrets).
- Sign arbitrary EVM transactions locally. The SDK never sees the key.
- Gate live trading on explicit user backup confirmation (backup_confirmed_at).
  Paper mode is unaffected.

Security:
- The plaintext key NEVER appears in an MCP tool response. Responses carry
  only the opaque secret_id, which is useful only via the localhost reveal
  CLI (out-of-band, never through Claude Code).
- sign() decrypts into a local bytes variable, derives the signing account,
  signs, discards the variable. Plaintext lifetime is <10ms per op.

Chain support (v1): EVM only. XRPL returns ChainNotSupportedInV1.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from eth_account import Account
from eth_account.datastructures import SignedTransaction
from eth_utils import to_checksum_address
from pydantic import BaseModel

from src.services.secret_vault import vault
from src.shared.clients.mangrove import mangrovemarkets_client
from src.shared.crypto.fernet import decrypt, encrypt, get_master_key_source
from src.shared.db.sqlite import get_connection
from src.shared.errors import (
    ChainNotSupportedInV1,
    SigningError,
    WalletAlreadyExists,
    WalletNotFound,
)
from src.shared.logging import get_logger

_log = get_logger(__name__)

_ENCRYPTION_METHOD = "fernet-v1"


# ---------------------------------------------------------------------------
# Response / model types
# ---------------------------------------------------------------------------


SecretType = Literal["private_key", "mnemonic"]


class WalletCreateResponse(BaseModel):
    """Response for POST /wallet/create.

    The plaintext secret is NEVER included. The caller receives a secret_id
    pointing at an in-process vault entry (TTL-bound, single-read) and a
    reveal_cmd describing how to retrieve the plaintext out-of-band.
    """

    address: str
    chain: str
    network: str
    chain_id: int | None = None
    label: str | None = None
    created_at: datetime
    secret_id: str
    secret_type: SecretType
    master_key_source: str
    reveal_cmd: str
    secret_ttl_seconds: int
    backup_required: bool
    deposit_instructions: str
    safety_note: str


class WalletImportResponse(BaseModel):
    """Response for import_wallet. Metadata only — no secret material."""

    address: str
    chain: str
    network: str
    chain_id: int | None = None
    label: str | None = None
    created_at: datetime
    master_key_source: str
    backup_required: bool
    next_step: str


class StashSecretResponse(BaseModel):
    """Response for POST /internal/stash-secret. Opaque id only."""

    secret_id: str
    secret_ttl_seconds: int


class RevealSecretResponse(BaseModel):
    """Response for GET /internal/reveal-secret/{id} or /wallet/{addr}/reveal.

    Contains plaintext — only exposed over localhost to a CLI subprocess
    that is not Claude Code. NEVER return this from an MCP tool.
    """

    secret: str
    address: str | None = None


class WalletListItem(BaseModel):
    """Redacted view of a stored wallet. Never carries secrets."""

    address: str
    chain: str
    network: str
    chain_id: int | None = None
    label: str | None = None
    created_at: datetime
    backup_confirmed_at: datetime | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _deposit_instructions(address: str, chain: str, network: str) -> str:
    net_label = "mainnet (real funds)" if network == "mainnet" else f"{network}"
    chain_label = chain.upper() if chain == "evm" else chain
    return (
        f"Deposit to this {chain_label} address on {net_label}:\n"
        f"  {address}\n\n"
        "Start with a SMALL TEST AMOUNT (1-5 USDC). Verify via `get_balances` "
        "before sending more. This wallet is dedicated to the agent — keep it "
        "separate from your personal holdings."
    )


def _detect_secret_type(secret: str) -> SecretType:
    """Heuristic: 0x + 64 hex or 64 hex → private_key, else mnemonic."""
    s = secret.strip()
    if s.startswith("0x") and len(s) == 66:
        return "private_key"
    if len(s) == 64 and all(c in "0123456789abcdefABCDEF" for c in s):
        return "private_key"
    return "mnemonic"


def _derive_address(secret: str) -> str:
    """Return the EVM address derived from the given secret."""
    s = secret.strip()
    if _detect_secret_type(s) == "private_key":
        return Account.from_key(s).address
    Account.enable_unaudited_hdwallet_features()
    return Account.from_mnemonic(s).address


def _extract_secret(create_result: Any) -> str:
    """Pull whichever sensitive field the SDK populated.

    SDK's WalletCreateResult can have any of: seed_phrase, private_key, secret.
    We store whichever is present, in priority order (seed_phrase > private_key > secret).
    """
    for attr in ("seed_phrase", "private_key", "secret"):
        val = getattr(create_result, attr, None)
        if val:
            return str(val)
    raise SigningError(
        "SDK wallet.create() returned no seed_phrase, private_key, or secret.",
        suggestion="Check the mangrovemarkets SDK version and the target chain's supported wallet_creation mode.",
    )


def _safety_note(secret_type: SecretType, master_key_source: str) -> str:
    src_blurb = {
        "keyfile": "your local keyfile (./agent-data/master.key, chmod 600)",
        "generated_keyfile": "your local keyfile (./agent-data/master.key, chmod 600)",
        "keychain": "your OS keychain (macOS Keychain / Linux Secret Service / Windows Credential Manager)",
    }.get(master_key_source, master_key_source)

    import_ui = (
        "MetaMask → Import Account → Private Key"
        if secret_type == "private_key"
        else "MetaMask → Import Account → Secret Recovery Phrase"
    )
    return (
        f"Your secret (type: {secret_type}) is encrypted at rest with a Fernet "
        f"master key stored in {src_blurb}. Run the reveal_cmd ONCE to back it "
        f"up outside the agent (off-agent backup needed for disaster recovery "
        f"if the master key is ever lost). Import with: {import_ui}."
    )


def _secret_vault_ttl() -> int:
    from src.config import app_config
    try:
        return int(app_config.SECRET_VAULT_TTL_SECONDS)
    except (AttributeError, TypeError, ValueError):
        return 300


def _reveal_cmd_for(secret_id: str) -> str:
    return f"./scripts/reveal-secret.sh {secret_id}"


def _reveal_cmd_for_address(address: str) -> str:
    return f"./scripts/reveal-secret.sh --address {address}"


# ---------------------------------------------------------------------------
# Create wallet (secret stays in-process, MCP response has secret_id only)
# ---------------------------------------------------------------------------


def create_wallet(
    chain: str,
    network: str,
    chain_id: int | None = None,
    label: str | None = None,
) -> WalletCreateResponse:
    """Create a new wallet. Encrypts the secret, persists to SQLite, stashes
    plaintext in the in-process vault, returns a secret_id.
    """
    chain_normalized = chain.lower()
    if chain_normalized in {"xrpl", "xrp"}:
        raise ChainNotSupportedInV1(
            "XRPL wallet creation is not supported in v1.",
            suggestion="Use an EVM chain (e.g. Base, Ethereum, Arbitrum). XRPL support is planned for a future release.",
        )
    if chain_normalized != "evm":
        raise ChainNotSupportedInV1(
            f"Chain '{chain}' is not supported in v1.",
            suggestion="Supported: evm (with a valid chain_id).",
        )

    result = mangrovemarkets_client().wallet.create(
        chain=chain_normalized, network=network, chain_id=chain_id,
    )
    secret = _extract_secret(result)
    address = str(result.address)
    secret_type = _detect_secret_type(secret)

    conn = get_connection()
    existing = conn.execute(
        "SELECT 1 FROM wallets WHERE address = ?", (address,),
    ).fetchone()
    if existing:
        raise WalletAlreadyExists(
            f"Wallet with address {address} is already stored.",
            suggestion="Use GET /wallet/list to see stored wallets.",
        )

    encrypted = encrypt(secret.encode())
    created_at = datetime.now(timezone.utc)
    wallet_id = str(uuid.uuid4())

    conn.execute(
        """INSERT INTO wallets
           (id, address, chain, network, chain_id, encrypted_secret,
            encryption_method, label, created_at, metadata_json)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            wallet_id, address, chain_normalized, network, chain_id,
            encrypted, _ENCRYPTION_METHOD, label, created_at.isoformat(), None,
        ),
    )
    conn.commit()

    # Stash plaintext in vault. `secret` is not returned to the caller.
    secret_id = vault.stash_for_address(secret, address=address)

    _log.info(
        "wallet.created",
        wallet_id=wallet_id,
        address=address,
        chain=chain_normalized,
        network=network,
        chain_id=chain_id,
        secret_type=secret_type,
    )

    return WalletCreateResponse(
        address=address,
        chain=chain_normalized,
        network=network,
        chain_id=chain_id,
        label=label,
        created_at=created_at,
        secret_id=secret_id,
        secret_type=secret_type,
        master_key_source=get_master_key_source(),
        reveal_cmd=_reveal_cmd_for(secret_id),
        secret_ttl_seconds=_secret_vault_ttl(),
        backup_required=True,
        deposit_instructions=_deposit_instructions(address, chain_normalized, network),
        safety_note=_safety_note(secret_type, get_master_key_source()),
    )


# ---------------------------------------------------------------------------
# Import wallet (secret provided via stash_secret, consumed by secret_id)
# ---------------------------------------------------------------------------


def import_wallet(
    secret_id: str,
    chain: str = "evm",
    network: str = "mainnet",
    chain_id: int | None = 8453,
    label: str | None = None,
) -> WalletImportResponse:
    """Import an existing wallet whose secret has been stashed in the vault.

    The user's CLI flow:
      1. Run `./scripts/stash-secret.sh` — it prompts for the private key via
         `read -s`, POSTs to /internal/stash-secret, prints the returned id.
      2. Ask the agent to import that id.
      3. Agent calls import_wallet(secret_id=<id>).

    The private key never enters Claude Code's conversation context.
    """
    chain_normalized = chain.lower()
    if chain_normalized != "evm":
        raise ChainNotSupportedInV1(
            f"Chain '{chain}' is not supported for import in v1.",
            suggestion="Supported: evm (with a valid chain_id).",
        )

    try:
        secret = vault.reveal(secret_id)
    except KeyError as e:
        raise SigningError(
            "secret_id is unknown or has expired.",
            suggestion=(
                "Re-run `./scripts/stash-secret.sh` to stash your key and get a "
                "fresh secret_id, then retry the import. Each secret_id is "
                "single-read and TTL-bound."
            ),
        ) from e

    try:
        address = _derive_address(secret)
    except Exception as e:  # noqa: BLE001
        raise SigningError(
            f"Could not derive EVM address from the provided secret: {e}",
            suggestion="Verify the secret is a valid 0x-prefixed private key or BIP39 mnemonic.",
        ) from e

    conn = get_connection()
    existing = conn.execute(
        "SELECT 1 FROM wallets WHERE address = ?", (address,),
    ).fetchone()
    if existing:
        raise WalletAlreadyExists(
            f"Wallet with address {address} is already stored.",
            suggestion="Use GET /wallet/list to see stored wallets.",
        )

    encrypted = encrypt(secret.encode())
    # Drop reference to plaintext immediately.
    del secret
    created_at = datetime.now(timezone.utc)
    wallet_id = str(uuid.uuid4())

    conn.execute(
        """INSERT INTO wallets
           (id, address, chain, network, chain_id, encrypted_secret,
            encryption_method, label, created_at, metadata_json,
            backup_confirmed_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            wallet_id, address, chain_normalized, network, chain_id,
            encrypted, _ENCRYPTION_METHOD, label, created_at.isoformat(), None,
            # Imported wallets: user already has the secret off-agent by
            # definition (they just typed it into stash-secret.sh). Auto-
            # confirm backup so they don't have to do it again.
            created_at.isoformat(),
        ),
    )
    conn.commit()

    _log.info(
        "wallet.imported",
        wallet_id=wallet_id,
        address=address,
        chain=chain_normalized,
        network=network,
        chain_id=chain_id,
    )

    return WalletImportResponse(
        address=address,
        chain=chain_normalized,
        network=network,
        chain_id=chain_id,
        label=label,
        created_at=created_at,
        master_key_source=get_master_key_source(),
        backup_required=False,  # imported: user already has it
        next_step=(
            "Verify balance with get_balances. The wallet is live — auto-"
            "confirmed as backed-up because you typed the key into the CLI, "
            "which means you have it off-agent already."
        ),
    )


# ---------------------------------------------------------------------------
# Reveal-on-demand (out-of-band via CLI, never through MCP)
# ---------------------------------------------------------------------------


def reveal_wallet_secret(address: str) -> RevealSecretResponse:
    """Decrypt and return the plaintext secret for a stored wallet.

    INTENDED FOR CALL BY THE LOCALHOST CLI ONLY. The server exposes this
    via a private REST endpoint; the bash script in scripts/reveal-secret.sh
    invokes it and prints to the user's terminal. MCP tools MUST NOT call
    this — doing so would leak the plaintext back through Claude Code.
    """
    secret = _load_secret(address)
    _log.info("wallet.secret_revealed", address=address)
    return RevealSecretResponse(secret=secret, address=address)


def stash_external_secret(secret: str, address_hint: str | None = None) -> str:
    """Accept a plaintext secret from the CLI, stash in the vault, return id.

    Called by /internal/stash-secret. The caller is expected to be the
    localhost bash CLI, which reads the secret via `read -s` and POSTs it
    here. The secret never enters Claude Code's context.
    """
    if not secret or not secret.strip():
        raise ValueError("secret must be non-empty")
    # If we can derive an address, tag the vault entry for later reveal-by-address.
    tag = address_hint
    if tag is None:
        try:
            tag = _derive_address(secret)
        except Exception:  # noqa: BLE001
            tag = None
    return vault.stash_for_address(secret, address=tag) if tag else vault.stash(secret)


# ---------------------------------------------------------------------------
# Backup confirmation (gates live trading)
# ---------------------------------------------------------------------------


def confirm_backup(address: str) -> WalletListItem:
    """Mark a wallet as backed-up by the user.

    The user invokes `./scripts/confirm-backup.sh <address>` AFTER they've
    saved the plaintext secret outside the agent. This flips the flag;
    downstream, execute_swap and update_strategy_status(live) unlock.
    """
    conn = get_connection()
    row = conn.execute(
        "SELECT 1 FROM wallets WHERE address = ?", (address,),
    ).fetchone()
    if not row:
        raise WalletNotFound(
            f"Wallet {address} not found.",
            suggestion="Use GET /wallet/list to see stored wallets.",
        )
    now = datetime.now(timezone.utc)
    conn.execute(
        "UPDATE wallets SET backup_confirmed_at = ? WHERE address = ?",
        (now.isoformat(), address),
    )
    conn.commit()
    _log.info("wallet.backup_confirmed", address=address, confirmed_at=now.isoformat())
    updated = conn.execute(
        """SELECT address, chain, network, chain_id, label, created_at,
                  backup_confirmed_at
           FROM wallets WHERE address = ?""",
        (address,),
    ).fetchone()
    return WalletListItem(
        address=updated["address"],
        chain=updated["chain"],
        network=updated["network"],
        chain_id=updated["chain_id"],
        label=updated["label"],
        created_at=datetime.fromisoformat(updated["created_at"]),
        backup_confirmed_at=datetime.fromisoformat(updated["backup_confirmed_at"])
        if updated["backup_confirmed_at"] else None,
    )


def require_backup_confirmed(address: str) -> None:
    """Raise SigningError if the wallet has no backup confirmation.

    Called by execute_swap / live-promotion paths. Paper mode does not
    call this — no real funds at risk.
    """
    row = get_connection().execute(
        "SELECT backup_confirmed_at FROM wallets WHERE address = ?",
        (address,),
    ).fetchone()
    if not row:
        raise WalletNotFound(
            f"Wallet {address} not found.",
            suggestion="Use GET /wallet/list to see stored wallets.",
        )
    if not row["backup_confirmed_at"]:
        raise SigningError(
            f"Wallet {address} is not backed up. Live trading refused.",
            suggestion=(
                "Back up the wallet's secret OUTSIDE the agent first:\n"
                f"  ./scripts/reveal-secret.sh --address {address}\n"
                "Save the printed secret in a password manager / hardware "
                "wallet / paper. THEN confirm the backup with:\n"
                f"  ./scripts/confirm-backup.sh {address}\n"
                "After that the agent will unlock live trading for this wallet."
            ),
        )


# ---------------------------------------------------------------------------
# List / load / exists
# ---------------------------------------------------------------------------


def list_wallets() -> list[WalletListItem]:
    """Return all stored wallets. Secrets are NEVER returned."""
    rows = get_connection().execute(
        """SELECT address, chain, network, chain_id, label, created_at,
                  backup_confirmed_at
           FROM wallets ORDER BY created_at DESC""",
    ).fetchall()
    return [
        WalletListItem(
            address=r["address"],
            chain=r["chain"],
            network=r["network"],
            chain_id=r["chain_id"],
            label=r["label"],
            created_at=datetime.fromisoformat(r["created_at"]),
            backup_confirmed_at=datetime.fromisoformat(r["backup_confirmed_at"])
            if r["backup_confirmed_at"] else None,
        )
        for r in rows
    ]


def _load_secret(address: str) -> str:
    row = get_connection().execute(
        "SELECT encrypted_secret, encryption_method FROM wallets WHERE address = ?",
        (address,),
    ).fetchone()
    if not row:
        raise WalletNotFound(
            f"Wallet {address} not found.",
            suggestion="Use GET /wallet/list to see stored wallets or POST /wallet/create to add one.",
        )
    if row["encryption_method"] != _ENCRYPTION_METHOD:
        raise SigningError(
            f"Unknown encryption method: {row['encryption_method']}",
            suggestion="The wallet was encrypted with a different version; manual migration required.",
        )
    return decrypt(row["encrypted_secret"]).decode()


# ---------------------------------------------------------------------------
# Signing (unchanged from previous impl except for backup-gated callers)
# ---------------------------------------------------------------------------


_INT_FIELDS = {
    "nonce", "gas", "gasLimit", "gasPrice",
    "maxFeePerGas", "maxPriorityFeePerGas",
    "value", "chainId", "type",
}


def _normalize_payload(payload: dict, chain_id: int | None = None) -> dict:
    out: dict = {}
    for k, v in payload.items():
        if v is None:
            continue
        if k in _INT_FIELDS and isinstance(v, str):
            out[k] = int(v, 16) if v.startswith("0x") else int(v)
        elif k == "to" and isinstance(v, str) and v.startswith("0x"):
            out[k] = to_checksum_address(v)
        else:
            out[k] = v

    if chain_id is not None and "chainId" not in out:
        out["chainId"] = chain_id

    has_eip1559 = (
        out.get("maxFeePerGas") is not None
        and out.get("maxPriorityFeePerGas") is not None
    )
    if has_eip1559:
        out.setdefault("type", 2)
        out.pop("gasPrice", None)
    elif "gasPrice" in out:
        out.pop("maxFeePerGas", None)
        out.pop("maxPriorityFeePerGas", None)
        out.pop("type", None)

    return out


def sign(unsigned_tx: dict, wallet_address: str, chain_id: int | None = None) -> str:
    """Sign an EVM transaction with the wallet's key.

    NOTE: callers that represent live money movement (execute_swap, live
    strategy evaluator) MUST call require_backup_confirmed(wallet_address)
    first. sign() itself does not gate — some callers (paper mode, signing
    approval txs during a read-only quote path) legitimately need to sign
    without a backup. The gate lives one layer up.
    """
    normalized = _normalize_payload(unsigned_tx, chain_id=chain_id)

    secret = _load_secret(wallet_address)
    try:
        if secret.startswith("0x") or len(secret) == 64:
            account = Account.from_key(secret)
        else:
            Account.enable_unaudited_hdwallet_features()
            account = Account.from_mnemonic(secret)

        signed: SignedTransaction = account.sign_transaction(normalized)
    except Exception as e:  # noqa: BLE001
        raise SigningError(
            f"Failed to sign transaction for {wallet_address}: {e}",
            suggestion="Verify the tx dict has all EVM required fields. Pass chain_id explicitly if the SDK payload omits it.",
        ) from e
    finally:
        del secret

    _log.info(
        "wallet.signed_tx",
        wallet_address=wallet_address,
        chain_id=normalized.get("chainId"),
        to=normalized.get("to"),
        tx_type=normalized.get("type", 0),
    )
    raw = signed.rawTransaction if hasattr(signed, "rawTransaction") else signed.raw_transaction
    raw_hex = raw.hex()
    return raw_hex if raw_hex.startswith("0x") else "0x" + raw_hex


def sign_message(message: str | bytes, wallet_address: str) -> str:
    """Sign a message (EIP-191 personal_sign) with the wallet's key."""
    from eth_account.messages import encode_defunct

    secret = _load_secret(wallet_address)
    try:
        if secret.startswith("0x") or len(secret) == 64:
            account = Account.from_key(secret)
        else:
            Account.enable_unaudited_hdwallet_features()
            account = Account.from_mnemonic(secret)

        encoded = encode_defunct(text=message) if isinstance(message, str) else encode_defunct(primitive=message)
        signed = account.sign_message(encoded)
    except Exception as e:  # noqa: BLE001
        raise SigningError(
            f"Failed to sign message for {wallet_address}: {e}",
        ) from e
    finally:
        del secret

    sig_hex = signed.signature.hex()
    return sig_hex if sig_hex.startswith("0x") else "0x" + sig_hex


def _get_wallet_row(address: str) -> dict | None:
    row = get_connection().execute(
        """SELECT address, chain, network, chain_id, label, created_at,
                  backup_confirmed_at
           FROM wallets WHERE address = ?""",
        (address,),
    ).fetchone()
    return dict(row) if row else None


def wallet_exists(address: str) -> bool:
    return _get_wallet_row(address) is not None
