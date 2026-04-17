# Technical Specification: Hank (defi-agent)

**Generated:** 2026-04-17
**Status:** Draft
**Based on:** `docs/user-stories.md` (approved requirements)

## Overview

Hank is a FastAPI + MCP service that wraps the `mangroveai` and `mangrovemarkets` Python SDKs with local state, autonomous strategy generation, cron-based execution, and a full audit trail.

Hank exposes the same functionality two ways:
- **MCP tools at `/mcp`** (Streamable HTTP transport) — preferred for AI agents because of structured tool discovery and typed invocation.
- **REST endpoints at `/api/v1/hank/*`** — universal; any HTTP client (Python scripts, cron jobs, curl, notebooks, tests) can use them without an MCP library.

Both protocols share a single service layer — `create_wallet` (MCP tool) and `POST /api/v1/hank/wallet/create` (REST endpoint) call the same Python function. No duplicated business logic.

Hank is single-user and **local-first**. It runs on the user's own machine via Docker Compose — no cloud account required. It holds wallet keys locally (encrypted), registers APScheduler cron jobs at strategy activation, and logs every evaluation and trade to local SQLite.

### Deployment modes

| Mode | State persistence | Requirements | Use case |
|------|-------------------|--------------|----------|
| **Local (default)** | `hank.db` in user's filesystem — persists across restarts | Docker Compose, Python 3.10+ | Daily use, development, real trading |
| **Cloud Run (optional, demo)** | `hank.db` in ephemeral container filesystem — **wiped on every redeploy** | GCP account (optional) | Workshop demo only; fresh state each session |
| **Cloud Run (persistent)** | **Not v1.** Requires swapping SQLite for Cloud SQL or mounting a GCS volume | — | Future |

**Most users will run Hank locally.** No GCP/AWS account is required. The Cloud Run option exists only for demo scenarios (e.g., the April 24 workshop) where a throwaway public URL is useful. If a user deploys to Cloud Run and redeploys, all state is lost by design — persistent cloud deploy is out of scope for v1.

## Access Tiers

| Tier | Endpoints | How to access |
|------|-----------|---------------|
| Free | `/health`, `/api/v1/hank/tools`, `/api/v1/hank/status` | No credentials |
| Auth | Everything else | `X-API-Key: $HANK_API_KEY` header |
| x402 | None (v1) | — |

Single-user model: `HANK_API_KEY` is a shared secret between the user's Claude Code config and Hank. No RBAC, no user accounts.

---

## API Contracts

