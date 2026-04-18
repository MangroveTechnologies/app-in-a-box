# defi-agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build defi-agent — a local FastAPI + MCP service that wraps `mangroveai` and `mangrovemarkets` SDKs, runs autonomous trading strategies on cron jobs, and logs every evaluation and trade.

**Architecture:** Single-process FastAPI app serves REST (`/api/v1/agent/*`) and MCP (`/mcp`) on port 8080. SQLite for all state including the APScheduler jobstore. Wallet keys encrypted with Fernet, master key in OS Keychain. Strategy evaluation delegated entirely to `mangroveai.execution.evaluate()` — the agent never reimplements signal/risk logic. Single execution path (`order_executor`) for both cron-driven and user-initiated swaps.

**Tech Stack:** Python 3.10+, FastAPI, FastMCP, SQLite, APScheduler, cryptography (Fernet), keyring, mangroveai SDK, mangrovemarkets SDK, pytest.

**Scope:** EVM-only for live execution. XRPL stubbed (501). Solana skipped. Local deployment via Docker Compose; cloud is roadmap.

**Spec:** [docs/specification.md](specification.md)
**Architecture:** [docs/architecture.md](architecture.md)
**Requirements:** [docs/user-stories.md](user-stories.md)

**Deadline:** April 24, 2026 (Bots & Bytes workshop, Nashville).

---

## Phase 1 — Foundation & Scaffold Cleanup

Goal: turn the app-in-a-box template into a defi-agent shell. After this phase, the app starts, but no agent endpoints exist yet.

### Task 1.1 — Scaffold cleanup

**Agent:** backend-developer
**Files:**
- Delete: `server/src/api/routes/items.py`, `server/src/api/routes/notes.py`, `server/src/api/routes/echo.py`, `server/src/api/routes/docs.py` (template demo only — agent gets its own discovery), `server/db/init.sql`, `infra/terraform/`, `.github/workflows/deploy-cloudrun.yaml`
- Delete: `server/tests/test_items.py`, `server/tests/test_notes.py`, `server/tests/test_echo.py`, `server/tests/test_docs.py`
- Rename: `server/src/api/routes/easter_egg.py` → `server/src/api/routes/hello_mangrove.py`
- Rename: `server/tests/test_easter_egg.py` → `server/tests/test_hello_mangrove.py`
- Modify: `server/src/api/router.py` (remove deleted routes, register `hello_mangrove`)
- Modify: `server/src/app.py` (update OpenAPI tags, remove items/notes/echo/docs)
- Modify: `docker-compose.yml` (remove `--profile full` services: postgres, redis; remove `db/init.sql` mount)
- Modify: `CLAUDE.md` (remove references to removed modules; update file inventory)

- [ ] **Step 1:** delete the file list above. Verify with `git status`.
- [ ] **Step 2:** run `rg easter_egg server/` and `rg EASTER_EGG server/` — replace every occurrence with `hello_mangrove` / `HELLO_MANGROVE`.
- [ ] **Step 3:** edit `server/src/app.py` `_setup_x402()` — change route key from `"GET /api/x402/easter-egg"` to `"GET /api/x402/hello-mangrove"`, update description. Update `openapi_tags` to drop items/notes/echo, leave x402.
- [ ] **Step 4:** edit `server/src/api/router.py` — remove imports + includes for deleted routes; add `hello_mangrove` import + include under `x402_router`.
- [ ] **Step 5:** edit `docker-compose.yml` — delete `postgres` and `redis` services + `volumes` block.
- [ ] **Step 6:** run the existing test suite: `cd server && pytest`. Expect failures only for removed tests (now deleted) and any test that imported the removed routes — fix any collateral.
- [ ] **Step 7:** run `docker compose up --build`. Verify the container starts and `curl http://localhost:8080/health` returns 200.
- [ ] **Step 8:** commit: `chore(scaffold): rip template demo routes; rename easter_egg → hello_mangrove`.

**Acceptance:** Clean repo with x402 still functional via `hello_mangrove`. App starts. No dead code.

---

### Task 1.2 — Configuration keys

**Agent:** backend-developer
**Files:**
- Modify: `server/src/config/configuration-keys.json`
- Modify: `server/src/config/local-example-config.json`
- Modify: `server/src/config/dev-config.json`, `prod-config.json`, `test-config.json`
- Create: `server/src/config/local-config.json` (gitignored)
- Modify: `.gitignore` (ensure `local-config.json` is ignored)

- [ ] **Step 1:** rewrite `configuration-keys.json` to match `docs/specification.md` Configuration section — include both agent keys and x402 keys.
- [ ] **Step 2:** rewrite `local-example-config.json` with the agent + x402 example values from the spec.
- [ ] **Step 3:** copy `local-example-config.json` → `local-config.json`, fill in real `MANGROVE_API_KEY` (placeholder for the user to populate).
- [ ] **Step 4:** confirm `local-config.json` is in `.gitignore`.
- [ ] **Step 5:** update `dev-config.json`, `prod-config.json`, `test-config.json` with the same shape (placeholder values).
- [ ] **Step 6:** start the app — `config.py` should load successfully. Add any missing required key handling.
- [ ] **Step 7:** commit: `chore(config): add agent + x402 configuration keys`.

