"""Tests for x402 payment models and config."""
import os
os.environ.setdefault("ENVIRONMENT", "test")

from src.shared.x402.models import PaymentOption, PaymentRequirements
from src.shared.x402.config import EASTER_EGG_PRICE, PAY_TO, NETWORK, USDC_BASE, FACILITATOR_URL


def test_payment_option_serialization():
    opt = PaymentOption(
        scheme="exact",
        network="base",
        asset=USDC_BASE,
        pay_to=PAY_TO,
        max_amount_required=EASTER_EGG_PRICE,
        description="test",
        facilitator_url=FACILITATOR_URL,
    )
    dumped = opt.model_dump(by_alias=True)
    assert dumped["payTo"] == PAY_TO
    assert dumped["maxAmountRequired"] == EASTER_EGG_PRICE
    assert dumped["facilitatorUrl"] == FACILITATOR_URL


def test_payment_requirements_structure():
    reqs = PaymentRequirements(
        accepts=[],
        tool_name="test_tool",
        tool_args_hash="abc123",
    )
    assert reqs.tool_name == "test_tool"
    assert reqs.tool_args_hash == "abc123"


def test_easter_egg_config_values():
    assert EASTER_EGG_PRICE == "50000"
    assert PAY_TO == "0xdAC6843ccA8B8c127d9d10EdB327fb0ddb2a5576"
    # NETWORK is CAIP-2 format, set via env var (defaults to mainnet)
    assert NETWORK.startswith("eip155:")
    # USDC_BASE auto-selects based on network
    assert USDC_BASE in [
        "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",  # mainnet
        "0x036CbD53842c5426634e7929541eC2318f3dCF7e",  # sepolia
    ]
