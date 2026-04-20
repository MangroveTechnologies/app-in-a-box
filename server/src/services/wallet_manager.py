"""wallet_manager — local encrypted key storage + signing.

Responsibilities:
- Create wallets via mangrovemarkets.wallet.create(). Encrypt the returned
  seed/private_key with Fernet, persist the ciphertext in SQLite.
- List stored wallets (addresses + metadata only; never returns secrets).
- Sign arbitrary EVM transactions locally. The SDK never sees the key.

Security:
- The seed phrase / private key is returned in the creation response
  EXACTLY ONCE so the user can back it up. After that it's only
  accessible encrypted on disk.
- sign() decrypts into a local bytes variable, derives the signing
  account, signs, then discards the variable. We do not hold the
  plaintext key any longer than needed.

Chain support (v1): EVM only. XRPL returns ChainNotSupportedInV1.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from eth_account import Account
from eth_account.datastructures import SignedTransaction
from pydantic import BaseModel

from src.shared.clients.mangrove import mangrovemarkets_client
from src.shared.crypto.fernet import decrypt, encrypt
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

SEED_PHRASE_WARNING = (
    "The seed phrase is shown ONCE here and then encrypted to disk. "
    "It is NOT retrievable via the API after this response. "
    "⚠️ The seed phrase will appear in your Claude Code chat transcript under "
    "~/.claude/projects/.../*.jsonl. Copy it to a secure location (paper, "
    "hardware wallet, password manager), delete the transcript file if needed, "
    "and never screenshot without securing the image."
)


class WalletCreateResponse(BaseModel):
    """Response for POST /wallet/create. The seed phrase is returned ONCE."""

    address: str
    chain: str
    network: str
    chain_id: int | None = None
    label: str | None = None
    created_at: datetime
    seed_phrase: str  # one-time, then encrypted to disk
    warning: str


class WalletListItem(BaseModel):
    """Redacted view of a stored wallet. Never carries secrets."""

    address: str
    chain: str
    network: str
    chain_id: int | None = None
    label: str | None = None
    created_at: datetime


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


def create_wallet(
    chain: str,
    network: str,
    chain_id: int | None = None,
    label: str | None = None,
) -> WalletCreateResponse:
    """Create a new wallet, encrypt the secret, persist to SQLite.

    Returns the seed phrase once in the response; after that it is only
    accessible in encrypted form via sign().
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

    # Delegate key generation to the SDK (which may call mangrovemarkets-mcp-server).
    result = mangrovemarkets_client().wallet.create(
        chain=chain_normalized, network=network, chain_id=chain_id,
    )
    secret = _extract_secret(result)
    address = str(result.address)

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

    _log.info(
        "wallet.created",
        wallet_id=wallet_id,
        address=address,
        chain=chain_normalized,
        network=network,
        chain_id=chain_id,
    )

    return WalletCreateResponse(
        address=address,
        chain=chain_normalized,
        network=network,
        chain_id=chain_id,
        label=label,
        created_at=created_at,
        seed_phrase=secret,
        warning=SEED_PHRASE_WARNING,
    )


def list_wallets() -> list[WalletListItem]:
    """Return all stored wallets. Secrets are NEVER returned."""
    rows = get_connection().execute(
        """SELECT address, chain, network, chain_id, label, created_at
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


def sign(unsigned_tx: dict, wallet_address: str) -> str:
    """Sign an EVM transaction dict with the wallet's key.

    Returns the signed transaction as a hex string suitable for passing to
    mangrovemarkets.dex.broadcast(). The key is decrypted locally, used to
    sign, and then dropped.

    Args:
        unsigned_tx: EVM tx dict (at minimum: nonce, chainId, to, value,
                     data, gas, maxFeePerGas + maxPriorityFeePerGas
                     OR gasPrice).
        wallet_address: Address from Hank's local wallet store.
    """
    secret = _load_secret(wallet_address)
    try:
        # Accept either a seed phrase (HD-derived) or a 0x-prefixed private key.
        if secret.startswith("0x") or len(secret) == 64:
            account = Account.from_key(secret)
        else:
            Account.enable_unaudited_hdwallet_features()
            account = Account.from_mnemonic(secret)

        signed: SignedTransaction = account.sign_transaction(unsigned_tx)
    except Exception as e:  # noqa: BLE001
        raise SigningError(
            f"Failed to sign transaction for {wallet_address}: {e}",
            suggestion="Verify the tx dict has all EVM required fields (nonce, chainId, to, value, data, gas, maxFeePerGas/maxPriorityFeePerGas).",
        ) from e
    finally:
        # Best-effort zeroing. Python strings are immutable so we can't truly
        # wipe, but we drop our local reference so the GC can reclaim.
        del secret

    _log.info(
        "wallet.signed_tx",
        wallet_address=wallet_address,
        chain_id=unsigned_tx.get("chainId"),
        to=unsigned_tx.get("to"),
    )
    raw = signed.rawTransaction if hasattr(signed, "rawTransaction") else signed.raw_transaction
    raw_hex = raw.hex()
    return raw_hex if raw_hex.startswith("0x") else "0x" + raw_hex


def sign_message(message: str | bytes, wallet_address: str) -> str:
    """Sign a message (EIP-191 personal_sign) with the wallet's key.

    Useful for off-chain authentication flows. The SDK may need this for
    EIP-712 or EIP-191 signing during approval or order submission.
    """
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
    """Internal helper: return raw wallet row or None."""
    row = get_connection().execute(
        """SELECT address, chain, network, chain_id, label, created_at
           FROM wallets WHERE address = ?""",
        (address,),
    ).fetchone()
    return dict(row) if row else None


def wallet_exists(address: str) -> bool:
    """Return True if a wallet with this address is stored."""
    return _get_wallet_row(address) is not None
