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
    from src.services.wallet_manager import create_wallet
    from src.shared.db.sqlite import get_connection

    response = create_wallet(chain="evm", network="testnet", chain_id=84532, label="test")
    assert response.address == _TEST_ADDRESS
    assert response.seed_phrase == _TEST_PRIVKEY
    assert "chat transcript" in response.warning  # security warning present

    row = get_connection().execute(
        "SELECT address, chain, chain_id, label, encrypted_secret, encryption_method FROM wallets WHERE address=?",
        (_TEST_ADDRESS,),
    ).fetchone()
    assert row["chain"] == "evm"
    assert row["chain_id"] == 84532
    assert row["label"] == "test"
    assert row["encrypted_secret"] != _TEST_PRIVKEY.encode()  # actually encrypted
    assert row["encryption_method"] == "fernet-v1"


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
