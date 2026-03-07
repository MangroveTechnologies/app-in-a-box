"""Easter egg service -- the fun part.

Returns a thank-you message to supporters. Available via x402 payment
or API key. Proves the payment pipeline works end-to-end.
"""
from datetime import datetime, timezone


def get_easter_egg() -> dict:
    return {
        "message": "Thank you for supporting the project and strengthening the ecosystem",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
