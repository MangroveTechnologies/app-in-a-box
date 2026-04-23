"""MCP tool definitions for the defi-agent.

Every tool mirrors a REST route by calling the same service function.
Zero duplicated business logic — the MCP layer is just a different
interface over the same code.

Auth: tools accept an `api_key` parameter; `has_valid_api_key` validates
against config. Returns the spec-shaped `AgentError` JSON on failure.
Discovery tools (`status`, `list_tools`) bypass auth.

Naming: plain verb_resource form (no project prefix). The MCP server
namespace is enough. See docs/specification.md MCP Tools table.
"""
from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from src.mcp.registry import ToolEntry, ToolParam, clear_tools, register_tool
from src.shared.auth.middleware import has_valid_api_key
from src.shared.errors import AgentError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _err(code: str, message: str, suggestion: str | None = None, status: int = 400) -> str:
    return json.dumps({
        "error": True,
        "code": code,
        "message": message,
        "suggestion": suggestion,
        "correlation_id": None,
    })


def _auth_error() -> str:
    return _err(
        "AUTH_INVALID_API_KEY",
        "API key required or invalid.",
        "Pass a valid api_key parameter matching the configured API_KEYS.",
        status=401,
    )


def _handle_agent_error(e: AgentError) -> str:
    return json.dumps(e.to_dict())


def _dump(obj: Any) -> Any:
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if isinstance(obj, list):
        return [_dump(x) for x in obj]
    return obj


def _require(api_key: str) -> bool:
    """Return True if api_key is valid, False otherwise."""
    return has_valid_api_key(api_key)


# Shorthand for the "api_key required" parameter in the discovery catalog.
_APIKEY = ToolParam(name="api_key", type="string", required=True, description="Valid API key")


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register(server: FastMCP):
    """Register all agent MCP tools + the x402 demo tool."""
    clear_tools()
    _register_discovery(server)
    _register_wallet(server)
    _register_dex(server)
    _register_market(server)
    _register_signals(server)
    _register_strategy(server)
    _register_logs(server)
    _register_kb(server)
    _register_hello_mangrove(server)


# ---------------------------------------------------------------------------
# Discovery (free)
# ---------------------------------------------------------------------------


def _register_discovery(server: FastMCP) -> None:
    @server.tool()
    async def status() -> str:
        """Return agent status: version, wallets count, strategies by status,
        active cron jobs, db path, uptime. Free, no auth required."""
        from src.api.routes.discovery import status as route
        return json.dumps(await route())

    register_tool(ToolEntry(
        name="status",
        description="Agent status + counts + uptime. Free, no auth.",
        access="free",
        parameters=[],
    ))

    @server.tool()
    async def list_tools() -> str:
        """List all registered MCP tools with their access tier, parameters,
        and pricing. Free, no auth."""
        from src.api.routes.discovery import tools as route
        return json.dumps(await route())

    register_tool(ToolEntry(
        name="list_tools",
        description="MCP tool catalog (name, tier, params, pricing). Free, no auth.",
        access="free",
        parameters=[],
    ))


# ---------------------------------------------------------------------------
# Wallet (auth)
# ---------------------------------------------------------------------------