**Acceptance:** App starts and `app_config.MANGROVE_API_KEY`, `app_config.DB_PATH`, `app_config.API_KEY` all read correctly.

---

### Task 1.3 — Dependencies

**Agent:** backend-developer
**Files:**
- Modify: `server/requirements.txt`
- Modify: `server/Dockerfile` (no change expected — pip install already covers this, just verify)

- [ ] **Step 1:** add to `requirements.txt`:
  ```
  mangroveai>=0.1.0
  mangrovemarkets>=0.1.0
  apscheduler[sqlalchemy]>=3.10
  cryptography>=42
  keyring>=24
  ```
- [ ] **Step 2:** rebuild Docker image: `docker compose build`. Verify install succeeds.
- [ ] **Step 3:** import smoke test — start container, exec into it, run `python -c "import mangroveai, mangrovemarkets, apscheduler, cryptography, keyring; print('ok')"`.
- [ ] **Step 4:** commit: `chore(deps): add SDK + scheduler + crypto + keyring`.

**Acceptance:** All five libraries installable and importable in the container.

---

### Task 1.4 — Errors module

**Agent:** backend-developer
**Files:**
- Create: `server/src/shared/errors.py`
- Create: `server/tests/unit/test_errors.py`

- [ ] **Step 1:** define `class AgentError(Exception)` with `code: str`, `message: str`, `suggestion: str | None`, `http_status: int`, `correlation_id: str` (auto-generated UUID).
- [ ] **Step 2:** define subclasses for each error code in `docs/specification.md` Error Handling section: `AuthMissingApiKey`, `AuthInvalidApiKey`, `ValidationError`, `ConfirmationRequired`, `WalletNotFound`, `WalletAlreadyExists`, `StrategyNotFound`, `StrategyInvalidStatusTransition`, `StrategyInvalidComposition`, `StrategyNoViableCandidates`, `AllocationInsufficient`, `SdkError`, `SigningError`, `EvaluationError`, `SchedulerError`, `ChainNotSupportedInV1`, `InternalError`. Each has its `code` and `http_status` baked in.
- [ ] **Step 3:** add a FastAPI exception handler that converts `AgentError` to the standard response shape from the spec (`{error, code, message, suggestion, correlation_id}`).
- [ ] **Step 4:** write a unit test per error class: instantiate, assert code + http_status + serialization shape.
- [ ] **Step 5:** wire the handler into `app.py` lifespan/startup.
- [ ] **Step 6:** commit: `feat(errors): add AgentError hierarchy + FastAPI handler`.

**Acceptance:** Raising `WalletNotFound("0xabc")` from a route returns the spec-defined JSON with HTTP 404.

---

### Task 1.5 — SDK client singletons

**Agent:** backend-developer
**Files:**
- Create: `server/src/shared/clients/__init__.py`
- Create: `server/src/shared/clients/mangrove.py`
- Create: `server/tests/unit/test_clients.py`

- [ ] **Step 1:** in `mangrove.py`, define module-level singletons (lazy):
  ```python
  from functools import lru_cache
  from mangroveai import MangroveAI
  from mangrovemarkets import MangroveMarkets
  from src.config import app_config

  @lru_cache(maxsize=1)
  def mangroveai_client() -> MangroveAI:
      return MangroveAI(api_key=app_config.MANGROVE_API_KEY)

  @lru_cache(maxsize=1)
  def mangrovemarkets_client() -> MangroveMarkets:
      return MangroveMarkets(
          base_url=app_config.MANGROVEMARKETS_BASE_URL,
          api_key=app_config.MANGROVE_API_KEY,
      )
  ```
- [ ] **Step 2:** write unit test that calls each accessor twice, asserts the same instance comes back.
- [ ] **Step 3:** add a smoke test: call `mangroveai_client().status` (or any free SDK call) — confirm a real connection works against dev URL.
- [ ] **Step 4:** commit: `feat(clients): add Mangrove SDK singletons`.

**Acceptance:** Routes and services can `from src.shared.clients.mangrove import mangroveai_client` and call SDK methods.

---

### Task 1.6 — SQLite layer + migrations

**Agent:** backend-developer
**Files:**
- Create: `server/src/shared/db/__init__.py` (already exists from template — verify)
- Create: `server/src/shared/db/sqlite.py`
- Create: `server/src/shared/db/migrations/001_initial.sql`
- Modify: `server/src/shared/db/exceptions.py` (already exists — extend if needed)
- Create: `server/tests/integration/test_sqlite.py`

