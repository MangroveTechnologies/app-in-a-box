"""Unit tests for wallet_manager — key gen, encryption, signing."""
from __future__ import annotations

import os
from unittest.mock import MagicMock

os.environ.setdefault("ENVIRONMENT", "test")

import pytest  # noqa: E402
from cryptography.fernet import Fernet  # noqa: E402
from eth_account import Account  # noqa: E402

# A funded-looking private key for signing tests (never sent anywhere).
_TEST_PRIVKEY = "0x" + "11" * 32
_TEST_ADDRESS = Account.from_key(_TEST_PRIVKEY).address


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_file = tmp_path / "test_wallet.db"
    from src.config import app_config
    from src.shared.db import sqlite as db_mod

    monkeypatch.setattr(app_config, "DB_PATH", str(db_file))
    db_mod.reset_connection()
    from src.shared.db.sqlite import init_db
    init_db()
    yield db_file
    db_mod.reset_connection()


@pytest.fixture
def stub_keyring(monkeypatch):
    """Stub keyring with an in-memory store so tests don't touch the real OS keychain."""
    store: dict[tuple[str, str], str] = {}

    def _get(service, user):
        return store.get((service, user))

    def _set(service, user, password):
        store[(service, user)] = password

    monkeypatch.setattr("keyring.get_password", _get)
    monkeypatch.setattr("keyring.set_password", _set)

    from src.shared.crypto import fernet as f
    f.reset_master_key_cache()
    yield store
    f.reset_master_key_cache()


@pytest.fixture
def mock_sdk_create(monkeypatch):
    """Stub mangrovemarkets_client().wallet.create() to return a fixed EVM wallet."""
    sdk_result = MagicMock()
    sdk_result.address = _TEST_ADDRESS
    sdk_result.private_key = _TEST_PRIVKEY
    sdk_result.seed_phrase = None
    sdk_result.secret = None

    sdk_client = MagicMock()
    sdk_client.wallet.create.return_value = sdk_result

    monkeypatch.setattr(
        "src.services.wallet_manager.mangrovemarkets_client",
        lambda: sdk_client,
    )
    return sdk_client


# -- crypto/fernet -----------------------------------------------------------


def test_master_key_generated_on_first_call(stub_keyring):
    from src.shared.crypto.fernet import get_master_key

    key = get_master_key()
    assert len(key) > 0
    # Should be a valid Fernet key
    Fernet(key)
    # Second call returns same (cached)
    assert get_master_key() == key


def test_master_key_persists_in_keychain(stub_keyring):
    from src.shared.crypto.fernet import get_master_key, reset_master_key_cache

    k1 = get_master_key()
    reset_master_key_cache()
    k2 = get_master_key()
    assert k1 == k2  # re-read from keychain


def test_encrypt_decrypt_round_trip(stub_keyring):
    from src.shared.crypto.fernet import decrypt, encrypt

    plaintext = b"super secret seed"
    ct = encrypt(plaintext)
    assert ct != plaintext
    assert decrypt(ct) == plaintext


def test_decrypt_invalid_raises_signing_error(stub_keyring):
    from src.shared.crypto.fernet import decrypt
    from src.shared.errors import SigningError

    with pytest.raises(SigningError):
        decrypt(b"not valid ciphertext")


# -- wallet_manager.create_wallet --------------------------------------------


