# Architecture: defi-agent

**Generated:** 2026-04-17
**Status:** Draft
**Based on:** `docs/specification.md`

## Overview

defi-agent is a local FastAPI + MCP service that wraps two Mangrove SDKs and runs strategies on in-process cron jobs. The architecture is deliberately minimal:

- **One process.** FastAPI app serves REST + MCP + runs the scheduler in-process.
- **One datastore.** SQLite for everything — business data and the APScheduler jobstore share a DB file.
- **Two external dependencies.** `mangroveai` and `mangrovemarkets` SDKs. That's it.
- **Zero local logic where the SDK already does the work.** Strategy evaluation, risk gates, position sizing, cooldowns, volatility adjustments — all of that lives in Mangrove's execution engine. The agent calls the SDK and executes the returned orders. It does not reimplement any of that logic.

No Postgres, no Redis, no x402, no message queues, no separate scheduler service.

Cloud deployment is out of scope for v1. See [Roadmap](#roadmap).

---

## System Architecture

```mermaid
graph TB
    subgraph "User's Machine"
        ClaudeCode[Claude Code<br/>or MCP client]
        HTTPClient[Python script / curl /<br/>any HTTP client]

        subgraph "defi-agent process"
            subgraph "API Layer"
                REST[REST routes<br/>/api/v1/agent/*]
                MCP[MCP tools<br/>/mcp]
            end
            AuthMW[Auth middleware<br/>X-API-Key]
            Services[Service layer]
            Scheduler[APScheduler<br/>in-process]
        end

        subgraph "Local storage"
            SQLite[(SQLite<br/>agent.db)]
            Keychain[(OS Keychain<br/>master key)]
        end
    end

    subgraph "Mangrove APIs"
        MangroveAI[mangroveai SDK<br/>strategies, backtest,<br/>evaluate, signals,<br/>market, KB]
        MangroveMkts[mangrovemarkets SDK<br/>DEX, wallet, portfolio]
    end

    ClaudeCode -->|MCP over HTTP| MCP
    HTTPClient -->|HTTPS| REST
    REST --> AuthMW
    MCP --> AuthMW
    AuthMW --> Services
    Scheduler -->|cron tick| Services
    Services --> SQLite
    Services -->|encrypt/decrypt| Keychain
    Services --> MangroveAI
    Services --> MangroveMkts
```

### Component responsibilities

| Component | Responsibility |
|-----------|---------------|
| REST routes | HTTP handlers under `/api/v1/agent/*`; delegate to service layer |
| MCP tools | FastMCP tool handlers at `/mcp`; delegate to service layer |
| Auth middleware | Validate `X-API-Key` against configured API key; bypass for discovery |
| Service layer | Orchestration — no strategy/risk logic; that's all in Mangrove |
| Scheduler | APScheduler BackgroundScheduler, SQLite jobstore |
| SQLite | Wallets (encrypted), strategies cache, allocations, evaluations, trades, positions, APScheduler jobs |
| OS Keychain | Stores the Fernet master key; config-resolved secret is the fallback |

---

## Data Flow — Request Path

```mermaid
flowchart LR
    A[Request<br/>REST or MCP] --> B{Discovery<br/>endpoint?}
    B -->|Yes| C[Service layer]
    B -->|No| D{Valid<br/>X-API-Key?}
    D -->|No| E[401<br/>AUTH_INVALID_API_KEY]
    D -->|Yes| C
    C --> F{Needs<br/>local state?}
    F -->|Yes| G[(SQLite)]
    F -->|Needs Mangrove?| H[SDK call]
    F -->|Needs key?| I[Keychain<br/>decrypt → sign]
    G --> J[Response]
    H --> J
    I --> J
```

Auth is enforced once at the boundary. The service layer is protocol-agnostic — it doesn't know or care whether the caller came in via REST or MCP.

---

## Data Flow — Automated Evaluation Loop

```mermaid
flowchart LR
    A[APScheduler<br/>cron tick] --> B[strategy_service]
    B --> C[Fetch latest market data<br/>mangroveai.crypto_assets]
    C --> D[mangroveai.execution.evaluate<br/>strategy_id + current data]
    D --> E[SDK applies:<br/>signal eval, position sizing,<br/>risk gates, cooldowns,<br/>vol adjustment]
    E --> F[OrderIntent array<br/>from SDK]
    F --> G[order_executor]
    G --> H{Strategy<br/>mode?}
    H -->|paper| I[Simulate fill<br/>at mid/mark price]
    H -->|live| J[DEX swap via<br/>mangrovemarkets SDK]
    J --> K[Sign locally,<br/>broadcast, poll]
    I --> L[trade_log]
    K --> L
    L --> M[(SQLite:<br/>evaluations, trades,<br/>positions)]
```

**Critical:** the agent does not evaluate strategies locally. Signal evaluation, risk gates (`max_risk_per_trade`, `max_open_positions`, `max_trades_per_day`), position sizing, volatility adjustment, and cooldown enforcement all live in Mangrove's SDK (`mangroveai.execution.evaluate()`). The agent's job is:
1. Fetch current market data
2. Call the SDK evaluate endpoint
3. Branch the returned `OrderIntent[]` to paper or live execution
4. Log everything

---

## Sequence — Autonomous Strategy Creation

```mermaid
sequenceDiagram
    participant U as User / Caller
    participant API as REST or MCP
    participant SS as strategy_service
    participant CG as candidate_generator
    participant SDK as mangroveai SDK
    participant DB as SQLite

    U->>API: POST /strategies/autonomous<br/>{goal, asset, timeframe}
    API->>SS: create_autonomous(req)
    SS->>CG: generate_candidates(goal, asset, timeframe)
    CG->>SDK: signals.list(category filters)
    SDK-->>CG: signal catalog
    CG-->>SS: 5-10 candidate strategies

    loop for each candidate
        SS->>SDK: backtesting.run(mode=quick, ...)
        SDK-->>SS: metrics
    end

    SS->>SS: filter (win_rate>0.51, trades>=10)
    SS->>SS: rank by IRR

    alt no survivors
        SS-->>API: 422 STRATEGY_NO_VIABLE_CANDIDATES
        API-->>U: error + suggestion
    else has survivors
        SS->>SDK: backtesting.run(mode=full, winner)
        SDK-->>SS: full metrics + trade history
        SS->>SDK: strategies.create(winner)
        SDK-->>SS: mangrove_id
        SS->>DB: INSERT strategies cache + generation_report
        SS-->>API: StrategyDetail + report
        API-->>U: 201 Created
    end
```

Candidate generation uses **deterministic heuristics** — a rules table mapping goal keywords (momentum, mean_reversion, breakout, trend) to signal categories, with random sampling within each category for diversity. No LLM call from the server. Intelligence lives in the mapping + the user's choice of goal language.

---

## Sequence — Strategy Activation (→ live)

```mermaid
sequenceDiagram
    participant U as User
    participant API as REST or MCP
    participant SS as strategy_service
    participant WM as wallet_manager
    participant AS as allocation_service
    participant SCH as scheduler_service
    participant SDK as mangroveai SDK
    participant DB as SQLite

    U->>API: PATCH /strategies/{id}/status<br/>{status: live, confirm: true,<br/>allocation: {...}}
    API->>SS: update_status(id, live, allocation)
    SS->>SS: validate transition (paper→live OK)
    SS->>WM: wallet_exists(allocation.wallet_address)
    WM->>DB: SELECT from wallets
    WM-->>SS: yes
    SS->>AS: record_allocation(strategy, allocation)
    AS->>DB: INSERT into allocations
    SS->>SDK: strategies.update_status(mangrove_id, live)
    SDK-->>SS: ok
    SS->>SCH: register_job(strategy_id, timeframe)
    SCH->>DB: INSERT into apscheduler_jobs
    SCH-->>SS: job_id
    SS-->>API: StrategyDetail (status=live)
    API-->>U: 200 OK
```

From here, the scheduler fires independently on the strategy's timeframe — no user involvement until they deactivate.

---

## Sequence — Cron Tick (strategy evaluation)

```mermaid
sequenceDiagram
    participant SCH as APScheduler
    participant SS as strategy_service
    participant MD as market_data
    participant SDK as mangroveai.execution
    participant OE as order_executor
    participant Mkts as mangrovemarkets SDK
    participant WM as wallet_manager
    participant TL as trade_log
    participant DB as SQLite

    SCH->>SS: tick(strategy_id)
    SS->>DB: load strategy
    SS->>MD: get_latest(asset, timeframe)
    MD-->>SS: current market data
    SS->>SDK: execution.evaluate(strategy_id, market_data)
    SDK-->>SS: [OrderIntent] (0..N, with risk gates already applied)

    alt order_intents empty
        SS->>TL: log evaluation (no_action)
        TL->>DB: INSERT evaluations
    else has orders
        SS->>OE: execute(order_intents, strategy.mode)
        loop per order
            alt mode == paper
                OE->>MD: mid price
                MD-->>OE: price
                OE->>TL: log simulated trade
                TL->>DB: INSERT trades (status=simulated)
            else mode == live
                OE->>Mkts: dex.get_quote(...)
                Mkts-->>OE: Quote
                OE->>Mkts: dex.approve_token if needed
                Mkts-->>OE: UnsignedTx | None
                opt approval needed
                    OE->>WM: sign(tx, wallet)
                    WM-->>OE: signed_tx
                    OE->>Mkts: dex.broadcast + tx_status
                end
                OE->>Mkts: dex.prepare_swap
                Mkts-->>OE: UnsignedTx
                OE->>WM: sign(tx, wallet)
                WM-->>OE: signed_tx
                OE->>Mkts: dex.broadcast
                Mkts-->>OE: tx_hash
                loop poll
                    OE->>Mkts: dex.tx_status
                    Mkts-->>OE: status
                end
                OE->>TL: log live trade
                TL->>DB: INSERT trades (status=confirmed)
            end
        end
        OE->>DB: UPDATE positions
    end
```

The evaluator logic is entirely inside `mangroveai.execution.evaluate()`. The agent's `strategy_service` is a thin orchestrator: fetch data, call SDK, dispatch results to the executor.

---

## Sequence — DEX Swap (user-initiated)

```mermaid
sequenceDiagram
    participant U as User
    participant API as REST or MCP
    participant DS as dex_service
    participant WM as wallet_manager
    participant SDK as mangrovemarkets SDK
    participant Chain as Blockchain

    U->>API: POST /dex/swap<br/>{..., confirm: true}
    API->>DS: execute_swap(req)
    DS->>SDK: dex.get_quote(...)
    SDK-->>DS: Quote
    DS->>SDK: dex.approve_token(...)
    SDK-->>DS: UnsignedTransaction | None

    opt needs approval
        DS->>WM: sign(tx, wallet)
        WM->>WM: decrypt seed in memory
        WM-->>DS: signed_tx
        DS->>SDK: dex.broadcast(signed_tx)
        SDK->>Chain: submit tx
        Chain-->>SDK: tx_hash
        SDK-->>DS: BroadcastResult
        loop poll
            DS->>SDK: dex.tx_status(hash)
            SDK-->>DS: status
        end
    end

    DS->>SDK: dex.prepare_swap(quote_id, wallet)
    SDK-->>DS: UnsignedTransaction
    DS->>WM: sign(tx, wallet)
    WM-->>DS: signed_tx
    DS->>SDK: dex.broadcast(signed_tx)
    SDK->>Chain: submit tx
    Chain-->>SDK: tx_hash
    loop poll
        DS->>SDK: dex.tx_status(hash)
        SDK-->>DS: status
    end
    DS->>DS: log to trades table
    DS-->>API: SwapResult (tx_hash, fill, ...)
    API-->>U: 200 OK
```

The full 6-step flow, mediated entirely by the agent. The SDK never touches the private key. The key is decrypted in `wallet_manager.sign()` and zeroed from memory immediately after.

---

## Chain Support — v1

v1 is **EVM-only** for live execution. Specifically, whatever chains the `mangrovemarkets` DEX service supports: Ethereum (1), Base (8453), Arbitrum (42161), Polygon (137), Optimism (10), BNB (56), Avalanche (43114), zkSync (324), Gnosis (100), Linea (59144).

| Chain family | Wallet create | Live DEX swap | Strategy execution |
|--------------|---------------|---------------|---------------------|
| EVM | ✅ | ✅ | ✅ live or paper |
| XRPL | 🟡 Stub ("not yet supported in v1") | ❌ | ❌ |
| Solana | ❌ Skip entirely | ❌ Upstream not supported | ❌ |

Rationale: Mangrove's DEX integration wraps 1inch, which is EVM-only in Mangrove's SDK. Solana requires upstream work in `mangrovemarkets` before the agent can support it. XRPL gets a clean "not supported in v1" stub so the API shape doesn't break when it's added later.

---

## Component Diagram — Server Internals

```mermaid
graph TB
    subgraph "server/src"
        App[app.py<br/>FastAPI + lifespan]
        Config[config.py + config/*.json<br/>existing template pattern]

        subgraph "api/"
            Router[router.py]
            subgraph "routes/"
                RWallet[wallet.py]
                RDex[dex.py]
                RMarket[market.py]
                ROnChain[on_chain.py]
                RSignals[signals.py]
                RStrat[strategies.py]
                RLogs[logs.py]
                RKb[kb.py]
                RDiscovery[discovery.py]
            end
        end

        subgraph "mcp/"
            MCPServer[server.py]
            MCPTools[tools.py]
            MCPReg[registry.py]
        end

        subgraph "services/"
            SWallet[wallet_manager.py]
            SStrat[strategy_service.py<br/>cron-tick orchestrator]
            SCG[candidate_generator.py]
            SBT[backtest_service.py]
            SExec[order_executor.py<br/>paper or live dispatch]
            SSched[scheduler_service.py]
            SLog[trade_log.py]
            SAlloc[allocation_service.py]
            SSig[signal_service.py]
            SMD[market_data.py]
            SOC[on_chain.py]
            SDex[dex_service.py]
            SPort[portfolio_service.py]
            SKb[kb_service.py]
        end

        subgraph "shared/"
            AuthMW[auth/middleware.py<br/>existing]
            DB[db/sqlite.py<br/>new]
            Crypto[crypto/fernet.py<br/>new]
            Clients[clients/mangrove.py<br/>SDK singletons, new]
            Errors[errors.py<br/>new]
        end

        subgraph "models/"
            MReq[requests.py]
            MResp[responses.py]
            MDB[db_models.py]
        end
    end

    App --> Router
    App --> MCPServer
    App --> SSched
    Router --> RWallet & RDex & RMarket & ROnChain & RSignals & RStrat & RLogs & RKb & RDiscovery
    MCPServer --> MCPTools
    MCPTools --> MCPReg

    RWallet & RDex --> SWallet & SDex & SPort
    RMarket & ROnChain --> SMD & SOC
    RSignals --> SSig
    RStrat --> SStrat
    RLogs --> SLog
    RKb --> SKb
    MCPTools -.same services.-> SWallet & SStrat & SDex

    SStrat --> SCG & SBT & SSched & SAlloc
    SStrat --> Clients
    SSched --> SStrat
    SStrat --> SExec
    SExec --> SDex & SLog

    SWallet --> Crypto
    SWallet --> DB
    SStrat & SLog & SAlloc --> DB
    SStrat & SBT & SSig & SMD & SOC & SDex & SPort & SKb --> Clients
```

Key properties:
- **Routes never call SDKs directly.** Always through the service layer.
- **MCP tools and REST routes call the same services.** Logic lives in one place.
- **`strategy_service` is thin.** Loads strategy + market data, calls `mangroveai.execution.evaluate()`, dispatches returned orders to the executor. Does not evaluate signals, size positions, or enforce risk gates locally — those live in the SDK.
- **SDK clients are singletons** initialized at startup (`shared/clients/mangrove.py`), shared across services.

---

## Configuration

The agent uses the existing app-in-a-box config pattern — no invented `.env` files, no parallel config layer.

### How the config system works

- `server/src/config/{environment}-config.json` holds all configuration for that env
- `ENVIRONMENT` env var selects which file to load (`local`, `dev`, `test`, `prod`)
- `server/src/config/configuration-keys.json` declares the required keys
- Values can be literal strings/numbers, or `secret:NAME:PROPERTY` references that resolve through GCP Secret Manager (a mechanism that stays in the template but isn't used by local deployments)
- Local dev: put values directly in `local-config.json` (gitignored)

### Configuration keys for defi-agent

Replace the template's `configuration-keys.json` with:

```json
{
  "required": [
    "AUTH_ENABLED",
    "API_KEY",
    "MANGROVE_API_KEY",
    "MANGROVEMARKETS_BASE_URL",
    "DB_PATH",
    "KEYRING_SERVICE_NAME",
    "MASTER_KEY_ENV_FALLBACK",
    "BACKTEST_CANDIDATE_COUNT",
    "BACKTEST_MIN_WIN_RATE",
    "BACKTEST_MIN_TRADES",
    "BACKTEST_DEFAULT_LOOKBACK_MONTHS",
    "LOG_RETENTION_DAYS"
  ],
  "full_app_keys": []
}
```

### Example `local-config.json`

```json
{
  "AUTH_ENABLED": true,
  "API_KEY": "local-dev-key",
  "MANGROVE_API_KEY": "dev_...",
  "MANGROVEMARKETS_BASE_URL": "http://localhost:8080",
  "DB_PATH": "./agent.db",
  "KEYRING_SERVICE_NAME": "defi-agent",
  "MASTER_KEY_ENV_FALLBACK": "",
  "BACKTEST_CANDIDATE_COUNT": 7,
  "BACKTEST_MIN_WIN_RATE": 0.51,
  "BACKTEST_MIN_TRADES": 10,
  "BACKTEST_DEFAULT_LOOKBACK_MONTHS": 3,
  "LOG_RETENTION_DAYS": 90
}
```

Secrets (API keys, master key fallback) can optionally be referenced as `"secret:mangrove-api-key:value"` when running in an environment that has Secret Manager configured — the local deployment puts literal values in the file.

The Fernet master key itself is **not** in config. It's stored in the OS Keychain under the service name `defi-agent`. The `MASTER_KEY_ENV_FALLBACK` config key exists for environments without a keychain — if set (non-empty), the agent uses that value instead of the keychain. Local dev leaves it empty.

### Full app keys (empty for v1)

`full_app_keys` is empty — no Postgres or Redis. If v2 adds them, they go here.

---

## Project Structure

```
app-in-a-box/
├── .claude/                                    # Development framework
│   ├── agents/
│   │   └── product-owner.md                    # Drives build after /plan
│   ├── hooks/
│   │   └── check-onboard.sh
│   ├── rules/
│   │   └── git-workflow.md
│   ├── skills/
│   │   ├── onboard/SKILL.md
│   │   ├── requirements/SKILL.md
│   │   ├── specification/SKILL.md
│   │   ├── architecture/SKILL.md
│   │   ├── plan/SKILL.md
│   │   └── tutorial/SKILL.md                   # Workshop curriculum
│   └── settings.json
├── server/
│   ├── src/
│   │   ├── app.py                              # FastAPI factory, scheduler lifespan
│   │   ├── config.py                           # Existing config loader (unchanged)
│   │   ├── config/
│   │   │   ├── configuration-keys.json         # Updated: agent's required keys
│   │   │   ├── local-config.json               # Local dev values
│   │   │   ├── dev-config.json
│   │   │   ├── test-config.json
│   │   │   └── prod-config.json                # Kept but unused in v1
│   │   ├── api/
│   │   │   ├── router.py                       # Aggregates routes, mounts /api/v1/agent
│   │   │   └── routes/
│   │   │       ├── discovery.py                # health, status, tool catalog
│   │   │       ├── wallet.py                   # create, list, balances, portfolio, history
│   │   │       ├── dex.py                      # venues, pairs, quote, swap
│   │   │       ├── market.py                   # ohlcv, data, trending, global
│   │   │       ├── on_chain.py                 # smart_money, whale, holders
│   │   │       ├── signals.py                  # list, get
│   │   │       ├── strategies.py               # create, list, get, patch status, backtest, evaluate
│   │   │       ├── logs.py                     # evaluations, trades
│   │   │       └── kb.py                       # search, glossary
│   │   ├── mcp/
│   │   │   ├── server.py                       # FastMCP setup
│   │   │   ├── tools.py                        # Tool definitions (mirror REST)
│   │   │   └── registry.py                     # register_tool helper
│   │   ├── services/
│   │   │   ├── wallet_manager.py               # Key gen, Fernet encrypt, local signing
│   │   │   ├── strategy_service.py             # Cron orchestrator: data → SDK evaluate → executor
│   │   │   ├── candidate_generator.py          # Goal → 5-10 signal combos
│   │   │   ├── backtest_service.py             # Quick + full, filter + IRR rank
│   │   │   ├── order_executor.py               # paper (simulate) or live (DEX swap)
│   │   │   ├── scheduler_service.py            # APScheduler wrapper
│   │   │   ├── trade_log.py                    # SQLite writes
│   │   │   ├── allocation_service.py           # Per-strategy fund accounting
│   │   │   ├── signal_service.py               # Wraps mangroveai.signals
│   │   │   ├── market_data.py                  # Wraps mangroveai.crypto_assets
│   │   │   ├── on_chain.py                     # Wraps mangroveai.on_chain
│   │   │   ├── dex_service.py                  # Wraps mangrovemarkets.dex
│   │   │   ├── portfolio_service.py            # Wraps mangrovemarkets.portfolio
│   │   │   └── kb_service.py                   # Wraps mangroveai.kb
│   │   ├── shared/
│   │   │   ├── auth/middleware.py              # X-API-Key validation (existing)
│   │   │   ├── db/
│   │   │   │   ├── sqlite.py                   # Connection helper, migrations
│   │   │   │   └── migrations/                 # SQL schema files
│   │   │   ├── crypto/
│   │   │   │   └── fernet.py                   # Master key mgmt + Fernet wrapper
│   │   │   ├── clients/
│   │   │   │   └── mangrove.py                 # SDK singletons
│   │   │   └── errors.py                       # Error codes, exception → HTTP mapping
│   │   ├── models/
│   │   │   ├── requests.py                     # Pydantic request models
│   │   │   ├── responses.py                    # Pydantic response models
│   │   │   └── db_models.py                    # Row adapters
│   │   └── health.py                           # Health probe payload
│   ├── tests/
│   │   ├── conftest.py
│   │   ├── unit/
│   │   ├── integration/
│   │   └── e2e/
│   ├── Dockerfile
│   └── requirements.txt
├── tutorials/                                  # Workshop curriculum (separate deliverable)
│   └── bots-and-bytes/
├── docs/
│   ├── api-reference.md
│   ├── user-stories.md
│   ├── specification.md
│   ├── architecture.md                         # This document
│   ├── implementation-plan.md                  # Generated by /plan
│   └── configuration.md
├── assets/
├── branding.json
├── docker-compose.yml                          # Local dev stack (app only)
├── init.sh
├── CLAUDE.md
├── README.md
└── LICENSE
```

---

## Module Decisions

| Module | Status | Reason |
|--------|--------|--------|
| **FastAPI app factory** | ✅ Keep | Core of the dual-protocol service pattern |
| **MCP server (FastMCP)** | ✅ Keep | Core — AI agents prefer MCP |
| **REST routes** | ✅ Keep | Core — universal HTTP access |
| **API key auth middleware** | ✅ Keep | Single-user auth model |
| **Service layer pattern** | ✅ Keep | Shared business logic between REST + MCP |
| **Per-environment JSON config** | ✅ Keep | Existing pattern; no `.env` files or parallel systems |
| **configuration-keys.json** | ✅ Keep, update contents | Replace x402 keys with agent keys |
| **SQLite (built-in)** | ✅ Keep | Single datastore for all state |
| **APScheduler** | ✅ Add (new) | In-process cron; not in template |
| **Fernet encryption + OS keychain** | ✅ Add (new) | Wallet key protection |
| **PostgreSQL** | ❌ Remove | SQLite suffices. Remove `--profile full`, `db/init.sql` postgres schema, `notes.py` route. |
| **Redis** | ❌ Remove | No caching; APScheduler jobstore goes in SQLite. |
| **x402 payment middleware + routes** | ❌ Remove | Local agent, no payment surface. Remove `shared/x402/`, `routes/easter_egg.py`, x402 keys from `configuration-keys.json`. |
| **Items demo route** | ❌ Remove | Template scaffolding. |
| **Notes demo route** | ❌ Remove | Template scaffolding. |
| **Easter egg route** | ❌ Remove | x402 demo, not applicable. |
| **Echo route** | ❌ Remove | Template scaffolding. |
| **Terraform (GCP)** | ❌ Remove | Cloud is out of scope for v1. Delete `infra/terraform/`. |
| **GitHub Actions: `deploy-cloudrun.yaml`** | ❌ Remove | Cloud is out of scope for v1. |
| **GitHub Actions: `ci.yml`** | ✅ Keep | Lint + test on push/PR. |
| **Docker Compose (app-only)** | ✅ Keep | Primary local dev entry point. |
| **Docker Compose (full profile)** | ❌ Remove | Postgres + Redis not needed. |

---

## Technology Choices

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Web framework | FastAPI | Template default; great OpenAPI; async-native; plays well with FastMCP |
| MCP library | FastMCP | Template default; FastAPI-integrated; tool registration is a one-liner |
| Storage | SQLite | Local-first means no external DB. Full ACID, WAL mode for concurrency, built into Python. |
| Scheduler | APScheduler (BackgroundScheduler, SQLAlchemy jobstore) | In-process, no broker required, persistent jobstore, Python-native |
| Key encryption | Fernet (from `cryptography`) | Battle-tested, standard-compliant, simple API |
| Master key storage | OS Keychain via `keyring`, config-referenced fallback | Zero-config for local users |
| Config | Existing template pattern (`config/*.json` + `configuration-keys.json`) | No parallel system; consistent with rest of template |
| HTTP client | `httpx` via SDKs | Built into upstream SDKs |
| Test framework | pytest | Template default |

---

## Deployment

### Local (the only supported mode for v1)

```mermaid
graph LR
    User[User's terminal<br/>Claude Code] -->|MCP/HTTP| Docker[Docker Compose<br/>defi-agent container]
    Docker -->|mounted volume| Volume[./agent.db]
    Docker -->|reads| Keychain[OS Keychain]
    Docker -->|HTTPS| Mangrove[Mangrove SDKs]
```

One `docker compose up` command. No cloud account required. State persists across restarts via bind-mounted volume.

For users without Docker, running directly against Python 3.10+ is also supported: `uvicorn src.app:app --reload`.

### Roadmap

Future deployment modes (Cloud Run with persistent storage, Cloud SQL backing, multi-region) are **out of scope for v1**. They will be addressed in a subsequent release once the local pattern is stable and the workshop curriculum is shipped.
