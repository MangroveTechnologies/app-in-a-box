"""Tests for x402 payment models and config."""
import os
os.environ.setdefault("ENVIRONMENT", "test")

from src.shared.x402.models import PaymentOption, PaymentRequirements
from src.shared.x402.config import (
    get_facilitator_url, get_network, get_pay_to,
    get_usdc_contract, get_easter_egg_price,
)


def test_payment_option_serialization():
    opt = PaymentOption(
        scheme="exact",
        network="eip155:84532",
        asset=get_usdc_contract(),
        pay_to=get_pay_to(),
        max_amount_required=get_easter_egg_price(),
        description="test",
        facilitator_url=get_facilitator_url(),
    )
    dumped = opt.model_dump(by_alias=True)
    assert dumped["payTo"] == get_pay_to()
    assert dumped["maxAmountRequired"] == get_easter_egg_price()
    assert dumped["facilitatorUrl"] == get_facilitator_url()


def test_payment_requirements_structure():
    reqs = PaymentRequirements(
        accepts=[],
        tool_name="test_tool",
        tool_args_hash="abc123",
    )
    assert reqs.tool_name == "test_tool"
    assert reqs.tool_args_hash == "abc123"


def test_config_values_loaded_from_json():
    """All x402 config values come from test-config.json, not hardcoded."""
    assert get_easter_egg_price() == "50000"
    assert get_pay_to() == "0xdAC6843ccA8B8c127d9d10EdB327fb0ddb2a5576"
    assert get_network().startswith("eip155:")
    assert get_facilitator_url().startswith("https://")
    assert get_usdc_contract().startswith("0x")
