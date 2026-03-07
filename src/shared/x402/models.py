"""x402 payment data models."""
from pydantic import Field
from src.shared.types import AppBaseModel


class PaymentOption(AppBaseModel):
    model_config = AppBaseModel.model_config.copy()
    model_config["populate_by_name"] = True

    scheme: str = Field(description="Payment scheme: 'exact'")
    network: str = Field(description="Target network: 'base'")
    asset: str = Field(description="Token contract address")
    pay_to: str = Field(alias="payTo", description="Recipient address")
    max_amount_required: str = Field(alias="maxAmountRequired", description="Required amount in base units")
    description: str = Field(description="What this payment covers")
    facilitator_url: str = Field(alias="facilitatorUrl", description="Facilitator URL for verify/settle")


class PaymentRequirements(AppBaseModel):
    accepts: list[PaymentOption]
    tool_name: str = Field(description="Name of the tool/endpoint requiring payment")
    tool_args_hash: str = Field(description="SHA-256 hash of request args")


class PaymentProof(AppBaseModel):
    scheme: str
    network: str
    payload: str = Field(description="Base64-encoded signed payment authorization")


class SettlementReceipt(AppBaseModel):
    tx_hash: str
    network: str
    settled_amount: str
    settled_asset: str
    facilitator: str
    timestamp: str