def test_create_wallet_evm_persists_encrypted(temp_db, stub_keyring, mock_sdk_create):
    from src.services.secret_vault import vault
    from src.services.wallet_manager import create_wallet
    from src.shared.db.sqlite import get_connection

    response = create_wallet(chain="evm", network="testnet", chain_id=84532, label="test")
    assert response.address == _TEST_ADDRESS
    # The plaintext is NOT in the response — only a secret_id pointing at the vault.
    assert response.secret_id and len(response.secret_id) >= 16
    assert response.secret_type == "private_key"
    assert response.master_key_source in {"keyfile", "keychain", "generated_keyfile"}
    assert response.reveal_cmd.startswith("./scripts/reveal-secret.sh ")
    assert response.backup_required is True
    # No seed_phrase/private_key field on the response model.
    resp_dump = response.model_dump()
    assert "seed_phrase" not in resp_dump
    assert "private_key" not in resp_dump
    # Deposit instructions still guide the user.
    assert _TEST_ADDRESS in response.deposit_instructions
    assert "small test amount" in response.deposit_instructions.lower()

    # The vault must have the plaintext (so reveal-secret.sh can retrieve it).
    plaintext = vault.reveal(response.secret_id)
    assert plaintext == _TEST_PRIVKEY

    row = get_connection().execute(
        "SELECT address, chain, chain_id, label, encrypted_secret, encryption_method, backup_confirmed_at FROM wallets WHERE address=?",
        (_TEST_ADDRESS,),
    ).fetchone()
    assert row["chain"] == "evm"
    assert row["chain_id"] == 84532
    assert row["label"] == "test"
    assert row["encrypted_secret"] != _TEST_PRIVKEY.encode()  # actually encrypted
    assert row["encryption_method"] == "fernet-v1"
    # Fresh wallet: backup not confirmed yet.
    assert row["backup_confirmed_at"] is None


def test_create_wallet_xrpl_raises(temp_db, stub_keyring, mock_sdk_create):
    from src.services.wallet_manager import create_wallet
    from src.shared.errors import ChainNotSupportedInV1

    with pytest.raises(ChainNotSupportedInV1):
        create_wallet(chain="xrpl", network="testnet")


def test_create_wallet_duplicate_raises(temp_db, stub_keyring, mock_sdk_create):
    from src.services.wallet_manager import create_wallet
    from src.shared.errors import WalletAlreadyExists

    create_wallet(chain="evm", network="testnet", chain_id=84532)
    with pytest.raises(WalletAlreadyExists):
        create_wallet(chain="evm", network="testnet", chain_id=84532)


# -- list_wallets ------------------------------------------------------------


def test_list_wallets_redacts_secret(temp_db, stub_keyring, mock_sdk_create):
    from src.services.wallet_manager import WalletListItem, create_wallet, list_wallets

    create_wallet(chain="evm", network="testnet", chain_id=84532, label="one")
    items = list_wallets()
    assert len(items) == 1
    assert isinstance(items[0], WalletListItem)
    assert items[0].address == _TEST_ADDRESS
    # No secret fields on WalletListItem
    serialized = items[0].model_dump()
    for forbidden in ("secret", "seed_phrase", "private_key", "encrypted_secret"):
        assert forbidden not in serialized


def test_list_wallets_empty(temp_db, stub_keyring):
    from src.services.wallet_manager import list_wallets

    assert list_wallets() == []


# -- sign --------------------------------------------------------------------


def test_sign_round_trip(temp_db, stub_keyring, mock_sdk_create):
    from src.services.wallet_manager import create_wallet, sign

    create_wallet(chain="evm", network="testnet", chain_id=84532)

    unsigned = {
        "nonce": 0,
        "gas": 21000,
        "maxFeePerGas": 2_000_000_000,
        "maxPriorityFeePerGas": 1_000_000_000,
        "to": "0x" + "22" * 20,
        "value": 0,
        "data": b"",
        "chainId": 84532,
    }
    raw_hex = sign(unsigned, _TEST_ADDRESS)
    assert raw_hex.startswith("0x")
    # Decode to bytes and compare with a direct sign via eth_account — should match.
    direct = Account.from_key(_TEST_PRIVKEY).sign_transaction(unsigned)
    direct_raw = direct.rawTransaction if hasattr(direct, "rawTransaction") else direct.raw_transaction
    direct_hex = direct_raw.hex()
    if not direct_hex.startswith("0x"):
        direct_hex = "0x" + direct_hex
    assert raw_hex == direct_hex


def test_sign_unknown_wallet_raises(temp_db, stub_keyring):
    from src.services.wallet_manager import sign
    from src.shared.errors import WalletNotFound

    with pytest.raises(WalletNotFound):
        sign({"nonce": 0}, "0x" + "33" * 20)


