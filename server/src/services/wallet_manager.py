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
from eth_utils import to_checksum_address
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


# Fields that should be int when they're present. The mangrovemarkets SDK
# returns them as strings (or `null` for missing EIP-1559 fields on legacy
# txs); eth_account's TypedTransaction validator rejects strings and Nones.
# Verified against the real Base mainnet swap (scripts/first_live_swap.py).
_INT_FIELDS = {
    "nonce", "gas", "gasLimit", "gasPrice",
    "maxFeePerGas", "maxPriorityFeePerGas",
    "value", "chainId", "type",
}


def _normalize_payload(payload: dict, chain_id: int | None = None) -> dict:
    """Coerce an SDK payload into a dict eth_account will accept.

    Observed SDK quirks (from real Base mainnet swap, April 2026):
    - numeric fields arrive as strings: "0", "11000000"
    - chainId is omitted entirely
    - approve_token returns EIP-1559 fields (maxFeePerGas populated);
      prepare_swap returns legacy (gasPrice populated, EIP-1559 nulls)

    Normalization:
    - drop keys whose value is None (so eth_account doesn't complain
      about `maxFeePerGas=None` on a legacy tx)
    - coerce known-numeric fields from str/hex to int
    - checksum the `to` address
    - inject chainId if missing and caller supplied one
    - stamp tx type 2 (EIP-1559) when maxFee fields are populated,
      else leave as legacy
    """
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
    """Sign an EVM transaction dict with the wallet's key.

    Returns the signed transaction as a hex string suitable for passing to
    mangrovemarkets.dex.broadcast(). The key is decrypted locally, used to
    sign, and then dropped.

    Args:
        unsigned_tx: EVM tx dict from the SDK (may have SDK quirks: stringified
                     numeric fields, missing chainId, nulls for the unused gas
                     pricing fields). See _normalize_payload().
        wallet_address: Address from the agent's local wallet store.
        chain_id: Optional chainId to inject if the payload omits it. Strongly
                  recommended — without it EIP-1559 signing defaults to
                  chainId=0 and broadcast fails.
    """
    normalized = _normalize_payload(unsigned_tx, chain_id=chain_id)

    secret = _load_secret(wallet_address)
    try:
        # Accept either a seed phrase (HD-derived) or a 0x-prefixed private key.
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
        # Best-effort zeroing. Python strings are immutable so we can't truly
        # wipe, but we drop our local reference so the GC can reclaim.
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