- [ ] **Step 1:** write `001_initial.sql` containing every CREATE TABLE + CREATE INDEX statement from `docs/specification.md` SQLite Schema section: `wallets`, `strategies`, `allocations`, `evaluations`, `trades`, `positions`. (APScheduler creates its own tables.)
- [ ] **Step 2:** in `sqlite.py`, write `get_connection() -> sqlite3.Connection` that opens `app_config.DB_PATH` with `PRAGMA foreign_keys = ON`, `PRAGMA journal_mode = WAL`. Cache via `lru_cache`.
- [ ] **Step 3:** add `init_db()` that runs all unapplied migrations in order. Track applied migrations in a `_migrations` table.
- [ ] **Step 4:** call `init_db()` from FastAPI lifespan startup.
- [ ] **Step 5:** integration test — point `DB_PATH` to a tmp file, call `init_db()`, then introspect each table via `PRAGMA table_info(<table>)` and assert columns match the spec.
- [ ] **Step 6:** commit: `feat(db): SQLite connection + initial schema migration`.

**Acceptance:** App startup creates `agent.db` with all 6 tables; restarting the app does not re-run migrations.

---

## Phase 2 — Core Infrastructure

Goal: the agent can hold wallets and write to its log tables. After this phase, no API yet, but the building blocks are in place.

### Task 2.1 — wallet_manager

**Agent:** backend-developer
**Files:**
- Create: `server/src/shared/crypto/__init__.py`, `server/src/shared/crypto/fernet.py`
- Create: `server/src/services/wallet_manager.py`
- Create: `server/src/models/db_models.py` (start; will grow across phases)
- Create: `server/tests/unit/test_wallet_manager.py`

- [ ] **Step 1:** in `crypto/fernet.py`, implement `get_master_key() -> bytes` — try `keyring.get_password(KEYRING_SERVICE_NAME, "master")`; if absent, generate via `Fernet.generate_key()`, store in keychain. Fallback to `MASTER_KEY_ENV_FALLBACK` config value when keychain unavailable.
- [ ] **Step 2:** add `encrypt(plaintext: bytes) -> bytes` and `decrypt(ciphertext: bytes) -> bytes` using Fernet with the master key.
- [ ] **Step 3:** in `wallet_manager.py`, implement `create_wallet(chain, network, chain_id, label) -> WalletCreateResult`:
  - For chain=`xrpl`: raise `ChainNotSupportedInV1`.
  - For chain=`evm`: call `mangrovemarkets_client().wallet.create(...)` to get address + secret, encrypt secret, INSERT into `wallets`.
  - Return the result with the seed phrase included exactly once + the security warning from the spec.
- [ ] **Step 4:** implement `list_wallets() -> list[WalletListItem]` (no secrets returned).
- [ ] **Step 5:** implement `sign(unsigned_tx: dict, wallet_address: str) -> str` — load encrypted seed, decrypt, sign via the SDK's signing helper or web3.py, zero the secret bytes, return signed tx.
- [ ] **Step 6:** unit tests:
  - `test_create_wallet_evm` — create, assert row exists, secret is encrypted, seed phrase returned.
  - `test_create_wallet_xrpl_raises` — assert `ChainNotSupportedInV1`.
  - `test_list_wallets_redacts_secret` — secret never appears in output.
  - `test_sign_round_trip` — encrypt, decrypt, sign known tx, assert signature is valid.
- [ ] **Step 7:** commit: `feat(wallet): wallet_manager with Fernet encryption + local signing`.

**Acceptance:** Wallets created via `wallet_manager.create_wallet()` survive restart, secrets are encrypted on disk, signing works without leaking the key.

---

### Task 2.2 — trade_log

**Agent:** backend-developer
**Files:**
- Create: `server/src/services/trade_log.py`
- Create: `server/src/models/domain.py` (`OrderIntent`, `Evaluation`, `Trade`, `Position`)
- Create: `server/tests/unit/test_trade_log.py`

- [ ] **Step 1:** define Pydantic domain models from `docs/specification.md` Data Models: `OrderIntent`, `Evaluation`, `Trade`, `Position`.
- [ ] **Step 2:** implement `log_evaluation(evaluation: Evaluation) -> str` — INSERT into `evaluations`, return id.
- [ ] **Step 3:** implement `log_trade(trade: Trade) -> str` — INSERT into `trades`, return id.
- [ ] **Step 4:** implement `update_position(position: Position) -> None` — UPSERT into `positions`.
- [ ] **Step 5:** implement query helpers: `list_evaluations(strategy_id, limit, offset)`, `list_trades(strategy_id, limit, offset)`, `list_all_trades(limit, mode_filter)`.
- [ ] **Step 6:** unit tests for each method against a tmp SQLite DB.
- [ ] **Step 7:** commit: `feat(logs): trade_log service with evaluation + trade + position writers`.

**Acceptance:** Every cron tick can be logged and queried back.

---

### Task 2.3 — allocation_service

**Agent:** backend-developer
**Files:**
- Create: `server/src/services/allocation_service.py`
- Create: `server/tests/unit/test_allocation_service.py`

