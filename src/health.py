"""Health check endpoint."""
from datetime import datetime, timezone


def health_payload() -> dict:
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