def _register_wallet(server: FastMCP) -> None:
    @server.tool()
    async def create_wallet(
        chain: str = "evm", network: str = "mainnet",
        chain_id: int | None = 8453, label: str | None = None,
        api_key: str = "",
    ) -> str:
        """Create + encrypt a wallet locally.

        The plaintext secret is NEVER returned in this response — it would
        land in the Claude Code transcript and get sent to Anthropic. Instead
        the response carries a `secret_id` referencing an in-process vault.
        Tell the user to run the `reveal_cmd` in a terminal to back up the
        secret. The id is TTL-bound (default 300s) and single-read.
        EVM only in v1. Base mainnet (chain_id 8453) is the default.
        """
        if not _require(api_key):
            return _auth_error()
        try:
            from src.services.wallet_manager import create_wallet as svc
            result = svc(chain=chain, network=network, chain_id=chain_id, label=label)
            return json.dumps(result.model_dump(mode="json"))
        except AgentError as e:
            return _handle_agent_error(e)

    register_tool(ToolEntry(
        name="create_wallet",
        description=(
            "Create + encrypt a wallet. Response carries only secret_id + "
            "reveal_cmd — plaintext never enters the Claude Code transcript. "
            "EVM only in v1."
        ),
        access="auth",
        parameters=[
            ToolParam(name="chain", type="string", required=False, description="evm (default). xrpl stubbed 501 in v1."),
            ToolParam(name="network", type="string", required=False, description="mainnet (default) | testnet"),
            ToolParam(name="chain_id", type="integer", required=False, description="Default 8453 (Base mainnet)"),
            ToolParam(name="label", type="string", required=False, description="Human-friendly name"),
            _APIKEY,
        ],
    ))

    @server.tool()
    async def import_wallet(
        secret_id: str,
        chain: str = "evm", network: str = "mainnet",
        chain_id: int | None = 8453, label: str | None = None,
        api_key: str = "",
    ) -> str:
        """Import an existing wallet whose secret has been stashed in the vault.

        The user's flow: run `./scripts/stash-secret.sh` in a terminal (it
        prompts for the private key via `read -s` so it isn't echoed, posts
        to /internal/stash-secret, prints the returned secret_id). Then
        tell the agent to import that id. The private key NEVER enters
        Claude Code's conversation context — this tool only handles the id.

        Do NOT accept a raw private key or mnemonic as input to this tool,
        and do NOT suggest the user paste one. If a user pastes a key in
        chat, tell them to run stash-secret.sh instead and purge the key
        from their message.
        """
        if not _require(api_key):
            return _auth_error()
        try:
            from src.services.wallet_manager import import_wallet as svc
            result = svc(
                secret_id=secret_id,
                chain=chain, network=network,
                chain_id=chain_id, label=label,
            )
            return json.dumps(result.model_dump(mode="json"))
        except AgentError as e:
            return _handle_agent_error(e)

    register_tool(ToolEntry(
        name="import_wallet",
        description=(
            "Import an existing wallet from a stashed secret_id. The user "
            "must obtain the id by running scripts/stash-secret.sh in a "
            "terminal FIRST — this tool refuses raw keys by design."
        ),
        access="auth",
        parameters=[
            ToolParam(name="secret_id", type="string", required=True, description="From scripts/stash-secret.sh output"),
            ToolParam(name="chain", type="string", required=False, description="evm (default)"),
            ToolParam(name="network", type="string", required=False, description="mainnet (default) | testnet"),
            ToolParam(name="chain_id", type="integer", required=False, description="Default 8453 (Base mainnet)"),
            ToolParam(name="label", type="string", required=False, description="Human-friendly name"),
            _APIKEY,
        ],
    ))

    @server.tool()
    async def list_wallets(api_key: str = "") -> str:
        """List stored wallets (addresses + metadata only)."""
        if not _require(api_key):
            return _auth_error()
        from src.services.wallet_manager import list_wallets as svc
        return json.dumps([w.model_dump(mode="json") for w in svc()])

    register_tool(ToolEntry(
        name="list_wallets",
        description="List stored wallets (secrets never returned).",
        access="auth",
        parameters=[_APIKEY],
    ))

    @server.tool()
    async def get_balances(address: str, chain_id: int, api_key: str = "") -> str:
        """Token balances for a wallet via mangrovemarkets.dex.balances."""
        if not _require(api_key):
            return _auth_error()
        try:
            from src.shared.clients.mangrove import mangrovemarkets_client
            result = mangrovemarkets_client().dex.balances(chain_id=chain_id, wallet=address)
            return json.dumps(_dump(result))
        except AgentError as e:
            return _handle_agent_error(e)

    register_tool(ToolEntry(
        name="get_balances",
        description="Token balances for a wallet.",
        access="auth",
        parameters=[
            ToolParam(name="address", type="string", required=True, description="Wallet address"),
            ToolParam(name="chain_id", type="integer", required=True, description="EVM chain id"),
            _APIKEY,
        ],
    ))


# ---------------------------------------------------------------------------
# DEX (auth)
# ---------------------------------------------------------------------------


