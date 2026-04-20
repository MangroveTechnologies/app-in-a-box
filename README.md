<div align="center">
  <a href="https://github.com/MangroveTechnologies/app-in-a-box">
    <img src="assets/icon.png" alt="Mangrove" width="120" height="112">
  </a>

  <h1>defi-agent</h1>

  <p>
    <strong>An AI trading bot built on the Mangrove API.</strong><br>
    FastAPI + MCP. Autonomous strategy generation, cron-driven execution, full audit trail.
  </p>

  <p>
    <a href="https://github.com/MangroveTechnologies/app-in-a-box/actions/workflows/ci.yml">
      <img src="https://github.com/MangroveTechnologies/app-in-a-box/actions/workflows/ci.yml/badge.svg" alt="CI">
    </a>
    <a href="https://github.com/MangroveTechnologies/app-in-a-box/blob/main/LICENSE">
      <img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License">
    </a>
  </p>
</div>

---

## What this is

A local AI trading bot that:
- Turns natural-language goals ("momentum on ETH") into backtested, ranked trading strategies via the [MangroveAI API](https://mangrovedeveloper.ai).
- Runs live strategies on APScheduler cron jobs. Same evaluator path for paper and live.
- Executes live swaps through [MangroveMarkets](https://github.com/MangroveTechnologies/MangroveMarkets). Client-side signing; SDK never touches your keys.
- Logs every evaluation and trade to local SQLite for a full audit trail.

**Real mainnet swap from the agent** (verified April 2026): [0x5c126e...c5565](https://basescan.org/tx/0x5c126e6be26fc736bcb3f11a8f4c699aeee754f6c0bf7e5b7aa2df6a859c5565)

---

## Quick start (target: ≤ 5 minutes)

You need:
- **Docker** (or Python 3.10+ if you'd rather run bare)
- **A MangroveAI API key** — free from https://mangrovedeveloper.ai (dev_ or prod_ prefix)
- **Claude Code** (optional, for the chat UX) — `npm install -g @anthropic-ai/claude-code`

### 1. Clone

```bash
git clone https://github.com/MangroveTechnologies/app-in-a-box.git defi-agent
cd defi-agent
```

### 2. Configure

```bash
cp server/src/config/local-example-config.json server/src/config/local-config.json
$EDITOR server/src/config/local-config.json
```

You need to change one value:

```json
"MANGROVE_API_KEY": "dev_..."
```

All other defaults are sensible. For a hosted MangroveMarkets MCP server (skip running one yourself), also set:

```json
"MANGROVEMARKETS_BASE_URL": "https://mangrovemarkets-pcqgpciucq-uc.a.run.app"
```

### 3. Run

```bash
touch agent.db                     # Docker Desktop on macOS needs this so the bind mount is a file, not a dir
docker compose up -d --build
```

First build takes a minute. Subsequent runs start in seconds.

### 4. Verify

```bash
./scripts/verify_quickstart.sh
```

This script checks the health endpoint, authenticates, lists the MCP tools, and confirms the agent is ready. Exits 0 on success (target runtime: under 300 seconds from a cold clone).

### 5. Connect Claude Code

Copy the MCP config and point Claude at the agent:

```bash
cp .mcp.json.example ~/.claude/mcp/defi-agent.json
# Or add to a project's .mcp.json
```

Then open a Claude Code session — the agent's 22 tools show up automatically.

---

## What the agent can do

All 22 core MCP tools (plus `hello_mangrove` x402 demo):

| Category | Tools |
|---|---|
| Discovery (free) | `status`, `list_tools` |
| Wallet | `create_wallet`, `list_wallets`, `get_balances` |
| DEX | `list_dex_venues`, `get_swap_quote`, `execute_swap` |
| Market | `get_ohlcv`, `get_market_data` |
| Signals | `list_signals` |
| Strategy | `create_strategy_autonomous`, `create_strategy_manual`, `list_strategies`, `get_strategy`, `update_strategy_status`, `backtest_strategy`, `evaluate_strategy` |
| Logs | `list_evaluations`, `list_trades`, `list_all_trades` |
| Knowledge Base | `kb_search` |

Every tool has a mirrored REST endpoint at `/api/v1/agent/*`. Both call the same service layer — pick whichever fits your caller.

---

## How it works

```
┌─────────────────────────────────────────────────────────────┐
│  Your machine                                               │
│                                                             │
│  Claude Code ─MCP──┐                                        │
│  Python/curl ─REST─┤                                        │
│                    ▼                                        │
│  ┌─ defi-agent (single FastAPI process, port 8080) ──┐     │
│  │   • auth middleware (X-API-Key)                   │     │
│  │   • service layer (one for REST + MCP)            │     │
│  │   • APScheduler (in-process cron, SQLite jobstore)│     │
│  │   • local Fernet-encrypted wallets                │     │
│  └───────────────────────────────────────────────────┘     │
│           │                        │                        │
│           ▼                        ▼                        │
│  ┌── SQLite: agent.db ─┐  ┌── OS Keychain (Fernet key) ─┐  │
│  └─────────────────────┘  └──────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
              │                      │
              ▼                      ▼
       mangroveai SDK         mangrovemarkets SDK
       (strategies, backtest, (DEX swap, portfolio,
        signals, market,       wallet)
        KB, on-chain)
```

Strategy evaluation happens inside `mangroveai.execution.evaluate()` — the agent does **not** re-implement signal logic, risk gates, position sizing, or cooldowns. It orchestrates: fetch strategy → call SDK → dispatch returned `OrderIntent[]` to the executor → log.

For live trades the agent decrypts your wallet's secret in-process, signs the unsigned transaction returned by `mangrovemarkets`, broadcasts the signed bytes, and zeroes the secret. The SDK never sees your key.

---

## Architecture docs

| Doc | What's in it |
|---|---|
| [docs/api-reference.md](docs/api-reference.md) | The Mangrove API surface we call |
| [docs/user-stories.md](docs/user-stories.md) | 18 user stories + 4 flow diagrams |
| [docs/specification.md](docs/specification.md) | API contracts, Pydantic models, SQLite schema, error codes |
| [docs/architecture.md](docs/architecture.md) | System diagrams, sequence diagrams, file tree |
| [docs/implementation-plan.md](docs/implementation-plan.md) | 24-task phased build plan |

## Development

Design-first workflow powered by Claude Code skills — use these when you're building something new on top of the template, not when running defi-agent itself:

```
/onboard → /requirements → /specification → /architecture → /plan
```

Each phase produces a doc in `docs/` and waits for your approval before proceeding. See [docs/](docs/) for the defi-agent outputs.

## Tests

```bash
docker run --rm -v "$(pwd)/server:/app" -w /app -e ENVIRONMENT=test \
  $(docker compose build -q app && docker compose images -q app) \
  pytest tests/
```

Or from inside the running container:

```bash
docker compose exec app pytest tests/
```

Expect: 239 passed, 2 skipped (opt-in live-swap tests).

To run the opt-in live swaps:

```bash
# Testnet (Base Sepolia)
ENABLE_SEPOLIA_TEST=1 BASE_SEPOLIA_PRIVATE_KEY=0x... pytest tests/e2e/test_live_swap.py::test_sepolia_live_swap

# Mainnet — real funds; we tested at 0.10 USDC
ENABLE_MAINNET_TEST=1 BASE_MAINNET_PRIVATE_KEY=0x... pytest tests/e2e/test_live_swap.py::test_mainnet_live_swap
```

## Deployment

Local-only for v1 (Docker Compose). Cloud deployment (Cloud Run with persistent storage, Cloud SQL) is roadmap, not shipped.

## Project layout

```
defi-agent/
├── .claude/                  # Claude Code framework (skills, agents, rules)
├── server/
│   ├── src/
│   │   ├── app.py            # FastAPI factory
│   │   ├── config/           # Per-env JSON configs
│   │   ├── api/routes/       # REST routes — one file per resource
│   │   ├── mcp/              # MCP tool registration
│   │   ├── models/           # Pydantic domain + DB models
│   │   ├── services/         # Business logic (wallet, strategy, executor, scheduler, trade_log, …)
│   │   └── shared/           # auth, db/sqlite.py, crypto/fernet.py, clients/mangrove.py, errors, logging
│   └── tests/                # unit / integration / e2e
├── docs/                     # Design docs (requirements, spec, architecture, plan)
├── scripts/verify_quickstart.sh
├── docker-compose.yml
├── .mcp.json.example         # Drop-in Claude Code MCP config
└── CLAUDE.md                 # Project context
```

## License

MIT