def test_sign_message_round_trip(temp_db, stub_keyring, mock_sdk_create):
    from eth_account.messages import encode_defunct

    from src.services.wallet_manager import create_wallet, sign_message

    create_wallet(chain="evm", network="testnet", chain_id=84532)
    sig_hex = sign_message("hello", _TEST_ADDRESS)
    assert sig_hex.startswith("0x")

    # Recover the signer and confirm it matches.
    recovered = Account.recover_message(encode_defunct(text="hello"), signature=sig_hex)
    assert recovered.lower() == _TEST_ADDRESS.lower()


# -- wallet_exists -----------------------------------------------------------


def test_wallet_exists(temp_db, stub_keyring, mock_sdk_create):
    from src.services.wallet_manager import create_wallet, wallet_exists

    assert not wallet_exists(_TEST_ADDRESS)
    create_wallet(chain="evm", network="testnet", chain_id=84532)
    assert wallet_exists(_TEST_ADDRESS)


# -- payload normalization (regression — caught by the real Base mainnet swap)


def test_normalize_coerces_stringified_numerics():
    from src.services.wallet_manager import _normalize_payload

    sdk_payload = {
        "to": "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
        "data": "0x095ea7b3",
        "value": "0",
        "gas": 60000,
        "nonce": 26,
        "maxPriorityFeePerGas": "1000000",
        "maxFeePerGas": "11000000",
    }
    out = _normalize_payload(sdk_payload, chain_id=8453)
    assert out["value"] == 0
    assert out["maxFeePerGas"] == 11_000_000
    assert out["maxPriorityFeePerGas"] == 1_000_000
    assert out["chainId"] == 8453  # injected
    assert out["type"] == 2         # eip-1559
    assert out["to"] == "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"  # checksum


def test_normalize_drops_null_fields_for_legacy_tx():
    """prepare_swap returns legacy (gasPrice populated, EIP-1559 nulls).
    eth_account validator rejects `maxFeePerGas=None`, so we drop them."""
    from src.services.wallet_manager import _normalize_payload

    sdk_payload = {
        "to": "0x111111125421ca6dc452d289314280a0f8842a65",
        "data": "0xabcdef",
        "value": "0",
        "gas": 207909,
        "nonce": 28,
        "gasPrice": "7800000",
        "maxFeePerGas": None,
        "maxPriorityFeePerGas": None,
    }
    out = _normalize_payload(sdk_payload, chain_id=8453)
    assert out["gasPrice"] == 7_800_000
    assert "maxFeePerGas" not in out
    assert "maxPriorityFeePerGas" not in out
    assert "type" not in out  # legacy tx, no type marker


def test_normalize_no_chain_id_injection_if_already_present():
    from src.services.wallet_manager import _normalize_payload

    out = _normalize_payload({"chainId": 1, "value": 0}, chain_id=8453)
    assert out["chainId"] == 1  # caller's value wins


def test_normalize_raises_nothing_when_chain_id_omitted():
    """Caller may sign without chainId — eth_account handles that."""
    from src.services.wallet_manager import _normalize_payload

    out = _normalize_payload({"value": "0"})
    assert out["value"] == 0
    assert "chainId" not in out


def test_sign_accepts_sdk_style_payload_with_chain_id(temp_db, stub_keyring, mock_sdk_create):
    """End-to-end: wallet_manager.sign accepts a payload shaped exactly like
    what mangrovemarkets SDK returns (stringified numerics, no chainId)."""
    from src.services.wallet_manager import create_wallet, sign

    create_wallet(chain="evm", network="testnet", chain_id=84532)

    sdk_style_payload = {
        "to": "0x" + "22" * 20,
        "data": "0x",
        "value": "0",
        "gas": 21000,
        "nonce": 0,
        "maxPriorityFeePerGas": "1000000",
        "maxFeePerGas": "11000000",
        # Note: NO chainId. Agent must inject it.
    }
    raw = sign(sdk_style_payload, _TEST_ADDRESS, chain_id=84532)
    assert raw.startswith("0x")
    # Signed tx must encode chainId=84532 (0x14a34). After tx type byte (02)
    # and RLP list prefix, the first list element is chainId. Quick sanity:
    # not the chainId=0 signature bug we hit on the real swap.
    assert "021482" not in raw[:20]  # would be chainId=0 (01 48 = type+empty)


