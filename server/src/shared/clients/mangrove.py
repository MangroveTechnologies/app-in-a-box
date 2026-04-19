"""SDK client singletons — mangroveai + mangrovemarkets.

Both clients are initialized lazily on first access and cached for the
lifetime of the process. Routes and services import the accessors, never
instantiate clients themselves. That keeps test mocking easy (override the
@lru_cache'd function) and avoids multiple HTTP pools / auth re-inits.

Usage:
    from src.shared.clients.mangrove import mangroveai_client, mangrovemarkets_client

    signals = mangroveai_client().signals.list()
    venues = mangrovemarkets_client().dex.supported_venues()
"""
from __future__ import annotations

from functools import lru_cache

from mangroveai import MangroveAI
from mangrovemarkets import MangroveMarkets


def _get_config():
    """Lazy import to avoid circular imports during testing."""
    from src.config import app_config
    return app_config


@lru_cache(maxsize=1)
def mangroveai_client() -> MangroveAI:
    """Return the singleton MangroveAI SDK client.

    Reads MANGROVE_API_KEY from config. Environment (dev vs prod) is
    auto-detected by the SDK from the API key prefix (dev_* / prod_*).
    """
    config = _get_config()
    return MangroveAI(api_key=str(config.MANGROVE_API_KEY))


@lru_cache(maxsize=1)
def mangrovemarkets_client() -> MangroveMarkets:
    """Return the singleton MangroveMarkets SDK client.

    Reads MANGROVEMARKETS_BASE_URL and MANGROVE_API_KEY from config. The
    base URL points at the MangroveMarkets MCP server (DEX + wallet +
    portfolio endpoints).
    """
    config = _get_config()
    return MangroveMarkets(
        base_url=str(config.MANGROVEMARKETS_BASE_URL),
        api_key=str(config.MANGROVE_API_KEY),
    )


def reset_clients() -> None:
    """Clear the cached singletons. Tests use this to re-init with different config."""
    mangroveai_client.cache_clear()
    mangrovemarkets_client.cache_clear()
