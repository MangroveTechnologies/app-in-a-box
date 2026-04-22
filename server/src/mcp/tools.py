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
        api_key: str = "",
    ) -> str:
        """Get a swap quote."""
        if not _require(api_key):
            return _auth_error()
        try:
            from src.shared.clients.mangrove import mangrovemarkets_client
            q = mangrovemarkets_client().dex.get_quote(
                input_token=input_token, output_token=output_token,
                amount=amount, chain_id=chain_id, venue_id=venue_id,
            )
            return json.dumps(_dump(q))
        except AgentError as e:
            return _handle_agent_error(e)

    register_tool(ToolEntry(
        name="get_swap_quote",
        description="Get a DEX swap quote.",
        access="auth",
        parameters=[
            ToolParam(name="input_token", type="string", required=True, description="Input token"),
            ToolParam(name="output_token", type="string", required=True, description="Output token"),
            ToolParam(name="amount", type="number", required=True, description="Input amount"),
            ToolParam(name="chain_id", type="integer", required=True, description="EVM chain id"),
            ToolParam(name="venue_id", type="string", required=False, description="Optional specific venue"),
            _APIKEY,
        ],
    ))

    @server.tool()
    async def execute_swap(
        input_token: str, output_token: str, amount: float,
        chain_id: int, wallet_address: str,
        slippage: float = 1.0, venue_id: str | None = None,
        confirm: bool = False,
        api_key: str = "",
    ) -> str:
        """Execute a swap. Requires confirm=true. Full 6-step flow with
        client-side signing; SDK never sees keys."""
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
                                chain_id=chain_id, venue_id=venue_id)
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
        description="Execute a DEX swap (requires confirm=true). Single code path shared with cron-driven trades.",
        access="auth",
        parameters=[
            ToolParam(name="input_token", type="string", required=True, description="Input token"),
            ToolParam(name="output_token", type="string", required=True, description="Output token"),
            ToolParam(name="amount", type="number", required=True, description="Input amount"),
            ToolParam(name="chain_id", type="integer", required=True, description="EVM chain id"),
            ToolParam(name="wallet_address", type="string", required=True, description="Wallet from local store"),
            ToolParam(name="slippage", type="number", required=False, description="Slippage % (default 1.0)"),
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
    async def get_ohlcv(symbol: str, timeframe: str = "1h",
                        lookback_days: int = 30, api_key: str = "") -> str:
        """OHLCV bars for an asset."""
        if not _require(api_key):
            return _auth_error()
        from src.shared.clients.mangrove import mangroveai_client
        try:
            result = mangroveai_client().crypto_assets.get_ohlcv(
                symbol=symbol, timeframe=timeframe, days=lookback_days,
            )
        except TypeError:
            result = mangroveai_client().crypto_assets.get_ohlcv(symbol)
        return json.dumps(_dump(result))

    register_tool(ToolEntry(
        name="get_ohlcv",
        description="OHLCV bars for an asset.",
        access="auth",
        parameters=[
            ToolParam(name="symbol", type="string", required=True, description="Asset symbol"),
            ToolParam(name="timeframe", type="string", required=False, description="1m | 5m | 15m | 1h | 4h | 1d"),
            ToolParam(name="lookback_days", type="integer", required=False, description="History window in days"),
            _APIKEY,
        ],
    ))

    @server.tool()
    async def get_market_data(symbol: str, api_key: str = "") -> str:
        """Current market data for an asset."""
        if not _require(api_key):
            return _auth_error()
        from src.shared.clients.mangrove import mangroveai_client
        return json.dumps(_dump(mangroveai_client().crypto_assets.get_market_data(symbol)))

    register_tool(ToolEntry(
        name="get_market_data",
        description="Current price, market cap, volume, 24h/7d change.",
        access="auth",
        parameters=[
            ToolParam(name="symbol", type="string", required=True, description="Asset symbol"),
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
        else:
            page = client.signals.list(limit=limit)
        items = [_dump(s) for s in getattr(page, "items", [])]
        if category:
            items = [s for s in items if (s.get("category") or "").lower() == category.lower()]
        return json.dumps({"items": items, "total": getattr(page, "total", len(items))})

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
            ToolParam(name="timeframe", type="string", required=True, description="1m | 5m | 15m | 1h | 4h | 1d"),
            ToolParam(name="candidate_count", type="integer", required=False, description="5-10"),
            ToolParam(name="backtest_lookback_months", type="integer", required=False, description="Default 3"),
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
            ToolParam(name="timeframe", type="string", required=True, description="Timeframe"),
            ToolParam(name="entry", type="array", required=True, description="Entry rules"),
            ToolParam(name="exit", type="array", required=False, description="Exit rules"),
            ToolParam(name="execution_config", type="object", required=False, description="Override exec params"),
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
        lookback_months: int = 3,
        start_date: str | None = None, end_date: str | None = None,
        api_key: str = "",
    ) -> str:
        """Run a backtest against an existing strategy (mode=quick|full)."""
        if not _require(api_key):
            return _auth_error()
        try:
            from src.api.routes.strategies import BacktestInput, backtest
            return json.dumps(await backtest(strategy_id, BacktestInput(
                mode=mode, lookback_months=lookback_months,
                start_date=start_date, end_date=end_date,
            )))
        except AgentError as e:
            return _handle_agent_error(e)

    register_tool(ToolEntry(
        name="backtest_strategy",
        description="Backtest a strategy (quick or full).",
        access="auth",
        parameters=[
            ToolParam(name="strategy_id", type="string", required=True, description="Agent strategy UUID"),
            ToolParam(name="mode", type="string", required=False, description="quick | full"),
            ToolParam(name="lookback_months", type="integer", required=False, description="Default 3"),
            ToolParam(name="start_date", type="string", required=False, description="ISO 8601"),
            ToolParam(name="end_date", type="string", required=False, description="ISO 8601"),
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
    @server.tool()
    async def hello_mangrove(payment: str = "") -> str:
        """x402 demo tool. $0.05 USDC on Base. Smoke test for the payment path."""
        if payment:
            from src.shared.x402.server import verify_and_settle_payment
            settlement = await verify_and_settle_payment(payment)
            if settlement.get("error"):
                return json.dumps(settlement)
            from src.services.hello_mangrove import get_hello_mangrove
            result = get_hello_mangrove()
            result["settlement"] = settlement
            return json.dumps(result)
        from src.shared.x402.server import build_hello_mangrove_requirements
        return json.dumps(build_hello_mangrove_requirements())

    register_tool(ToolEntry(
        name="hello_mangrove",
        description="x402 demo: $0.05 USDC on Base. Smoke test for the payment path.",
        access="x402",
        price="$0.05 USDC",
        network="base",
        parameters=[
            ToolParam(
                name="payment", type="string", required=False,
                description="Base64-encoded x402 payment signature. Call with no parameters to get payment requirements.",
            ),
        ],
    ))