# -- SecretVault flow (phase-2 contract: plaintext never in MCP responses) ----


def test_secret_vault_single_read(temp_db, stub_keyring):
    from src.services.secret_vault import vault

    sid = vault.stash("hello-world")
    assert vault.reveal(sid) == "hello-world"
    # Second read fails — single-read semantics.
    with pytest.raises(KeyError):
        vault.reveal(sid)


def test_stash_external_secret_then_import(temp_db, stub_keyring):
    """End-to-end for the CLI-stash-then-MCP-import flow."""
    from src.services.wallet_manager import import_wallet, stash_external_secret
    from src.shared.db.sqlite import get_connection

    sid = stash_external_secret(_TEST_PRIVKEY)
    assert sid

    response = import_wallet(secret_id=sid, chain="evm", network="testnet", chain_id=84532)
    assert response.address == _TEST_ADDRESS
    # Imported wallets auto-confirm backup (user typed the key into the CLI,
    # so they have it off-agent by definition).
    assert response.backup_required is False

    row = get_connection().execute(
        "SELECT backup_confirmed_at FROM wallets WHERE address=?",
        (_TEST_ADDRESS,),
    ).fetchone()
    assert row["backup_confirmed_at"] is not None


def test_import_wallet_expired_secret_id_raises(temp_db, stub_keyring):
    from src.services.wallet_manager import import_wallet
    from src.shared.errors import SigningError

    with pytest.raises(SigningError, match="unknown or has expired"):
        import_wallet(secret_id="bogus-id-that-was-never-stashed")


def test_reveal_wallet_secret_roundtrip(temp_db, stub_keyring, mock_sdk_create):
    """reveal_wallet_secret decrypts from DB — used by the reveal-by-address CLI."""
    from src.services.wallet_manager import create_wallet, reveal_wallet_secret

    create_wallet(chain="evm", network="testnet", chain_id=84532)
    result = reveal_wallet_secret(_TEST_ADDRESS)
    assert result.secret == _TEST_PRIVKEY
    assert result.address == _TEST_ADDRESS


# -- Backup gate (phase-2 contract: live trading refuses on unconfirmed wallets) -


def test_require_backup_confirmed_null_raises(temp_db, stub_keyring, mock_sdk_create):
    from src.services.wallet_manager import create_wallet, require_backup_confirmed
    from src.shared.errors import SigningError

    create_wallet(chain="evm", network="testnet", chain_id=84532)
    # Fresh wallet, no backup confirmation → must raise.
    with pytest.raises(SigningError, match="not backed up"):
        require_backup_confirmed(_TEST_ADDRESS)


def test_confirm_backup_unlocks(temp_db, stub_keyring, mock_sdk_create):
    from src.services.wallet_manager import (
        confirm_backup,
        create_wallet,
        require_backup_confirmed,
    )

    create_wallet(chain="evm", network="testnet", chain_id=84532)
    item = confirm_backup(_TEST_ADDRESS)
    assert item.backup_confirmed_at is not None
    # After confirmation, the gate is open.
    require_backup_confirmed(_TEST_ADDRESS)  # must not raise


def test_confirm_backup_unknown_wallet_raises(temp_db, stub_keyring):
    from src.services.wallet_manager import confirm_backup
    from src.shared.errors import WalletNotFound

    with pytest.raises(WalletNotFound):
        confirm_backup("0x" + "99" * 20)


# -- Fernet keyfile + guard (phase-1 contract: never silently regenerate) ------


def test_fernet_never_silently_regenerates_with_stubbed_keyring(tmp_path, monkeypatch):
    """If a keyfile exists, fernet MUST return that key, not generate a new one."""
    from cryptography.fernet import Fernet

    from src.config import app_config
    from src.shared.crypto import fernet as f

    # Write a known keyfile.
    key_path = tmp_path / "master.key"
    known_key = Fernet.generate_key()
    key_path.write_bytes(known_key)
    key_path.chmod(0o600)

    monkeypatch.setattr(app_config, "MASTER_KEY_PATH", str(key_path))
    f.reset_master_key_cache()

    assert f.get_master_key() == known_key
    assert f.get_master_key_source() == "keyfile"

    f.reset_master_key_cache()
