"""Tests for x402 config system.

Verifies that all x402 config values are loaded from the JSON config file
via the app_config singleton. No hardcoded values, no env var overrides.
"""
import os

os.environ.setdefault("ENVIRONMENT", "test")

from src.shared.x402.config import (
    get_cdp_api_key_id,
    get_cdp_api_key_secret,
    get_easter_egg_price,
    get_facilitator_url,
    get_network,
    get_pay_to,
    get_usdc_contract,
)


def test_config_values_loaded_from_json():
    """All x402 config values come from test-config.json."""
    assert get_easter_egg_price() == "50000"
    assert get_pay_to().startswith("0x")
    assert len(get_pay_to()) == 42
    assert get_network().startswith("eip155:")
    assert get_facilitator_url().startswith("https://")
    assert get_usdc_contract().startswith("0x")


def test_facilitator_url_is_valid():
    url = get_facilitator_url()
    assert url in [
        "https://x402.org/facilitator",
        "https://api.cdp.coinbase.com/platform/v2/x402",
    ]


def test_network_is_caip2_format():
    network = get_network()
    assert network.startswith("eip155:")
    chain_id = network.split(":")[1]
    assert chain_id.isdigit()


def test_cdp_keys_are_strings():
    assert isinstance(get_cdp_api_key_id(), str)
    assert isinstance(get_cdp_api_key_secret(), str)