- [ ] **Step 1:** implement `record_allocation(strategy_id, wallet_address, token_address, token_symbol, amount) -> Allocation` — validate wallet exists, validate amount > 0, INSERT into `allocations` with `active=1`.
- [ ] **Step 2:** implement `release_allocation(strategy_id) -> None` — UPDATE active allocations for the strategy: set `active=0`, `released_at=now`.
- [ ] **Step 3:** implement `get_active_allocation(strategy_id) -> Allocation | None`.
- [ ] **Step 4:** unit tests including the wallet-not-found case (raises `WalletNotFound`).
- [ ] **Step 5:** commit: `feat(allocations): per-strategy fund accounting service`.

**Acceptance:** Live strategy activation records an allocation; deactivation releases it.

---

### Task 2.4 — scheduler_service

**Agent:** backend-developer
**Files:**
- Create: `server/src/services/scheduler_service.py`
- Create: `server/tests/unit/test_scheduler_service.py`

- [ ] **Step 1:** implement module-level `BackgroundScheduler` with `SQLAlchemyJobStore(url=f"sqlite:///{app_config.DB_PATH}")`. Lazy init.
- [ ] **Step 2:** add timeframe-to-cron mapping table from architecture doc (1m → `*/1 * * * *`, etc.).
- [ ] **Step 3:** implement `register_job(strategy_id, timeframe, callable_path) -> str` — adds a `CronTrigger` job named `eval-<strategy_id>`. Idempotent (replace existing).
- [ ] **Step 4:** implement `cancel_job(strategy_id) -> None` and `list_active_jobs() -> list[dict]`.
- [ ] **Step 5:** wire scheduler `start()` into FastAPI lifespan; `shutdown()` on app stop.
- [ ] **Step 6:** unit tests:
  - register a job, list jobs, assert it's there
  - cancel, assert it's gone
  - register same strategy twice, assert no duplicates
- [ ] **Step 7:** commit: `feat(scheduler): APScheduler wrapper with SQLite jobstore`.

**Acceptance:** Jobs persist across app restart; canceling removes them.

---

## Phase 3 — Strategy Pipeline

Goal: the autonomous strategy creation flow + cron evaluation work end-to-end against the SDK.

### Task 3.1 — candidate_generator

**Agent:** backend-developer
**Files:**
- Create: `server/src/services/candidate_generator.py`
- Create: `server/tests/unit/test_candidate_generator.py`

- [ ] **Step 1:** define a deterministic mapping table — goal keywords → signal categories. Use the categories returned by `mangroveai.signals`. Example seed mapping:
  ```python
  GOAL_TO_CATEGORIES = {
      "momentum": {"trigger": ["momentum", "trend"], "filter": ["volume", "trend"]},
      "mean_reversion": {"trigger": ["overbought_oversold"], "filter": ["volatility"]},
      "breakout": {"trigger": ["breakout"], "filter": ["volume"]},
      "trend": {"trigger": ["trend"], "filter": ["momentum", "volume"]},
  }
  ```
- [ ] **Step 2:** implement `parse_goal(goal: str) -> dict` — detect keywords case-insensitive; default to "momentum" if none match.
- [ ] **Step 3:** implement `generate(goal, asset, timeframe, n=7) -> list[StrategyCandidate]`:
  - Fetch signal catalog via `mangroveai_client().signals.list()`
  - Filter by category buckets from the parsed goal
  - For each of n candidates: random-pick 1 trigger, 0–2 filters for entry; 0–1 trigger + 0+ filters for exit
  - Use sensible default param values from the signal metadata
  - Deterministic with a seed (so backtests are reproducible)
- [ ] **Step 4:** unit tests:
  - `test_parse_goal` — known phrasing → expected categories
  - `test_generate_seeded` — same seed produces same candidates
  - `test_generate_respects_composition_rules` — entry has exactly 1 trigger, exit has 0–1
- [ ] **Step 5:** commit: `feat(candidates): deterministic goal-to-strategy candidate generator`.

**Acceptance:** Calling `generate("momentum on ETH", "ETH", "1h")` returns 7 well-formed candidates that pass `mangroveai`'s strategy schema.

---

### Task 3.2 — backtest_service

**Agent:** backend-developer
**Files:**
- Create: `server/src/services/backtest_service.py`
- Create: `server/tests/integration/test_backtest_service.py`

- [ ] **Step 1:** implement `quick_backtest_all(candidates, asset, timeframe, lookback_months) -> list[BacktestResult]`:
  - For each candidate, call `mangroveai_client().backtesting.run(mode="quick", ...)` with the candidate's strategy_json
  - Capture per-candidate metrics
- [ ] **Step 2:** implement `filter_and_rank(results) -> list[BacktestResult]`:
  - Drop any with `win_rate <= 0.51` or `total_trades < 10`
  - Sort surviving by `irr_annualized` descending
- [ ] **Step 3:** implement `full_backtest(strategy_json, lookback_months, start_date=None, end_date=None) -> BacktestResult`.
- [ ] **Step 4:** integration tests against the dev Mangrove env:
  - `test_quick_backtest_returns_metrics` — assert all expected metric fields populated
  - `test_filter_drops_low_win_rate`
  - `test_filter_drops_low_trade_count`
  - `test_rank_by_irr`
  - `test_full_backtest_returns_trades` — full mode includes trade history
