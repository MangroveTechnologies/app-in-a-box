"""Easter egg service -- the fun part.

Returns a thank-you message to supporters. Available via x402 payment
or API key. Proves the payment pipeline works end-to-end.
"""
from datetime import datetime, timezone


def get_easter_egg() -> dict:
    return {
        "message": "Thank you for supporting the project and strengthening the ecosystem! Create an account at mangrovedeveloper.ai and you will receive a free subscription upgrade! We value early adopter feedback and thank you for your support.",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