def _register_dex(server: FastMCP) -> None:
    @server.tool()
    async def list_dex_venues(api_key: str = "") -> str:
        """List supported DEX venues."""
        if not _require(api_key):
            return _auth_error()
        from src.shared.clients.mangrove import mangrovemarkets_client
        venues = mangrovemarkets_client().dex.supported_venues()
        return json.dumps([_dump(v) for v in venues])

    register_tool(ToolEntry(
        name="list_dex_venues",
        description="List supported DEX venues.",
        access="auth",
        parameters=[_APIKEY],
    ))

    @server.tool()
    async def get_swap_quote(
        input_token: str, output_token: str, amount: float,
        chain_id: int, venue_id: str | None = None,
        mode: str | None = None,
        api_key: str = "",
    ) -> str:
        """Get a DEX swap quote.

        Mirrors `mangrovemarkets.dex.get_quote(input_token, output_token,
        amount, venue_id, chain_id, mode)`. `mode` is an optional
        routing hint recognized by some venues (e.g. 1inch supports
        modes that bias for gas-cost vs price-improvement).
        """
        if not _require(api_key):
            return _auth_error()
        try:
            from src.shared.clients.mangrove import mangrovemarkets_client
            kwargs: dict[str, Any] = {
                "input_token": input_token,
                "output_token": output_token,
                "amount": amount,
                "chain_id": chain_id,
                "venue_id": venue_id,
            }
            if mode is not None:
                kwargs["mode"] = mode
            q = mangrovemarkets_client().dex.get_quote(**kwargs)
            return json.dumps(_dump(q))
        except AgentError as e:
            return _handle_agent_error(e)

    register_tool(ToolEntry(
        name="get_swap_quote",
        description="Get a DEX swap quote. Optionally pin a venue + mode.",
        access="auth",
        parameters=[
            ToolParam(name="input_token", type="string", required=True, description="Input token"),
            ToolParam(name="output_token", type="string", required=True, description="Output token"),
            ToolParam(name="amount", type="number", required=True, description="Input amount"),
            ToolParam(name="chain_id", type="integer", required=True, description="EVM chain id"),
            ToolParam(name="venue_id", type="string", required=False, description="Optional specific venue"),
            ToolParam(name="mode", type="string", required=False, description="Optional routing hint (venue-specific)"),
            _APIKEY,
        ],
    ))

    @server.tool()
    async def execute_swap(
        input_token: str, output_token: str, amount: float,
        chain_id: int, wallet_address: str, slippage_pct: float,
        venue_id: str | None = None,
        confirm: bool = False,
        api_key: str = "",
    ) -> str:
        """Execute a swap. Requires confirm=true + explicit slippage_pct.

        Full 6-step flow with client-side signing; SDK never sees keys.

        `slippage_pct` is REQUIRED and specified as a DECIMAL, capped
        at 0.0025 (0.25%). Typical values: 0.001 (0.1%), 0.002 (0.2%),
        0.0025 (0.25% = max). Higher values are refused to prevent
        rekt-on-illiquid-pair execution. No default — picking a
        slippage tolerance is a risk decision the user must make
        explicitly. Converted to the upstream percentage convention
        (multiplied by 100) at the `dex.prepare_swap()` boundary.
        """
        if not _require(api_key):
            return _auth_error()
        try:
            from src.models.domain import OrderIntent
            from src.services.order_executor import execute_one
            from src.shared.errors import ConfirmationRequired
            if not confirm:
                raise ConfirmationRequired(
                    "DEX swaps require confirm=true.",
                    suggestion="Re-invoke with confirm=true.",
                )
            side = "sell" if output_token.upper() == "USDC" else "buy"
            symbol = input_token if side == "sell" else output_token
            intent = OrderIntent(action="enter", side=side, symbol=symbol,
                                 amount=amount, reason="user-initiated")
            trade = execute_one(intent, mode="live",
                                wallet_address=wallet_address,
                                chain_id=chain_id, venue_id=venue_id,
                                slippage_pct=slippage_pct)
            return json.dumps({
                "tx_hash": trade.tx_hash, "status": trade.status,
                "input_token": trade.input_token, "input_amount": trade.input_amount,
                "output_token": trade.output_token, "output_amount": trade.output_amount,
                "fill_price": trade.fill_price, "fees": trade.fees,
                "trade_log_id": trade.id,
            })
        except AgentError as e:
            return _handle_agent_error(e)

    register_tool(ToolEntry(
        name="execute_swap",
        description=(
            "Execute a DEX swap (requires confirm=true + explicit "
            "slippage_pct). Single code path shared with cron-driven "
            "trades. Slippage is always user-specified — no default — "
            "because picking a tolerance is a risk decision."
        ),
        access="auth",
        parameters=[
            ToolParam(name="input_token", type="string", required=True, description="Input token"),
            ToolParam(name="output_token", type="string", required=True, description="Output token"),
            ToolParam(name="amount", type="number", required=True, description="Input amount"),
            ToolParam(name="chain_id", type="integer", required=True, description="EVM chain id"),
            ToolParam(name="wallet_address", type="string", required=True, description="Wallet from local store"),
            ToolParam(name="slippage_pct", type="number", required=True, description="Slippage tolerance as DECIMAL, capped at 0.0025 (0.25%). Typical: 0.001 (0.1%), 0.002 (0.2%), 0.0025 (max). Higher values refused."),
            ToolParam(name="venue_id", type="string", required=False, description="Optional specific venue"),
            ToolParam(name="confirm", type="boolean", required=True, description="Must be true"),
            _APIKEY,
        ],
    ))