All endpoints are JSON over HTTPS. Base path: `/api/v1/hank`. Every endpoint has a mirrored MCP tool with identical semantics (see [MCP Tools](#mcp-tools)).

### Discovery (free)

#### `GET /health`
Returns `{ status, service, version, timestamp }`. Used by Cloud Run health checks.

#### `GET /api/v1/hank/tools`
Returns the full MCP tool catalog (tool names, descriptions, parameters, access tier).

#### `GET /api/v1/hank/status`
Returns service state:
```json
{
  "version": "0.1.0",
  "wallets_count": 2,
  "strategies": {"draft": 3, "inactive": 1, "paper": 2, "live": 1, "archived": 5},
  "active_cron_jobs": 3,
  "db_path": "./hank.db",
  "uptime_seconds": 12345
}
```

---

### Wallet (auth)

#### `POST /api/v1/hank/wallet/create`
Create + encrypt + store a wallet locally.

**Request:**
```json
{
  "chain": "string — evm | xrpl",
  "network": "string — mainnet | testnet",
  "chain_id": "int | null — required for evm",
  "label": "string | null — human-friendly name"
}
```

**Response (201):**
```json
{
  "address": "string — public address",
  "chain": "string",
  "network": "string",
  "chain_id": "int | null",
  "label": "string | null",
  "created_at": "string — ISO 8601",
  "warning": "string — reminder that keys are stored locally encrypted; user should back up their seed phrase shown in the chat"
}
```

**Security warning returned in `warning` field and also logged to stdout:**

> The seed phrase is shown **once** in the response, then encrypted to disk. Never retrievable via API after creation.
>
> ⚠️ **Important:** the seed phrase will appear in your chat transcript, which Claude Code writes to disk under `~/.claude/projects/.../*.jsonl`. If you do not want the seed phrase persisted there, (1) copy it to a secure location, (2) delete the corresponding session transcript file, and (3) back it up offline (paper, hardware wallet, password manager). Never screenshot without securing the image.

**Errors:** 400 `VALIDATION_ERROR`, 409 `WALLET_ALREADY_EXISTS`, 502 `SDK_ERROR`.

#### `GET /api/v1/hank/wallet/list`
List all stored wallets (addresses + metadata only, no keys).

#### `GET /api/v1/hank/wallet/{address}/balances?chain_id=<int>`
Returns token balances via `mangrovemarkets.dex.balances()`.

#### `GET /api/v1/hank/wallet/{address}/portfolio?chain_id=<int>`
Returns aggregate portfolio: value, P&L, tokens, DeFi positions (via `mangrovemarkets.portfolio.*`).

#### `GET /api/v1/hank/wallet/{address}/history?limit=<int>`
Returns transaction history via `mangrovemarkets.portfolio.history()`.

---

### DEX (auth)

#### `GET /api/v1/hank/dex/venues`
List supported DEX venues via `mangrovemarkets.dex.supported_venues()`.

#### `GET /api/v1/hank/dex/pairs?venue_id=<str>`
List trading pairs for a venue.

#### `POST /api/v1/hank/dex/quote`
**Request:**
```json
{
  "input_token": "string — token address or symbol",
  "output_token": "string",
  "amount": "number — in base units of input_token",
  "chain_id": "int",
  "venue_id": "string | null — null = best across venues"
}
```
**Response (200):** Mirrors `mangrovemarkets.dex.Quote` model.

#### `POST /api/v1/hank/dex/swap`
Execute the full 6-step swap flow. **Requires `confirm: true`** in the request body — protects against agent-initiated swaps without user approval.

**Request:**
```json
{
  "input_token": "string",
  "output_token": "string",
  "amount": "number",
  "chain_id": "int",
  "wallet_address": "string — must be in Hank's wallet store",
  "slippage": "number — default 1.0 (percent)",
  "mev_protection": "boolean — default false",
  "confirm": "boolean — must be true"
}
```

**Response (200):**
```json
{
  "tx_hash": "string",
  "status": "string — confirmed | pending",
  "input_amount": "number",
  "output_amount": "number",
  "fill_price": "number",
  "fees": "object",
  "approval_tx_hash": "string | null",
  "trade_log_id": "string — UUID in Hank's local trades table"
}
```

Internal flow: quote → `approve_token` (returns None if already approved) → sign approval if returned → broadcast → wait → `prepare_swap` → sign locally → `broadcast` → poll `tx_status` until confirmed → log to SQLite.

**Errors:** 400 `VALIDATION_ERROR`, 400 `CONFIRMATION_REQUIRED`, 404 `WALLET_NOT_FOUND`, 502 `SDK_ERROR`, 500 `SIGNING_ERROR`.

---

### Market Data (auth)

#### `GET /api/v1/hank/market/ohlcv?symbol=<str>&timeframe=<str>&lookback_days=<int>`
Returns OHLCV via `mangroveai.crypto_assets.get_ohlcv()`.

#### `GET /api/v1/hank/market/data?symbol=<str>`
Current market data (price, market cap, volume, 24h/7d change).

#### `GET /api/v1/hank/market/trending`
Trending assets.

#### `GET /api/v1/hank/market/global`
Global market cap, BTC dominance, 24h change.

#### `GET /api/v1/hank/on-chain/smart-money?symbol=<str>&chain=<str>`
Smart money sentiment via `mangroveai.on_chain.get_smart_money_sentiment()`.

#### `GET /api/v1/hank/on-chain/whale-activity?symbol=<str>&hours_back=<int>`
Whale activity summary.

#### `GET /api/v1/hank/on-chain/token-holders/{symbol}`
Holder distribution and concentration.

---

### Signals (auth)

#### `GET /api/v1/hank/signals?category=<str>&search=<str>&limit=<int>`
List/search signals via `mangroveai.signals.list()` with optional filtering.

#### `GET /api/v1/hank/signals/{name}`
Signal detail with parameter spec.

---

### Strategies (auth)

#### `POST /api/v1/hank/strategies/autonomous`
Autonomous strategy creation: skill picks candidates → quick backtest → filter → rank by IRR → full backtest → persist.

**Request:**
```json
{
  "goal": "string — natural-language goal, e.g. 'Trade ETH on momentum breakouts with tight stops'",
  "asset": "string",
  "timeframe": "string — 1m | 5m | 15m | 1h | 4h | 1d",
  "candidate_count": "int — default 7, range [5, 10]",
  "backtest_lookback_months": "int — default 3"
}
```

**Response (201):**
```json
{
  "strategy": { ... full StrategyDetail ... },
  "generation_report": {
    "candidates_tried": 7,
    "candidates_passed_filter": 3,
    "winner_rank": 1,
    "full_backtest_metrics": {
      "irr_annualized": 0.42,
      "sharpe_ratio": 1.8,
      "max_drawdown": 0.12,
      "win_rate": 0.58,
      "total_trades": 47
    },
    "rejected_reasons": [
      {"candidate": "...", "reason": "win_rate 0.48 < 0.51"},
      ...
    ]
  }
}
```

**Errors:** 400 `VALIDATION_ERROR`, 422 `STRATEGY_NO_VIABLE_CANDIDATES`, 502 `SDK_ERROR`.

#### `POST /api/v1/hank/strategies/manual`
Manual strategy creation with explicit entry/exit rules.

**Request:**
```json
{
  "name": "string",
  "asset": "string",
  "timeframe": "string",
  "entry": [
    {
      "name": "string — signal name",
      "signal_type": "string — TRIGGER | FILTER",
      "params": "object"
    }
  ],
  "exit": [ ... ],
  "execution_config": "object | null — null = Mangrove defaults"
}
```

**Response (201):** Full `StrategyDetail`.

Validation: entry must be exactly 1 TRIGGER + 0+ FILTERs; exit must be 0–1 TRIGGERs + 0+ FILTERs.

#### `GET /api/v1/hank/strategies?status=<str>&limit=<int>&offset=<int>`
List strategies with optional status filter.

#### `GET /api/v1/hank/strategies/{id}`
Full strategy details.

#### `PATCH /api/v1/hank/strategies/{id}/status`
**Single source of truth for strategy lifecycle.** This is the only way to activate, deactivate, or archive a strategy. Side effects (register/cancel cron jobs, allocate/release funds) are driven by the status transition.

**Request:**
```json
{
  "status": "string — draft | inactive | paper | live | archived",
  "confirm": "boolean — required when activating to live or deactivating a live strategy",
  "allocation": {
    "wallet_address": "string — required when transitioning to live",
    "token": "string — token address or symbol",
    "amount": "number"
  }
}
```

Valid transitions: `draft → inactive`, `inactive → paper`, `inactive → live`, `paper → live`, `paper → inactive`, `live → inactive`, `* → archived`.

Side effects by target status:
- `paper`: register APScheduler cron job keyed to strategy timeframe. Allocation field ignored.
- `live`: require `confirm: true` AND `allocation` block. Record allocation in local DB. Register cron job.
- `inactive` (from live): require `confirm: true`. Cancel cron job. Release allocation (mark `active=false`, set `released_at`).
- `inactive` (from paper): cancel cron job. No allocation change.
- `archived`: cancel any running cron job. Release allocation if active.

**Errors:** 400 `STRATEGY_INVALID_STATUS_TRANSITION`, 400 `CONFIRMATION_REQUIRED`, 400 `ALLOCATION_INSUFFICIENT`, 404 `WALLET_NOT_FOUND`.

#### `POST /api/v1/hank/strategies/{id}/backtest`
**Request:**
```json
{
  "mode": "string — quick | full",
  "lookback_months": "int — default 3",
  "start_date": "string | null — ISO 8601",
  "end_date": "string | null"
}
```
**Response:** Full backtest metrics + trade history.

#### `POST /api/v1/hank/strategies/{id}/evaluate`
Manually trigger a single evaluation tick (for debugging/power users). Same code path the cron job runs.

---

### Execution Logs (auth)

#### `GET /api/v1/hank/strategies/{id}/evaluations?limit=<int>&offset=<int>`
Returns evaluation log for a strategy, newest first.

#### `GET /api/v1/hank/strategies/{id}/trades?limit=<int>&offset=<int>`
Returns trades for a strategy, newest first.

#### `GET /api/v1/hank/trades?limit=<int>&strategy_id=<str>&mode=<str>`
All trades across strategies, with optional filters.

---

### Knowledge Base (auth)

#### `GET /api/v1/hank/kb/search?q=<str>&limit=<int>`
Full-text search via `mangroveai.kb.search.*`.

#### `GET /api/v1/hank/kb/glossary/{term}`
Glossary term lookup with backlinks.

---

## MCP Tools

Every REST endpoint has a mirrored MCP tool with identical semantics. Tool names use plain `verb_resource` form (e.g. `create_strategy_autonomous`, `list_trades`, `get_market_data`) — no `hank_` prefix; the MCP server namespace is enough.

Tool descriptions include parameters, return shapes, and access tier. All tools enforce the same auth as their REST counterparts.

### v1 scope — core vs nice-to-have

**Core (must work for a demoable trading bot, ~22 tools):**

| Category | Tool | REST endpoint |
|----------|------|---------------|
| Discovery | `status` | `GET /status` |
| Discovery | `list_tools` | `GET /tools` |
| Wallet | `create_wallet` | `POST /wallet/create` |
| Wallet | `list_wallets` | `GET /wallet/list` |
| Wallet | `get_balances` | `GET /wallet/{a}/balances` |
| DEX | `list_dex_venues` | `GET /dex/venues` |
| DEX | `get_swap_quote` | `POST /dex/quote` |
| DEX | `execute_swap` | `POST /dex/swap` |
| Market | `get_ohlcv` | `GET /market/ohlcv` |
| Market | `get_market_data` | `GET /market/data` |
| Signals | `list_signals` | `GET /signals` |
| Strategy | `create_strategy_autonomous` | `POST /strategies/autonomous` |
| Strategy | `create_strategy_manual` | `POST /strategies/manual` |
| Strategy | `list_strategies` | `GET /strategies` |
| Strategy | `get_strategy` | `GET /strategies/{id}` |
| Strategy | `update_strategy_status` | `PATCH /strategies/{id}/status` |
| Strategy | `backtest_strategy` | `POST /strategies/{id}/backtest` |
| Strategy | `evaluate_strategy` | `POST /strategies/{id}/evaluate` |
| Logs | `list_evaluations` | `GET /strategies/{id}/evaluations` |
| Logs | `list_trades` | `GET /strategies/{id}/trades` |
| Logs | `list_all_trades` | `GET /trades` |
| KB | `kb_search` | `GET /kb/search` |

**Nice-to-have (extend after core ships):**

| Category | Tool | REST endpoint |
|----------|------|---------------|
| Wallet | `get_portfolio` | `GET /wallet/{a}/portfolio` |
| Wallet | `get_history` | `GET /wallet/{a}/history` |
| DEX | `list_dex_pairs` | `GET /dex/pairs` |
| Market | `get_trending` | `GET /market/trending` |
| Market | `get_global_market` | `GET /market/global` |
| On-chain | `get_smart_money` | `GET /on-chain/smart-money` |
| On-chain | `get_whale_activity` | `GET /on-chain/whale-activity` |
| On-chain | `get_token_holders` | `GET /on-chain/token-holders/{s}` |
| Signals | `get_signal` | `GET /signals/{name}` |
| KB | `kb_glossary` | `GET /kb/glossary/{term}` |

Cut list rationale: the core 22 are enough to demo "autonomously create, backtest, deploy, and execute a strategy" end-to-end. The 10 nice-to-haves are research/analytics surface that the user can reach via other Mangrove tooling if needed.

---

## Data Models

### Pydantic request/response models

```python
# Wallets
class WalletCreateRequest(BaseModel):
    chain: Literal["evm", "xrpl"]
    network: Literal["mainnet", "testnet"]
    chain_id: int | None = None
    label: str | None = None

class WalletCreateResponse(BaseModel):
    address: str
    chain: str
    network: str
    chain_id: int | None
    label: str | None
    created_at: datetime
    seed_phrase: str  # ONLY returned on create, never again
    warning: str

class WalletListItem(BaseModel):
    address: str
    chain: str
    network: str
    chain_id: int | None
    label: str | None
    created_at: datetime


# Strategies
class StrategyRule(BaseModel):
    name: str                                 # signal name
    signal_type: Literal["TRIGGER", "FILTER"]
    timeframe: str | None = None
    params: dict[str, Any]

class ExecutionConfig(BaseModel):
    initial_balance: float = 10000
    max_open_positions: int = 3
    max_trades_per_day: int = 10
    max_risk_per_trade: float = 0.02
    max_units_per_trade: float | None = None
    max_trade_amount: float | None = None
    min_trade_amount: float = 25
    volatility_window: int = 24
    target_volatility: float = 0.1

class StrategyCreateAutonomousRequest(BaseModel):
    goal: str                                  # natural-language
    asset: str
    timeframe: Literal["1m", "5m", "15m", "1h", "4h", "1d"]
    candidate_count: int = Field(7, ge=5, le=10)
    backtest_lookback_months: int = 3

class StrategyCreateManualRequest(BaseModel):
    name: str
    asset: str
    timeframe: str
    entry: list[StrategyRule]
    exit: list[StrategyRule] = []
    execution_config: ExecutionConfig | None = None

class StrategyDetail(BaseModel):
    id: str                                    # Hank's local UUID
    mangrove_id: str                           # Mangrove's strategy ID
    name: str
    asset: str
    timeframe: str
    status: Literal["draft", "inactive", "paper", "live", "archived"]
    entry: list[StrategyRule]
    exit: list[StrategyRule]
    execution_config: ExecutionConfig
    generation_report: dict | None = None       # for autonomous strategies
    created_at: datetime
    updated_at: datetime


# Allocations (live strategies only)
class Allocation(BaseModel):
    strategy_id: str
    wallet_address: str
    token_address: str
    token_symbol: str
    amount: float
    active: bool
    created_at: datetime
    released_at: datetime | None


# Execution
class OrderIntent(BaseModel):
    """Pure output of strategy_evaluator. No side effects."""
    action: Literal["enter", "exit"]
    side: Literal["buy", "sell"]
    symbol: str
    amount: float
    reason: str                                 # which signal fired
    stop_loss: float | None = None
    take_profit: float | None = None

class Evaluation(BaseModel):
    id: str
    strategy_id: str
    timestamp: datetime
    market_snapshot: dict                        # last bar + indicators
    signals_fired: list[dict]
    order_intents: list[OrderIntent]
    positions_snapshot: list[Position]
    duration_ms: int
    status: Literal["ok", "error", "skipped"]
    error_msg: str | None

class Trade(BaseModel):
    id: str
    strategy_id: str
    evaluation_id: str
    order_intent: OrderIntent
    mode: Literal["live", "paper"]
    tx_hash: str | None                          # null for paper
    input_token: str
    input_amount: float
    output_token: str
    output_amount: float
    fill_price: float
    fees: dict                                   # gas, protocol, slippage
    status: Literal["pending", "confirmed", "failed", "simulated"]
    executed_at: datetime
    confirmed_at: datetime | None
    p_and_l: float | None                        # filled when the position closes

class Position(BaseModel):
    id: str
    strategy_id: str
    asset: str
    entry_trade_id: str
    exit_trade_id: str | None
    entry_price: float
    entry_amount: float
    entry_time: datetime
    exit_price: float | None
    exit_amount: float | None
    exit_time: datetime | None
    status: Literal["open", "closed"]
    stop_loss: float | None
    take_profit: float | None


# Backtest
class BacktestRequest(BaseModel):
    mode: Literal["quick", "full"]
    lookback_months: int = 3
    start_date: datetime | None = None
    end_date: datetime | None = None

class BacktestResult(BaseModel):
    strategy_id: str
    mode: str
    metrics: dict                                 # irr, sharpe, sortino, max_dd, win_rate, total_trades, net_pnl
    trades: list[dict] | None                     # only populated for full mode
    duration_ms: int
```

---

### SQLite Schema

```sql
-- Wallets: encrypted local key storage
CREATE TABLE wallets (
    id TEXT PRIMARY KEY,                          -- UUID
    address TEXT UNIQUE NOT NULL,
    chain TEXT NOT NULL,                          -- evm | xrpl
    network TEXT NOT NULL,                        -- mainnet | testnet
    chain_id INTEGER,
    encrypted_secret BLOB NOT NULL,               -- Fernet-encrypted seed phrase
    encryption_method TEXT NOT NULL,              -- 'fernet-v1'
    label TEXT,
    created_at TEXT NOT NULL,                     -- ISO 8601
    metadata_json TEXT
);
CREATE INDEX idx_wallets_chain ON wallets(chain, chain_id);

-- Strategies: local cache of Mangrove strategies (Mangrove is source of truth)
CREATE TABLE strategies (
    id TEXT PRIMARY KEY,                          -- Hank's UUID
    mangrove_id TEXT UNIQUE NOT NULL,             -- Mangrove's strategy ID
    name TEXT NOT NULL,
    asset TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    status TEXT NOT NULL,                         -- draft | inactive | paper | live | archived
    entry_json TEXT NOT NULL,                     -- list[StrategyRule]
    exit_json TEXT NOT NULL,
    execution_config_json TEXT NOT NULL,
    generation_report_json TEXT,                  -- null for manual strategies
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX idx_strategies_status ON strategies(status);

-- Allocations: per-strategy fund commitments (live only)
CREATE TABLE allocations (
    id TEXT PRIMARY KEY,
    strategy_id TEXT NOT NULL REFERENCES strategies(id),
    wallet_address TEXT NOT NULL REFERENCES wallets(address),
    token_address TEXT NOT NULL,
    token_symbol TEXT NOT NULL,
    amount REAL NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,            -- boolean
    created_at TEXT NOT NULL,
    released_at TEXT
);
CREATE INDEX idx_allocations_strategy ON allocations(strategy_id, active);

-- Evaluations: every cron tick
CREATE TABLE evaluations (
    id TEXT PRIMARY KEY,
    strategy_id TEXT NOT NULL REFERENCES strategies(id),
    timestamp TEXT NOT NULL,
    market_snapshot_json TEXT NOT NULL,
    signals_fired_json TEXT NOT NULL,
    order_intents_json TEXT NOT NULL,
    positions_snapshot_json TEXT NOT NULL,
    duration_ms INTEGER NOT NULL,
    status TEXT NOT NULL,                         -- ok | error | skipped
    error_msg TEXT
);
CREATE INDEX idx_evaluations_strategy_ts ON evaluations(strategy_id, timestamp DESC);

-- Trades: every order intent → execution
CREATE TABLE trades (
    id TEXT PRIMARY KEY,
    strategy_id TEXT NOT NULL REFERENCES strategies(id),
    evaluation_id TEXT REFERENCES evaluations(id),
    order_intent_json TEXT NOT NULL,
    mode TEXT NOT NULL,                           -- live | paper
    tx_hash TEXT,                                 -- null for paper
    input_token TEXT NOT NULL,
    input_amount REAL NOT NULL,
    output_token TEXT NOT NULL,
    output_amount REAL NOT NULL,
    fill_price REAL NOT NULL,
    fees_json TEXT NOT NULL,
    status TEXT NOT NULL,                         -- pending | confirmed | failed | simulated
    executed_at TEXT NOT NULL,
    confirmed_at TEXT,
    p_and_l REAL
);
CREATE INDEX idx_trades_strategy ON trades(strategy_id, executed_at DESC);
CREATE INDEX idx_trades_status ON trades(status);

-- Positions: derived from trades, cached for fast evaluator access
CREATE TABLE positions (
    id TEXT PRIMARY KEY,
    strategy_id TEXT NOT NULL REFERENCES strategies(id),
    asset TEXT NOT NULL,
    entry_trade_id TEXT NOT NULL REFERENCES trades(id),
    exit_trade_id TEXT REFERENCES trades(id),
    entry_price REAL NOT NULL,
    entry_amount REAL NOT NULL,
    entry_time TEXT NOT NULL,
    exit_price REAL,
    exit_amount REAL,
    exit_time TEXT,
    status TEXT NOT NULL,                         -- open | closed
    stop_loss REAL,
    take_profit REAL
);
CREATE INDEX idx_positions_strategy_status ON positions(strategy_id, status);

-- APScheduler job store (built-in table schema, managed by apscheduler[sqlalchemy])
-- CREATE TABLE apscheduler_jobs ... (managed by the library)
```

---

## Error Handling

Standard error response:
```json
{
  "error": true,
  "code": "ERROR_CODE",
  "message": "Human-readable description",
  "suggestion": "What to do about it",
  "correlation_id": "uuid"
}
```

### Error codes

| Code | HTTP | When |
|------|------|------|
| `AUTH_MISSING_API_KEY` | 401 | `X-API-Key` header not provided |
| `AUTH_INVALID_API_KEY` | 401 | Key doesn't match `HANK_API_KEY` |
| `VALIDATION_ERROR` | 400 | Pydantic validation failed; details in `message` |
| `CONFIRMATION_REQUIRED` | 400 | Live deploy/stop/withdraw without `confirm: true` |
| `WALLET_NOT_FOUND` | 404 | Address not in Hank's wallet store |
| `WALLET_ALREADY_EXISTS` | 409 | Wallet with that address already stored |
| `STRATEGY_NOT_FOUND` | 404 | Strategy ID not found |
| `STRATEGY_INVALID_STATUS_TRANSITION` | 400 | Illegal transition (e.g., draft → live) |
| `STRATEGY_INVALID_COMPOSITION` | 400 | Manual mode: entry/exit rule constraint violated |
| `STRATEGY_NO_VIABLE_CANDIDATES` | 422 | Autonomous mode: no candidates passed filters |
| `ALLOCATION_INSUFFICIENT` | 400 | Wallet balance < requested allocation |
| `SDK_ERROR` | 502 | Upstream Mangrove SDK error; original error in `message` |
| `SIGNING_ERROR` | 500 | Local signing failed (bad key, wallet corruption) |
| `EVALUATION_ERROR` | 500 | Strategy evaluator raised; details logged |
| `SCHEDULER_ERROR` | 500 | APScheduler job registration/cancellation failed |
| `INTERNAL_ERROR` | 500 | Catch-all; details in server logs |

All errors carry a `correlation_id` for cross-referencing against Hank's logs.

---

## Authentication & Authorization

**Model:** single-user API key authentication.

**Flow:**
1. User sets `HANK_API_KEY` env var (local) or GCP Secret (Cloud Run).
2. Requests include `X-API-Key: <key>`.
3. Middleware validates against `HANK_API_KEY`; rejects with 401 if missing or invalid.
4. Free tier endpoints bypass the middleware.

**MCP auth:** MCP is served over Streamable HTTP transport. The MCP client (Claude Code, Claude Desktop, custom agent) sends the API key as a standard HTTP header on every request to `/mcp`.

Client-side configuration example (`.mcp.json` in a Claude Code project):
```json
{
  "mcpServers": {
    "hank": {
      "transport": "http",
      "url": "http://localhost:8080/mcp",
      "headers": {
        "X-API-Key": "${HANK_API_KEY}"
      }
    }
  }
}
```

Server-side, Hank's FastAPI middleware inspects `X-API-Key` identically for REST and MCP requests — the MCP mount at `/mcp` is just another FastAPI route group. If the key is missing or invalid, the MCP tool call returns an MCP-level error with `code: AUTH_INVALID_API_KEY` (mapped to 401 for REST). Discovery tools (`status`, `list_tools`) bypass auth.

**Storage:** No user accounts, no sessions, no tokens. Single shared secret per deployment.

---

## External Integrations

### 1. `mangroveai` SDK

**Purpose:** strategies, backtesting, signals, market data, on-chain, KB.

**Config:**
- `MANGROVE_API_KEY` — prod_* or dev_* (SDK auto-detects env)
- `MANGROVEAI_BASE_URL` — optional override

**Usage:**
```python
from mangroveai import MangroveAI
client = MangroveAI()  # reads env
```

**Failure handling:** SDK raises `APIError`, `NotFoundError`, `RateLimitError`. Hank's service layer catches these and re-raises as `SDKError` (502) with the original correlation_id preserved.

**Retry:** SDK's built-in retry handles 429/5xx. Hank does not add additional retry.

---

### 2. `mangrovemarkets` SDK

**Purpose:** DEX swaps, wallet creation, portfolio analytics.

**Config:**
- `MANGROVEMARKETS_BASE_URL` — defaults to `http://localhost:8080` (MCP server); set to deployed URL in prod
- `MANGROVE_API_KEY` — same key as `mangroveai`

**Usage:**
```python
from mangrovemarkets import MangroveMarkets
client = MangroveMarkets(base_url=os.environ["MANGROVEMARKETS_BASE_URL"])
```

**Signing:** The SDK never touches private keys. `prepare_swap()` and `approve_token()` return unsigned transaction payloads; Hank's `wallet_manager` decrypts the key in memory, signs the payload, then calls `broadcast()` with the signed tx. Key is zeroed from memory immediately after.

**Failure handling:** Same pattern as `mangroveai`.

---

### 3. Local Key Encryption

**Library:** `cryptography` (Fernet symmetric encryption).

**Master key source (priority order):**
1. OS Keychain via `keyring` library (macOS Keychain, GNOME Keyring, Windows Credential Manager) — default
2. `HANK_MASTER_KEY` env var — fallback for Cloud Run / CI

**Scheme:**
- Master key generated once on first wallet creation, stored in keychain
- Each wallet's seed phrase encrypted with `Fernet(master_key)` before DB insert
- Decryption only in `wallet_manager.sign()` scope; decrypted bytes never logged, never returned from an endpoint

---

### 4. APScheduler

**Library:** `apscheduler` with `BackgroundScheduler` and SQLAlchemy job store.

**Job store:** the same SQLite DB as Hank's data (`HANK_DB_PATH`) — survives process restarts.

**Timeframe mapping:**
| Strategy timeframe | Cron expression |
|--------------------|-----------------|
| 1m | `*/1 * * * *` |
| 5m | `*/5 * * * *` |
| 15m | `*/15 * * * *` |
| 1h | `0 * * * *` |
| 4h | `0 */4 * * *` |
| 1d | `0 0 * * *` |

**Lifecycle:**
- Scheduler starts in FastAPI lifespan (`on_startup`)
- Strategy activation (`paper` or `live`) → register job `eval-<strategy_id>`
- Strategy deactivation → remove job
- Job fires → call `strategy_evaluator.evaluate(strategy_id)`

**Failure handling:** failed evaluations are logged to the `evaluations` table with `status='error'` and `error_msg` populated. The strategy remains active — transient failures (API outages, etc.) should not stop the schedule.

---

## Configuration

### Required environment variables

| Variable | Purpose |
|----------|---------|
| `MANGROVE_API_KEY` | Shared between both SDKs; `prod_*` or `dev_*` prefix |
| `HANK_API_KEY` | Hank's own auth |
| `ENVIRONMENT` | `local` \| `dev` \| `test` \| `prod` |

### Optional environment variables

| Variable | Default |
|----------|---------|
| `MANGROVEAI_BASE_URL` | auto-detect from API key prefix |
| `MANGROVEMARKETS_BASE_URL` | `http://localhost:8080` |
| `HANK_DB_PATH` | `./hank.db` |
| `HANK_MASTER_KEY` | OS keychain |

### Per-environment config JSON (`server/src/config/{env}-config.json`)

```json
{
  "service_name": "hank",
  "log_level": "INFO",
  "backtest": {
    "autonomous_candidate_count": 7,
    "candidate_filter": {
      "min_win_rate": 0.51,
      "min_total_trades": 10
    },
    "default_lookback_months": 3
  },
  "scheduler": {
    "max_instances": 1,
    "coalesce": true,
    "misfire_grace_time_seconds": 60
  },
  "logs": {
    "retention_days": 90
  }
}
```

---

## Service Layer Modules

All routes and MCP tools delegate to these services. Never duplicate business logic between the two interfaces.

| Module | Responsibility |
|--------|---------------|
| `services/wallet_manager.py` | Key gen, encryption, decryption, local signing |
| `services/strategy_service.py` | Strategy CRUD (wraps `mangroveai.strategies`), local cache sync |
| `services/candidate_generator.py` | Autonomous skill: goal → 5–10 signal combos (uses `mangroveai.signals` + `mangroveai.kb`) |
| `services/backtest_service.py` | Quick + full backtest orchestration; filter + rank by IRR |
| `services/signal_service.py` | Signal discovery (wraps `mangroveai.signals`) |
| `services/market_data.py` | OHLCV, market data, trending, global (wraps `mangroveai.crypto_assets`) |
| `services/on_chain.py` | Smart money, whale activity, holders (wraps `mangroveai.on_chain`) |
| `services/dex_service.py` | DEX venue/pair/quote/swap (wraps `mangrovemarkets.dex`) |
| `services/portfolio_service.py` | Portfolio value, P&L, history (wraps `mangrovemarkets.portfolio`) |
| `services/kb_service.py` | KB search and glossary (wraps `mangroveai.kb`) |
| `services/strategy_evaluator.py` | Pure function: (strategy, market_data, positions) → OrderIntent[] |
| `services/order_executor.py` | OrderIntent → DEX swap (live) or simulated fill (paper) |
| `services/scheduler_service.py` | APScheduler wrapper: register, cancel, list active jobs |
| `services/trade_log.py` | SQLite writes: evaluations, trades, positions |
| `services/allocation_service.py` | Local allocation accounting for live strategies |

---

## Traceability: User Story → Endpoint

Every user story maps to at least one endpoint.

| Story | Endpoints |
|-------|-----------|
| US-1 create wallet | `POST /wallet/create` |
| US-2 balances | `GET /wallet/{a}/balances` |
| US-3 DEX venues/pairs | `GET /dex/venues`, `GET /dex/pairs` |
| US-4 swap quote | `POST /dex/quote` |
| US-5 execute swap | `POST /dex/swap` |
| US-6 OHLCV | `GET /market/ohlcv` |
| US-7 market data | `GET /market/data` |
| US-8 trending / global | `GET /market/trending`, `GET /market/global` |
| US-9 on-chain | `GET /on-chain/smart-money`, `/whale-activity`, `/token-holders` |
| US-10 portfolio | `GET /wallet/{a}/portfolio`, `/history` |
| US-11 signals | `GET /signals`, `GET /signals/{name}` |
| US-12 create strategy | `POST /strategies/autonomous`, `POST /strategies/manual` |
| US-13 list/view strategies | `GET /strategies`, `GET /strategies/{id}` |
| US-14 update status | `PATCH /strategies/{id}/status` |
| US-15 backtest | `POST /strategies/{id}/backtest` |
| US-16 automated eval loop | `PATCH /strategies/{id}/status` (activates cron) + `POST /strategies/{id}/evaluate` (manual tick) |
| US-17 deposit/withdraw | `PATCH /strategies/{id}/status` with `allocation` block (deposit on → live) or confirm (withdraw on → inactive) |
| US-18 KB | `GET /kb/search`, `GET /kb/glossary/{term}` |
