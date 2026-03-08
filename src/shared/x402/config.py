"""x402 payment configuration for this service.

Supports two facilitators:
- CDP (production): https://api.cdp.coinbase.com/platform/v2/x402
  Requires CDP_API_KEY_ID + CDP_API_KEY_SECRET. Supports Base mainnet.
- x402.org (testnet): https://x402.org/facilitator
  No API key required. Base Sepolia only.

Set X402_FACILITATOR_URL and X402_NETWORK env vars to switch.
"""
import os

# Facilitator URL -- defaults to CDP production facilitator
# Override with X402_FACILITATOR_URL env var
# CDP mainnet: https://api.cdp.coinbase.com/platform/v2/x402
# Testnet: https://x402.org/facilitator
FACILITATOR_URL = os.environ.get(
    "X402_FACILITATOR_URL",
    "https://api.cdp.coinbase.com/platform/v2/x402",
)

# Network -- defaults to Base mainnet
# Override with X402_NETWORK env var
# Base mainnet: eip155:8453
# Base Sepolia: eip155:84532
NETWORK = os.environ.get("X402_NETWORK", "eip155:8453")

# Base mainnet USDC contract address
USDC_BASE_MAINNET = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
# Base Sepolia USDC contract address
USDC_BASE_SEPOLIA = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"

# Auto-select USDC contract based on network
USDC_BASE = USDC_BASE_SEPOLIA if "84532" in NETWORK else USDC_BASE_MAINNET

# Deposit address for x402 payments (where money goes TO)
PAY_TO = "0xdAC6843ccA8B8c127d9d10EdB327fb0ddb2a5576"

# Price in USDC base units (6 decimals). $0.05 = 50000
EASTER_EGG_PRICE = "50000"
EASTER_EGG_DESCRIPTION = "Easter egg message -- thank you for supporting the project"