- [ ] **Step 5:** commit: `feat(backtest): quick + full backtest orchestration with IRR ranking`.

**Acceptance:** Pipeline runs 7 candidates in <30s wall clock against dev env, returns ranked list.

---

### Task 3.3 — order_executor

**Agent:** backend-developer
**Files:**
- Create: `server/src/services/order_executor.py`
- Create: `server/tests/unit/test_order_executor.py`
- Create: `server/tests/integration/test_order_executor_live.py`

- [ ] **Step 1:** define `execute_one(intent: OrderIntent, mode: Literal["paper", "live"], wallet_address: str | None = None) -> Trade`. For paper: skip to step 3. For live: continue.
- [ ] **Step 2 (live mode):** implement the full 6-step swap from the spec:
  1. `dex.get_quote(input_token, output_token, amount, chain_id)` → Quote
  2. `dex.approve_token(...)` → may return None (already approved)
  3. If approval returned: `wallet_manager.sign(approval_tx, wallet_address)` → signed → `dex.broadcast(signed)` → poll `dex.tx_status` until confirmed
  4. `dex.prepare_swap(quote_id, wallet_address)` → UnsignedTx
  5. `wallet_manager.sign(swap_tx, wallet_address)` → signed → `dex.broadcast(signed)` → poll `dex.tx_status`
  6. Build `Trade` with `mode="live"`, `tx_hash`, fill amounts/prices/fees
- [ ] **Step 3 (paper mode):** fetch current price via `mangroveai_client().crypto_assets.get_market_data(intent.symbol)`, build a `Trade` with `mode="paper"`, `status="simulated"`, `tx_hash=None`, fill at mid/mark price.
- [ ] **Step 4:** call `trade_log.log_trade(trade)` and `trade_log.update_position(...)` based on intent type (enter/exit). Return the `Trade`.
- [ ] **Step 5:** add `execute_many(intents, mode, wallet_address) -> list[Trade]` — sequential loop, each wrapped in try/except so one failure doesn't stop the batch.
- [ ] **Step 6:** unit tests with mocked SDK:
  - `test_paper_simulates_at_mark_price` — no SDK swap calls made
  - `test_live_skips_approval_when_none` — no approval signed
  - `test_live_full_flow_with_approval` — both txs signed and broadcast
  - `test_failure_in_one_does_not_block_others` (for execute_many)
- [ ] **Step 7:** integration test against Base testnet (Chain ID 84532) with a funded testnet wallet — actually swap a small amount and verify the trade row.
- [ ] **Step 8:** commit: `feat(executor): single swap path for cron-driven and user-initiated trades`.

**Acceptance:** Paper mode logs simulated trades; live mode (testnet) completes a real swap and writes a Trade row with the tx hash.

---

### Task 3.4 — strategy_service

**Agent:** backend-developer
**Files:**
- Create: `server/src/services/strategy_service.py`
- Create: `server/tests/integration/test_strategy_service.py`

- [ ] **Step 1:** implement `create_autonomous(req: StrategyCreateAutonomousRequest) -> StrategyDetail`:
  1. `candidate_generator.generate(...)` → list of candidates
  2. `backtest_service.quick_backtest_all(...)` → results
  3. `filter_and_rank(...)` → survivors
  4. If empty: raise `StrategyNoViableCandidates` with suggestion
  5. `backtest_service.full_backtest(winner)` → full metrics
  6. `mangroveai_client().strategies.create(winner)` → mangrove_id
  7. Cache locally in `strategies` table with `generation_report_json`
  8. Return `StrategyDetail`
- [ ] **Step 2:** implement `create_manual(req)` — validate composition (1 TRIGGER + 0+ FILTERs entry; 0–1 TRIGGER + 0+ FILTERs exit), call `mangroveai_client().strategies.create(...)`, cache locally.
- [ ] **Step 3:** implement `list_strategies(status_filter, limit, offset)` and `get_strategy(id)` — read from local cache.
- [ ] **Step 4:** implement `update_status(id, status, confirm, allocation) -> StrategyDetail`:
  - Validate transition per spec (`StrategyInvalidStatusTransition` if illegal)
  - `confirm=True` required for live activation or live deactivation
  - On `→ live`: validate allocation block, call `allocation_service.record_allocation()`, call `mangroveai_client().strategies.update_status()`, register cron job via `scheduler_service.register_job(strategy_id, timeframe, "src.services.strategy_service.tick")`
  - On `→ paper`: register cron, no allocation
  - On `→ inactive` or `→ archived`: cancel cron, release allocation if any
- [ ] **Step 5:** implement `tick(strategy_id) -> Evaluation` — the cron callback:
  1. Load strategy from local cache
  2. Fetch latest market data via `mangroveai_client().crypto_assets.get_ohlcv(...)`
  3. Call `mangroveai_client().execution.evaluate(strategy_mangrove_id, current_data)` → SDK response with OrderIntent[]
  4. If orders empty: log evaluation with `status="ok"`, no trades
  5. If orders present: extract OrderIntents, dispatch to `order_executor.execute_many(intents, mode, wallet_address)`, log evaluation with sdk_response_json verbatim
  6. Catch SDK errors → log evaluation with `status="error"`, `error_msg=str(e)` — never crash the scheduler