# ---------------------------------------------------------------------------
# Market data (auth)
# ---------------------------------------------------------------------------


def _register_market(server: FastMCP) -> None:
    @server.tool()
    async def get_ohlcv(symbol: str, lookback_days: int = 30,
                        provider: str | None = None,
                        api_key: str = "") -> str:
        """OHLCV bars for an asset.

        Thin wrapper over `mangroveai.crypto_assets.get_ohlcv(symbol, days,
        provider)`. The SDK does NOT accept a timeframe — the upstream
        endpoint returns the provider's native bar granularity (1h for
        most). A previous version of this tool advertised a `timeframe`
        parameter; it was silently dropped by the SDK. Removed to stop
        misleading callers.
        """
        if not _require(api_key):
            return _auth_error()
        from src.shared.clients.mangrove import mangroveai_client
        kwargs: dict[str, Any] = {"symbol": symbol, "days": lookback_days}
        if provider is not None:
            kwargs["provider"] = provider
        result = mangroveai_client().crypto_assets.get_ohlcv(**kwargs)
        return json.dumps(_dump(result))

    register_tool(ToolEntry(
        name="get_ohlcv",
        description=(
            "OHLCV bars for an asset. Bar granularity is set by the "
            "data provider (typically 1h). No `timeframe` parameter — "
            "the SDK / upstream endpoint don't support overriding bar "
            "size at this call site."
        ),
        access="auth",
        parameters=[
            ToolParam(name="symbol", type="string", required=True, description="Asset symbol (e.g. BTC, ETH)"),
            ToolParam(name="lookback_days", type="integer", required=False, description="History window in days (default 30)"),
            ToolParam(name="provider", type="string", required=False, description="Optional CEX provider override"),
            _APIKEY,
        ],
    ))

    @server.tool()
    async def get_market_data(
        symbol: str, provider: str | None = None, api_key: str = "",
    ) -> str:
        """Current market data for an asset.

        Thin wrapper over `mangroveai.crypto_assets.get_market_data(symbol,
        *, provider)`. `provider` selects a specific data source; omit to
        use the SDK default.
        """
        if not _require(api_key):
            return _auth_error()
        from src.shared.clients.mangrove import mangroveai_client
        kwargs: dict[str, Any] = {"symbol": symbol}
        if provider is not None:
            kwargs["provider"] = provider
        return json.dumps(_dump(mangroveai_client().crypto_assets.get_market_data(**kwargs)))

    register_tool(ToolEntry(
        name="get_market_data",
        description="Current price, market cap, volume, 24h/7d change. Optionally pin a provider.",
        access="auth",
        parameters=[
            ToolParam(name="symbol", type="string", required=True, description="Asset symbol"),
            ToolParam(name="provider", type="string", required=False, description="Optional data provider override"),
            _APIKEY,
        ],
    ))


# ---------------------------------------------------------------------------
# Signals (auth)
# ---------------------------------------------------------------------------


def _register_signals(server: FastMCP) -> None:
    @server.tool()
    async def list_signals(category: str | None = None, search: str | None = None,
                           limit: int = 50, api_key: str = "") -> str:
        """List available signals (optionally filtered by category or search)."""
        if not _require(api_key):
            return _auth_error()
        from src.shared.clients.mangrove import mangroveai_client
        client = mangroveai_client()
        if search:
            from mangroveai.models import SearchSignalsRequest
            page = client.signals.search(SearchSignalsRequest(query=search, limit=limit))
            items = [_dump(s) for s in getattr(page, "items", [])]
        else:
            all_signals = list(client.signals.list_iter(limit_per_page=min(limit, 100)))
            items = [_dump(s) for s in all_signals[:limit]]
        if category:
            items = [s for s in items if (s.get("category") or "").lower() == category.lower()]
        return json.dumps({"items": items, "total": len(items)})

    register_tool(ToolEntry(
        name="list_signals",
        description="List / search available signals.",
        access="auth",
        parameters=[
            ToolParam(name="category", type="string", required=False, description="Filter by category"),
            ToolParam(name="search", type="string", required=False, description="Search query"),
            ToolParam(name="limit", type="integer", required=False, description="Max results"),
            _APIKEY,
        ],
    ))


# ---------------------------------------------------------------------------
# Strategy (auth)
# ---------------------------------------------------------------------------


