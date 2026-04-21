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

Copy the example config. This file is gitignored — edit it freely.

```bash
cp server/src/config/local-example-config.json server/src/config/local-config.json
$EDITOR server/src/config/local-config.json
```

Two values to set:

| Key | Why | What to put |
|-----|-----|-------------|
| `MANGROVE_API_KEY` | Authenticates you to the MangroveAI backend (strategies, signals, backtests, on-chain data). Free key at https://mangrovedeveloper.ai. | Your `dev_...` or `prod_...` key |
| `MANGROVEMARKETS_BASE_URL` | Where the agent sends DEX calls (quotes, swaps, wallet ops). Defaults to localhost, which assumes you're running your own MangroveMarkets server. Most people want the hosted one. | `https://mangrovemarkets-pcqgpciucq-uc.a.run.app` |

Every other value in the file has a sensible default.

### 3. Persist the encryption master key

The agent encrypts every wallet's private key with a Fernet master key. By default that key lives in your OS keychain (macOS Keychain / Linux Secret Service / Windows Credential Manager), but **those backends aren't reachable from inside a Docker container** — so without this step each container process generates a fresh in-memory key that dies on restart, stranding any wallets encrypted with it.

Run this once; it's idempotent:

```bash
./scripts/init-master-key.sh
```

The script generates a Fernet key and writes it to `MASTER_KEY_ENV_FALLBACK` in your gitignored `local-config.json`. Container reads it on startup, wallet secrets survive restarts.

### 4. Run

The agent stores its state in a local SQLite file `./agent.db`. Docker bind-mounts it so restarts preserve history. On macOS, Docker creates missing mount targets as directories (which breaks SQLite), so we pre-create the file:

```bash
touch agent.db
docker compose up -d --build
```

First build takes ~60s. After that, startup is a few seconds.

### 5. Verify

One script that proves everything's wired up — checks Docker, config, `/health`, the tool catalog, and startup log events:

```bash
./scripts/verify_quickstart.sh
```

Exits 0 on success. Typical runtime: under 10 seconds once the image is built.

### 6. Connect Claude Code

Register the MCP server with Claude Code. One command — it reads your API key from `local-config.json`, checks the container is healthy, and writes a user-scope registration so Claude Code loads the tools on next start.

```bash
./scripts/setup-mcp.sh
```

Then start (or restart) a Claude Code session in that directory. All 22 agent tools appear automatically.

> **Why a script and not `.mcp.json`?** Claude Code's project-scope `.mcp.json` approval prompt is currently unreliable ([#9189](https://github.com/anthropics/claude-code/issues/9189)) — the "enable this MCP server?" prompt often doesn't persist across restarts. Registering via `claude mcp add` writes user-scope config keyed to this project directory and is honored reliably. `.mcp.json.example` is kept in the repo for reference; once the upstream bug is fixed, the cp-based flow will work too.

### 7. Your first trade

Everything below is a natural-language prompt to Claude Code. The agent handles the tool calls.

1. **Create a dedicated trading wallet.**
   > "Create a wallet on Base mainnet"

   The agent generates a fresh EVM wallet, shows the address + seed phrase **once**, then encrypts the secret to disk. Save the seed phrase offline (paper, hardware wallet, password manager) — it's not retrievable after.

   Use a fresh wallet per project so a misbehaving strategy can only spend what you've deposited into it, never your personal holdings.

2. **Deposit a small test amount.** Send 1–5 USDC from your own wallet or exchange to the address the agent gave you. Confirm it arrived before depositing more.
   > "Check my balance"

3. **Create a strategy from a plain-English goal.**
   > "Create an autonomous momentum strategy for ETH on a 1-hour timeframe"

   The agent picks 5–10 candidate signal combinations, quick-backtests each, filters by win-rate and trade-count, ranks by IRR, and deep-backtests the winner. You get the final metrics back.

4. **Run more backtests if you want.**
   > "Backtest that strategy over the last 6 months"

5. **Activate — paper first, live when you trust it.**
   > "Activate the strategy in paper mode"

   Paper simulates fills at the current market price. Live executes real DEX swaps and requires explicit confirmation + an allocation amount.

6. **Monitor.** Every tick and every trade is logged to the local DB.
   > "Show me my last 10 trades"

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