- [ ] **Step 6:** integration tests:
  - `test_create_autonomous_happy_path` — produces a StrategyDetail with generation_report
  - `test_create_autonomous_no_viable_candidates` — raises 422
  - `test_status_transition_paper_to_live_requires_confirm`
  - `test_status_transition_to_live_registers_cron_and_allocation`
  - `test_tick_paper_mode_logs_simulated_trade`
- [ ] **Step 7:** commit: `feat(strategy): orchestration service for create, lifecycle, and cron tick`.

**Acceptance:** Calling `create_autonomous` produces a working strategy in Mangrove + local cache; activating to paper registers a cron that ticks and logs.

---

## Phase 4 — API Layer

Goal: every spec endpoint and MCP tool is wired up. After this phase, the agent is feature-complete from the user's perspective.

### Task 4.1 — Discovery routes

**Agent:** backend-developer
**Files:**
- Create: `server/src/api/routes/discovery.py`
- Modify: `server/src/api/router.py` (mount under `/api/v1/agent`)
- Create: `server/tests/integration/test_discovery_routes.py`

- [ ] **Step 1:** create `GET /tools` — return MCP tool catalog (placeholder; will be auto-populated once MCP tools are registered in 4.7).
- [ ] **Step 2:** create `GET /status` — return `{version, wallets_count, strategies: {…}, active_cron_jobs, db_path, uptime_seconds}`.
- [ ] **Step 3:** ensure `/health` already works (template provides it).
- [ ] **Step 4:** integration tests for each endpoint.
- [ ] **Step 5:** commit: `feat(api): discovery routes (status, tools)`.

**Acceptance:** `curl http://localhost:8080/api/v1/agent/status` returns the spec-defined shape.

---

### Task 4.2 — Wallet routes

**Agent:** backend-developer
**Files:**
- Create: `server/src/api/routes/wallet.py`
- Create: `server/src/models/requests.py`, `server/src/models/responses.py` (start; will grow)
- Create: `server/tests/integration/test_wallet_routes.py`

- [ ] **Step 1:** define request/response Pydantic models for wallet endpoints from the spec.
- [ ] **Step 2:** implement routes:
  - `POST /wallet/create` → `wallet_manager.create_wallet(...)`
  - `GET /wallet/list` → `wallet_manager.list_wallets()`
  - `GET /wallet/{address}/balances?chain_id` → `mangrovemarkets_client().dex.balances(chain_id, address)` directly
  - `GET /wallet/{address}/portfolio?chain_id` → `mangrovemarkets_client().portfolio.value/pnl/tokens/defi(...)` directly, aggregate
  - `GET /wallet/{address}/history?limit` → `mangrovemarkets_client().portfolio.history(...)` directly
- [ ] **Step 3:** wire auth via the existing middleware (auth required on all wallet endpoints).
- [ ] **Step 4:** integration tests for create + list happy paths and `WalletNotFound` error.
- [ ] **Step 5:** commit: `feat(api): wallet routes`.

**Acceptance:** Full wallet workflow works via REST.

---

### Task 4.3 — DEX routes

**Agent:** backend-developer
**Files:**
- Create: `server/src/api/routes/dex.py`
- Create: `server/tests/integration/test_dex_routes.py`

- [ ] **Step 1:** routes that pass through to SDK directly:
  - `GET /dex/venues` → `mangrovemarkets_client().dex.supported_venues()`
  - `GET /dex/pairs?venue_id` → `mangrovemarkets_client().dex.supported_pairs(venue_id)`
  - `POST /dex/quote` → `mangrovemarkets_client().dex.get_quote(...)`
- [ ] **Step 2:** `POST /dex/swap`:
  - Require `confirm=True` else raise `ConfirmationRequired`
  - Build `OrderIntent` from request body
  - Call `order_executor.execute_one(intent, mode="live", wallet_address=req.wallet_address)`
  - Return `SwapResult` populated from the returned `Trade`
- [ ] **Step 3:** integration tests including the `confirm=False` rejection path.
- [ ] **Step 4:** commit: `feat(api): DEX routes (venues, pairs, quote, swap)`.

**Acceptance:** End-to-end swap (testnet) via `POST /dex/swap` works.

---

### Task 4.4 — Pass-through routes (market, on-chain, signals, KB)

**Agent:** backend-developer
**Files:**
- Create: `server/src/api/routes/market.py`
- Create: `server/src/api/routes/on_chain.py`
- Create: `server/src/api/routes/signals.py`
- Create: `server/src/api/routes/kb.py`
- Create: `server/tests/integration/test_passthrough_routes.py`