def _register_strategy(server: FastMCP) -> None:
    @server.tool()
    async def create_strategy_autonomous(
        goal: str, asset: str, timeframe: str,
        candidate_count: int = 7, backtest_lookback_months: int = 3,
        seed: int | None = None, api_key: str = "",
    ) -> str:
        """Autonomous strategy creation: goal → candidates → backtest → rank → winner."""
        if not _require(api_key):
            return _auth_error()
        try:
            from src.services.strategy_service import (
                StrategyAutonomousRequest,
                create_autonomous,
            )
            detail, report = create_autonomous(StrategyAutonomousRequest(
                goal=goal, asset=asset, timeframe=timeframe,
                candidate_count=candidate_count,
                backtest_lookback_months=backtest_lookback_months,
                seed=seed,
            ))
            return json.dumps({"strategy": detail.model_dump(mode="json"),
                               "generation_report": report})
        except AgentError as e:
            return _handle_agent_error(e)

    register_tool(ToolEntry(
        name="create_strategy_autonomous",
        description="Create a strategy from a natural-language goal.",
        access="auth",
        parameters=[
            ToolParam(name="goal", type="string", required=True, description="Natural-language goal"),
            ToolParam(name="asset", type="string", required=True, description="Asset symbol"),
            ToolParam(name="timeframe", type="string", required=True, description="5m | 15m | 30m | 1h | 4h | 1d (1m not supported)"),
            ToolParam(name="candidate_count", type="integer", required=False, description="5-10"),
            ToolParam(name="backtest_lookback_months", type="integer", required=False, description="Default: auto by timeframe (5m-1h=3mo, 4h=6mo, 1d=12mo)"),
            ToolParam(name="seed", type="integer", required=False, description="Reproducibility seed"),
            _APIKEY,
        ],
    ))

    @server.tool()
    async def create_strategy_manual(
        name: str, asset: str, timeframe: str,
        entry: list[dict], exit: list[dict] | None = None,
        execution_config: dict | None = None, api_key: str = "",
    ) -> str:
        """Manual strategy creation with explicit rules."""
        if not _require(api_key):
            return _auth_error()
        try:
            from src.services.strategy_service import (
                StrategyManualRequest,
                create_manual,
            )
            detail = create_manual(StrategyManualRequest(
                name=name, asset=asset, timeframe=timeframe,
                entry=entry, exit=exit or [],
                execution_config=execution_config,
            ))
            return json.dumps(detail.model_dump(mode="json"))
        except AgentError as e:
            return _handle_agent_error(e)

    register_tool(ToolEntry(
        name="create_strategy_manual",
        description="Create a strategy with explicit entry/exit rules.",
        access="auth",
        parameters=[
            ToolParam(name="name", type="string", required=True, description="Strategy name"),
            ToolParam(name="asset", type="string", required=True, description="Asset symbol"),
            ToolParam(name="timeframe", type="string", required=True, description="5m | 15m | 30m | 1h | 4h | 1d (1m not supported)"),
            ToolParam(name="entry", type="array", required=True, description="Entry rules"),
            ToolParam(name="exit", type="array", required=False, description="Exit rules"),
            ToolParam(name="execution_config", type="object", required=False, description="Override exec params"),
            _APIKEY,
        ],
    ))

    @server.tool()
    async def search_reference_strategies(
        asset: str,
        timeframe: str | None = None,
        category: str | None = None,
        goal_hint: str | None = None,
        limit: int = 5,
        api_key: str = "",
    ) -> str:
        """Search curated reference strategies — Mechanism 2 of /create-strategy.

        The agent calls this BEFORE picking signals/params manually. Each
        returned reference has known-good entry/exit signals + parameter
        choices. The agent picks one that matches user intent, then calls
        build_strategy_from_reference to materialize it.

        Ranks by specificity: asset+timeframe+category > asset+timeframe
        > asset > category. Auto-detects category from goal_hint if not
        supplied.
        """
        if not _require(api_key):
            return _auth_error()
        from src.services import reference_strategies_service
        items = reference_strategies_service.search(
            asset=asset,
            timeframe=timeframe,
            category=category,
            goal_hint=goal_hint,
            limit=limit,
        )
        return json.dumps({
            "asset": asset.upper(),
            "timeframe": timeframe,
            "category": category,
            "count": len(items),
            "strategies": [r.model_dump() for r in items],
        })

    register_tool(ToolEntry(
        name="search_reference_strategies",
        description=(
            "Find curated reference strategies that match the user's goal "
            "and asset. Returns ranked candidates with signals + parameter "
            "choices that have worked in backtests. ALWAYS call this "
            "before picking signals manually — it's the primary source of "
            "parameter intuition."
        ),
        access="auth",
        parameters=[
            ToolParam(name="asset", type="string", required=True, description="Asset symbol (e.g. BTC, ETH)"),
            ToolParam(name="timeframe", type="string", required=False, description="5m | 15m | 30m | 1h | 4h | 1d"),
            ToolParam(name="category", type="string", required=False, description="momentum | mean_reversion | trend_following | breakout | volatility"),
            ToolParam(name="goal_hint", type="string", required=False, description="Free text from the user's goal — auto-detects category if category is not supplied"),
            ToolParam(name="limit", type="integer", required=False, description="Max results (default 5)"),
            _APIKEY,
        ],
    ))

    @server.tool()
    async def build_strategy_from_reference(
        reference_id: str,
        timeframe: str | None = None,
        name: str | None = None,
        api_key: str = "",
    ) -> str:
        """Materialize a reference into a create_strategy_manual payload.

        Called after search_reference_strategies + user pick. Copies the
        reference's signals EXACTLY (parameters untouched) and only
        rewrites each signal's timeframe if overridden. Returns a payload
        the caller passes straight to create_strategy_manual.
        """
        if not _require(api_key):
            return _auth_error()
        from src.services import reference_strategies_service
        try:
            payload = reference_strategies_service.build_from_reference(
                reference_id=reference_id,
                timeframe_override=timeframe,
                name=name,
            )
        except ValueError as e:
            return json.dumps({"error": str(e), "code": "REFERENCE_NOT_FOUND"})
        return json.dumps(payload)

    register_tool(ToolEntry(
        name="build_strategy_from_reference",
        description=(
            "After search_reference_strategies returns candidates and the "
            "user picks one, call this to produce a create_strategy_manual "
            "payload. Signals and params are copied exactly — the agent "
            "must NOT modify them. Only timeframe and name can be overridden."
        ),
        access="auth",
        parameters=[
            ToolParam(name="reference_id", type="string", required=True, description="e.g. ref-001 — from search_reference_strategies"),
            ToolParam(name="timeframe", type="string", required=False, description="Override the reference's timeframe (canonicalized)"),
            ToolParam(name="name", type="string", required=False, description="Optional strategy name override"),
            _APIKEY,
        ],
    ))

    @server.tool()
    async def list_strategies(status: str | None = None, limit: int = 50,
                              offset: int = 0, api_key: str = "") -> str:
        """List strategies, optionally filtered by status."""
        if not _require(api_key):
            return _auth_error()
        from src.services.strategy_service import list_strategies as svc
        items = svc(status=status, limit=limit, offset=offset)
        return json.dumps([s.model_dump(mode="json") for s in items])

    register_tool(ToolEntry(
        name="list_strategies",
        description="List strategies.",
        access="auth",
        parameters=[
            ToolParam(name="status", type="string", required=False, description="Filter: draft|inactive|paper|live|archived"),
            ToolParam(name="limit", type="integer", required=False, description="Page size"),
            ToolParam(name="offset", type="integer", required=False, description="Page offset"),
            _APIKEY,
        ],
    ))

    @server.tool()
    async def get_strategy(strategy_id: str, api_key: str = "") -> str:
        """Get a strategy by ID."""
        if not _require(api_key):
            return _auth_error()
        try:
            from src.services.strategy_service import get_strategy as svc
            return json.dumps(svc(strategy_id).model_dump(mode="json"))
        except AgentError as e:
            return _handle_agent_error(e)

    register_tool(ToolEntry(
        name="get_strategy",
        description="Get a strategy by ID.",
        access="auth",
        parameters=[
            ToolParam(name="strategy_id", type="string", required=True, description="Agent strategy UUID"),
            _APIKEY,
        ],
    ))

    @server.tool()
    async def update_strategy_status(
        strategy_id: str, status: str, confirm: bool = False,
        allocation: dict | None = None, api_key: str = "",
    ) -> str:
        """Transition strategy status. live + live→inactive require confirm=true;
        live requires an allocation block."""
        if not _require(api_key):
            return _auth_error()
        try:
            from src.services.strategy_service import (
                StrategyAllocationInput,
                StrategyStatusUpdate,
                update_status,
            )
            alloc = StrategyAllocationInput(**allocation) if allocation else None
            detail = update_status(strategy_id, StrategyStatusUpdate(
                status=status, confirm=confirm, allocation=alloc,
            ))
            return json.dumps(detail.model_dump(mode="json"))
        except AgentError as e:
            return _handle_agent_error(e)

    register_tool(ToolEntry(
        name="update_strategy_status",
        description="Transition strategy lifecycle status.",
        access="auth",
        parameters=[
            ToolParam(name="strategy_id", type="string", required=True, description="Agent strategy UUID"),
            ToolParam(name="status", type="string", required=True, description="Target status"),
            ToolParam(name="confirm", type="boolean", required=False, description="Required for live + live→inactive"),
            ToolParam(name="allocation", type="object", required=False, description="Required for live"),
            _APIKEY,
        ],
    ))

    @server.tool()
    async def backtest_strategy(
        strategy_id: str, mode: str = "full",
        lookback_months: int | None = None,
        lookback_days: int | None = None,
        lookback_hours: int | None = None,
        start_date: str | None = None, end_date: str | None = None,
        config: dict | None = None,
        api_key: str = "",
    ) -> str:
        """Run a backtest against an existing strategy (mode=quick|full).

        Window resolution (first non-null wins):
          start_date+end_date > lookback_hours > lookback_days
          > lookback_months > timeframes.recommended_lookback_months
          (5m/15m/30m/1h → 3 mo, 4h → 6 mo, 1d → 12 mo).

        `config` is a single dict that merges over the canonical
        trading_defaults.json. Any SDK BacktestRequest field is valid —
        slippage_pct, fee_pct, max_hold_time_hours, initial_balance,
        max_risk_per_trade, reward_factor, atr_period, etc. Omit the
        argument entirely to get a pure trading-defaults backtest.
        """
        if not _require(api_key):
            return _auth_error()
        try:
            from src.api.routes.strategies import BacktestInput, backtest
            return json.dumps(await backtest(strategy_id, BacktestInput(
                mode=mode,
                lookback_months=lookback_months,
                lookback_days=lookback_days,
                lookback_hours=lookback_hours,
                start_date=start_date,
                end_date=end_date,
                config=config,
            )))
        except AgentError as e:
            return _handle_agent_error(e)

    register_tool(ToolEntry(
        name="backtest_strategy",
        description=(
            "Backtest a strategy (quick or full). Window precedence: "
            "start+end > hours > days > months > timeframe-aware auto "
            "(5m-1h=3mo, 4h=6mo, 1d=12mo). `config` is a single dict "
            "that merges over trading_defaults.json — use it for "
            "slippage_pct, fee_pct, max_hold_time_hours, initial_balance, "
            "max_risk_per_trade, reward_factor, atr_period, or any other "
            "BacktestRequest field. Returns full SDK metrics, trade "
            "history, and a resolved_window block for fallback detection."
        ),
        access="auth",
        parameters=[
            ToolParam(name="strategy_id", type="string", required=True, description="Agent strategy UUID"),
            ToolParam(name="mode", type="string", required=False, description="quick | full (default full)"),
            ToolParam(name="lookback_months", type="integer", required=False, description="Window in months (auto by timeframe if all window fields omitted)"),
            ToolParam(name="lookback_days", type="integer", required=False, description="Window in days (overrides lookback_months)"),
            ToolParam(name="lookback_hours", type="integer", required=False, description="Window in hours — use for short backtests"),
            ToolParam(name="start_date", type="string", required=False, description="ISO 8601 — paired with end_date, overrides all lookback_* fields"),
            ToolParam(name="end_date", type="string", required=False, description="ISO 8601"),
            ToolParam(name="config", type="object", required=False, description="Merges over trading_defaults.json (slippage_pct, max_risk_per_trade, initial_balance, reward_factor, atr_*, etc.)"),
            _APIKEY,
        ],
    ))

    @server.tool()
    async def evaluate_strategy(strategy_id: str, api_key: str = "") -> str:
        """Manually trigger a single evaluation tick."""
        if not _require(api_key):
            return _auth_error()
        try:
            from src.api.routes.strategies import evaluate
            return json.dumps(await evaluate(strategy_id))
        except AgentError as e:
            return _handle_agent_error(e)

    register_tool(ToolEntry(
        name="evaluate_strategy",
        description="Manually trigger one evaluation tick.",
        access="auth",
        parameters=[
            ToolParam(name="strategy_id", type="string", required=True, description="Agent strategy UUID"),
            _APIKEY,
        ],
    ))


