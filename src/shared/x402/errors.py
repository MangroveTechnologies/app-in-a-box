"""x402 error hierarchy."""


class X402Error(Exception):
    def __init__(self, code: str, message: str, suggestion: str = ""):
        self.code = code
        self.message = message
        self.suggestion = suggestion
        super().__init__(message)


class FacilitatorUnreachableError(X402Error):
    def __init__(self, url: str):
        super().__init__("FACILITATOR_UNREACHABLE", f"Cannot reach facilitator at {url}", "Try again later or check facilitator status.")


class PaymentInvalidError(X402Error):
    def __init__(self, detail: str):
        super().__init__("PAYMENT_INVALID", f"Payment verification failed: {detail}", "Ensure payment proof is correctly signed and has sufficient funds.")


class SettlementFailedError(X402Error):
    def __init__(self, detail: str):
        super().__init__("SETTLEMENT_FAILED", f"Settlement failed: {detail}", "The tool executed but settlement is pending. Check your wallet.")


class PaymentNetworkMismatchError(X402Error):
    def __init__(self, got: str, expected: list[str]):
        super().__init__("PAYMENT_NETWORK_MISMATCH", f"Payment network '{got}' not accepted. Expected one of: {expected}", f"Use one of: {', '.join(expected)}")