- [ ] **Step 1:** market routes — all delegate to `mangroveai_client().crypto_assets.*`:
  - `GET /market/ohlcv?symbol&timeframe&lookback_days`
  - `GET /market/data?symbol`
  - `GET /market/trending`
  - `GET /market/global`
- [ ] **Step 2:** on-chain routes — delegate to `mangroveai_client().on_chain.*`:
  - `GET /on-chain/smart-money?symbol&chain`
  - `GET /on-chain/whale-activity?symbol&hours_back`
  - `GET /on-chain/token-holders/{symbol}`
- [ ] **Step 3:** signals routes — delegate to `mangroveai_client().signals.*`:
  - `GET /signals?category&search&limit`
  - `GET /signals/{name}`
- [ ] **Step 4:** KB routes — delegate to `mangroveai_client().kb.*`:
  - `GET /kb/search?q&limit`
  - `GET /kb/glossary/{term}`
- [ ] **Step 5:** one integration test per route that just confirms the SDK call succeeds and the response is well-formed (mock the SDK; we're testing the wiring, not the SDK).
- [ ] **Step 6:** commit: `feat(api): market + on-chain + signals + KB routes`.

**Acceptance:** All pass-through endpoints reachable via REST.

---

### Task 4.5 — Strategy routes

**Agent:** backend-developer
**Files:**
- Create: `server/src/api/routes/strategies.py`
- Create: `server/tests/integration/test_strategy_routes.py`

- [ ] **Step 1:** define request/response models for all strategy endpoints from the spec.
- [ ] **Step 2:** implement routes (all delegate to `strategy_service`):
  - `POST /strategies/autonomous`
  - `POST /strategies/manual`
  - `GET /strategies?status&limit&offset`
  - `GET /strategies/{id}`
  - `PATCH /strategies/{id}/status` — single source of truth for lifecycle (incl. allocation in body for live)
  - `POST /strategies/{id}/backtest` — `{mode, lookback_months, start_date?, end_date?}`
  - `POST /strategies/{id}/evaluate` — manual tick (debugging)
- [ ] **Step 3:** integration tests including the autonomous happy path, the no-viable-candidates 422, and the live-without-confirm 400.
- [ ] **Step 4:** commit: `feat(api): strategy routes (CRUD, lifecycle, backtest, evaluate)`.

**Acceptance:** Full strategy lifecycle reachable via REST.

---

### Task 4.6 — Logs routes

**Agent:** backend-developer
**Files:**
- Create: `server/src/api/routes/logs.py`
- Create: `server/tests/integration/test_logs_routes.py`

- [ ] **Step 1:** implement routes (all delegate to `trade_log`):
  - `GET /strategies/{id}/evaluations?limit&offset`
  - `GET /strategies/{id}/trades?limit&offset`
  - `GET /trades?limit&strategy_id&mode`
- [ ] **Step 2:** integration tests against a seeded SQLite.
- [ ] **Step 3:** commit: `feat(api): log routes`.

**Acceptance:** Audit trail queryable via REST.

---

### Task 4.7 — MCP tool registration

**Agent:** backend-developer
**Files:**
- Modify: `server/src/mcp/tools.py`
- Modify: `server/src/mcp/registry.py` (if helpers needed)
- Create: `server/tests/integration/test_mcp_tools.py`

- [ ] **Step 1:** for every REST route in 4.1–4.6, register a matching MCP tool. Tool names from `docs/specification.md` MCP Tools table — plain `verb_resource` form, no project prefix.
- [ ] **Step 2:** core 22 tools first (see spec); nice-to-haves last. Each tool calls the same service function the REST route does — never duplicate logic.
- [ ] **Step 3:** ensure `GET /api/v1/agent/tools` returns the now-populated catalog from the registry.
- [ ] **Step 4:** integration test — start the app, connect via FastMCP test client, list tools, call `status` and assert response.
- [ ] **Step 5:** commit: `feat(mcp): register all agent tools mirroring REST routes`.

**Acceptance:** Claude Code with `.mcp.json` pointing to the agent can list and call all tools.

---

## Phase 5 — Verification

Goal: prove the full system works end-to-end.

### Task 5.1 — Endpoint smoke test

**Agent:** test-engineer
**Files:**
- Create: `server/tests/e2e/test_smoke.py`

- [ ] **Step 1:** parametrized test that hits every REST endpoint with valid input and asserts 2xx + a basic response shape. Use a fixture that sets `ENVIRONMENT=test` and a tmp DB.
- [ ] **Step 2:** also invoke each MCP tool via test client.
- [ ] **Step 3:** run `pytest server/tests/e2e/test_smoke.py` — must pass.
- [ ] **Step 4:** commit: `test(e2e): smoke test for all endpoints + MCP tools`.

**Acceptance:** Every endpoint returns the expected status code on a happy-path call.

---

### Task 5.2 — E2E paper trading lifecycle

**Agent:** test-engineer
**Files:**
- Create: `server/tests/e2e/test_paper_lifecycle.py`

- [ ] **Step 1:** test scenario:
  1. Create wallet (EVM testnet)
  2. Create autonomous strategy (`{goal: "momentum", asset: "ETH", timeframe: "5m"}`)
  3. Activate to `paper`
  4. Wait for one cron tick (or invoke `/strategies/{id}/evaluate` manually)
  5. Assert at least one evaluation row exists
  6. If orders fired, assert simulated trades logged (mode=paper, status=simulated)
  7. Deactivate to `inactive` (cron should be removed)
- [ ] **Step 2:** uses the dev Mangrove env. Skip if `SKIP_E2E=1`.
- [ ] **Step 3:** commit: `test(e2e): paper trading full lifecycle`.

**Acceptance:** A user can chat-driven create → backtest → deploy paper → see logs without errors.

---

### Task 5.3 — E2E live swap on testnet

**Agent:** test-engineer
**Files:**
- Create: `server/tests/e2e/test_live_swap.py`

- [ ] **Step 1:** test scenario:
  1. Create EVM wallet on Base testnet (Chain ID 84532)
  2. Pre-fund manually (test fixture documents the funded address; runner must seed before the test)
  3. POST `/dex/swap` with `confirm=true` for a tiny amount (e.g., 0.001 USDC → ETH)
  4. Assert response includes `tx_hash` and `status=confirmed`
  5. Query the trades table — assert the row matches
- [ ] **Step 2:** Skip if `SKIP_E2E=1` or `BASE_TESTNET_PRIVATE_KEY` not set.
- [ ] **Step 3:** commit: `test(e2e): live DEX swap on Base testnet`.

**Acceptance:** Live execution path works against a real chain.

---

## Phase 6 — Workshop Polish

Goal: anyone cloning the repo on workshop day can `docker compose up`, hand Claude Code an `.mcp.json`, and have a working trading bot.

### Task 6.1 — Docs polish

**Agent:** backend-developer
**Files:**
- Modify: `README.md`
- Create: `.mcp.json.example`
- Modify: `docs/configuration.md` (refresh to match the agent's actual config)

- [ ] **Step 1:** rewrite the top of `README.md` for defi-agent: what it is, quick start (3 commands), where to put your API key, link to spec/architecture.
- [ ] **Step 2:** create `.mcp.json.example` with the Streamable HTTP transport config from the spec.
- [ ] **Step 3:** refresh `docs/configuration.md` to match the v1 config keys.
- [ ] **Step 4:** commit: `docs: README + .mcp.json example for workshop`.

**Acceptance:** A new user can read the README and be running in <5 min.

---

### Task 6.2 — Final docker-compose verify

**Agent:** devops-engineer
**Files:**
- Modify: `docker-compose.yml` if needed
- Modify: `server/Dockerfile` if needed

- [ ] **Step 1:** mount `./agent.db` as a volume so it survives container restarts.
- [ ] **Step 2:** ensure `local-config.json` is mounted from a host path (or built into the image at build time for the workshop demo).
- [ ] **Step 3:** end-to-end smoke: `docker compose down -v`, `docker compose up --build`, run smoke test from 5.1 against the running container.
- [ ] **Step 4:** commit: `chore(docker): persistent volume + config mount`.

**Acceptance:** `docker compose up` produces a working agent that survives restart with state intact.

---

### Task 6.3 — Code review pass

**Agent:** code-review
**Files:** all modified files since branch start

- [ ] **Step 1:** run code-review across the diff vs. main. Address findings in follow-up commits.
- [ ] **Step 2:** verify against `.claude/rules/code-style.md` (if present) and the repo conventions.
- [ ] **Step 3:** verify spec/architecture/plan traceability — every endpoint exists, every service exists, no extra cruft.
- [ ] **Step 4:** commit any review fixes.

**Acceptance:** No blocking findings; ready for merge.

---

## Summary

**Total: 22 tasks across 6 phases.**

| Phase | Tasks | Parallelizable? |
|-------|-------|-----------------|
| 1. Foundation & cleanup | 6 | Mostly sequential (1.1 → 1.2 → 1.3 → 1.4/1.5 parallel → 1.6) |
| 2. Core infrastructure | 4 | 2.2/2.3/2.4 parallel after 2.1 |
| 3. Strategy pipeline | 4 | 3.1/3.2 parallel after Phase 2; 3.3 needs 2.1; 3.4 needs all of Phase 3 |
| 4. API layer | 7 | 4.1–4.6 parallel after Phase 3; 4.7 last |
| 5. Verification | 3 | Sequential |
| 6. Polish | 3 | Sequential |

**Critical path (sequential):** 1.1 → 1.2 → 1.3 → 1.6 → 2.1 → 3.3 → 3.4 → 4.7 → 5.x → 6.x.

**Agent allocation:**
- backend-developer: 16 tasks
- test-engineer: 3 tasks
- devops-engineer: 1 task
- code-review: 1 task (final pass)
- diagram-agent: not needed (diagrams already approved in arch phase)

**Definition of done for v1:** all 22 tasks complete + paper lifecycle E2E green + live swap E2E green + `docker compose up` produces a working agent + README quick-start works.