# ---------------------------------------------------------------------------
# Logs (auth)
# ---------------------------------------------------------------------------


def _register_logs(server: FastMCP) -> None:
    @server.tool()
    async def list_evaluations(strategy_id: str, limit: int = 50,
                                offset: int = 0, api_key: str = "") -> str:
        """Evaluation log for a strategy."""
        if not _require(api_key):
            return _auth_error()
        from src.services.trade_log import list_evaluations as svc
        return json.dumps([e.model_dump(mode="json") for e in
                           svc(strategy_id, limit=limit, offset=offset)])

    register_tool(ToolEntry(
        name="list_evaluations",
        description="Evaluation log for a strategy.",
        access="auth",
        parameters=[
            ToolParam(name="strategy_id", type="string", required=True, description="Strategy UUID"),
            ToolParam(name="limit", type="integer", required=False, description="Page size"),
            ToolParam(name="offset", type="integer", required=False, description="Page offset"),
            _APIKEY,
        ],
    ))

    @server.tool()
    async def list_trades(strategy_id: str, limit: int = 50,
                          offset: int = 0, api_key: str = "") -> str:
        """Trades for a strategy."""
        if not _require(api_key):
            return _auth_error()
        from src.services.trade_log import list_trades as svc
        return json.dumps([t.model_dump(mode="json") for t in
                           svc(strategy_id, limit=limit, offset=offset)])

    register_tool(ToolEntry(
        name="list_trades",
        description="Trades for a strategy.",
        access="auth",
        parameters=[
            ToolParam(name="strategy_id", type="string", required=True, description="Strategy UUID"),
            ToolParam(name="limit", type="integer", required=False, description="Page size"),
            ToolParam(name="offset", type="integer", required=False, description="Page offset"),
            _APIKEY,
        ],
    ))

    @server.tool()
    async def list_all_trades(limit: int = 50,
                               strategy_id: str | None = None,
                               mode: str | None = None,
                               api_key: str = "") -> str:
        """All trades across strategies."""
        if not _require(api_key):
            return _auth_error()
        from src.services.trade_log import list_all_trades as svc
        return json.dumps([t.model_dump(mode="json") for t in
                           svc(limit=limit, strategy_id=strategy_id, mode=mode)])  # type: ignore[arg-type]

    register_tool(ToolEntry(
        name="list_all_trades",
        description="All trades across strategies (optional filters).",
        access="auth",
        parameters=[
            ToolParam(name="limit", type="integer", required=False, description="Max results"),
            ToolParam(name="strategy_id", type="string", required=False, description="Filter"),
            ToolParam(name="mode", type="string", required=False, description="live | paper"),
            _APIKEY,
        ],
    ))


# ---------------------------------------------------------------------------
# Knowledge Base (auth)
# ---------------------------------------------------------------------------


def _register_kb(server: FastMCP) -> None:
    @server.tool()
    async def kb_search(q: str, limit: int = 20, api_key: str = "") -> str:
        """Full-text search the knowledge base."""
        if not _require(api_key):
            return _auth_error()
        from src.shared.clients.mangrove import mangroveai_client
        return json.dumps(_dump(mangroveai_client().kb.search.query(q=q, limit=limit)))

    register_tool(ToolEntry(
        name="kb_search",
        description="Full-text KB search.",
        access="auth",
        parameters=[
            ToolParam(name="q", type="string", required=True, description="Search query"),
            ToolParam(name="limit", type="integer", required=False, description="Max results"),
            _APIKEY,
        ],
    ))


# ---------------------------------------------------------------------------
# x402 demo (unchanged)
# ---------------------------------------------------------------------------


def _register_hello_mangrove(server: FastMCP) -> None:
    """Register hello_mangrove via the x402 library's MCP payment wrapper.

    The wrapper intercepts tool calls, reads payment from MCP ``_meta``, verifies
    and settles via the shared x402ResourceServer, and attaches the settlement
    receipt to the result's ``_meta``. Clients using ``x402.mcp.x402MCPClient``
    auto-handle the empty-payment -> sign -> retry round-trip.
    """
    from x402 import ResourceConfig
    from x402.mcp import create_payment_wrapper
    from x402.schemas import ResourceInfo as X402ResourceInfo

    from src.services.hello_mangrove import get_hello_mangrove as _impl
    from src.shared.x402.config import get_network, get_pay_to
    from src.shared.x402.server import _ensure_initialized

    resource_server = _ensure_initialized()
    accepts = resource_server.build_payment_requirements(
        ResourceConfig(
            scheme="exact",
            network=get_network(),
            pay_to=get_pay_to(),
            price="$0.05",
        )
    )

    wrapper = create_payment_wrapper(
        resource_server,
        accepts=accepts,
        resource=X402ResourceInfo(
            url="mcp://hello_mangrove",
            description="hello_mangrove message — $0.05 USDC donation",
        ),
    )

    @server.tool(
        name="hello_mangrove",
        description="x402 demo: $0.05 USDC on Base. Smoke test for the payment path.",
    )
    @wrapper
    async def hello_mangrove() -> str:
        return json.dumps(_impl())

    register_tool(ToolEntry(
        name="hello_mangrove",
        description="x402 demo: $0.05 USDC on Base. Smoke test for the payment path.",
        access="x402",
        price="$0.05 USDC",
        network="base",
        parameters=[],
    ))
