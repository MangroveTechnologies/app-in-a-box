# Hank — User Stories & Flows

Scope for the AI trading bot ("Hank", project code: `defi-agent`). These stories and flows define the surface area the Mangrove SDK + MCP server must expose. Endpoint-level detail is in [`api-reference.md`](./api-reference.md).

**Users:** both humans and agents, via chat interface (no UI).
**Funds:** real funds (not testnet).
**Risk management:** fully delegated to the Mangrove API (`execution_config`). The only human-confirmed financial actions are **deposits to a strategy** and **withdrawals from a strategy**.

---

## User Stories

18 stories across 4 categories.

### 1. Wallet & DEX Trading

**US-1:** As a user, I want to create a wallet so that I can hold and trade crypto assets.
- [ ] Supports XRPL and EVM chains
- [ ] Returns address and keys (stored locally, never sent back)
- [ ] Displays funded status

**US-2:** As a user, I want to check my wallet balances so that I know what assets I hold.
- [ ] Shows all token balances for a given wallet/chain
- [ ] Displays in human-readable format with USD values when available

**US-3:** As a user, I want to see available DEX venues and trading pairs so that I know what I can trade.
- [ ] Lists venues with status and fee info
- [ ] Lists pairs per venue with active status

**US-4:** As a user, I want to get a swap quote so that I can evaluate a trade before committing.
- [ ] Returns best quote across venues or from a specific venue
- [ ] Shows input/output amounts, exchange rate, and fees

**US-5:** As a user, I want to execute a token swap so that I can trade one asset for another.
- [ ] Full flow: quote → approve → prepare → sign → broadcast → confirm
- [ ] Agent handles signing locally
- [ ] Transaction status tracked to confirmation

### 2. Market Data & Analytics

**US-6:** As a user, I want to get OHLCV data for an asset so that I can analyze price history.
- [ ] Supports configurable time range (days)
- [ ] Returns timestamp, open, high, low, close, volume

**US-7:** As a user, I want to get real-time market data so that I know current prices and trends.
- [ ] Current price, market cap, volume, 24h/7d change, ATH

**US-8:** As a user, I want to see trending assets and global market data so that I can detect market regime shifts.
- [ ] Trending assets with search volume
- [ ] Total market cap, BTC dominance, 24h change

**US-9:** As a user, I want to view on-chain analytics so that I can follow smart money activity.
- [ ] Smart money flows and holdings
- [ ] Token holder distribution and concentration

**US-10:** As a user, I want to view my portfolio value, P&L, holdings, and transaction history so that I can track performance.
- [ ] Portfolio value across chains
- [ ] P&L metrics
- [ ] Token/DeFi holdings breakdown
- [ ] Transaction history

### 3. Strategy & Execution

**US-11:** As a user, I want to browse and search available signals so that I can build informed strategies.
- [ ] List by category (momentum, trend, volume, volatility)
- [ ] Search by name, params, or keywords
- [ ] View parameter specs (type, min, max, defaults)

**US-12:** As a user, I want to create a trading strategy by composing entry and exit rules from signals so that I can automate my trading logic.
- [ ] Compose entry rules (1 TRIGGER + 0+ FILTERs)
- [ ] Compose exit rules (0-1 TRIGGER + 0+ FILTERs)
- [ ] Configure execution parameters or use defaults
- [ ] Strategy persisted to database

**US-13:** As a user, I want to list and view my strategies so that I can manage my trading portfolio.
- [ ] List with summary view
- [ ] Get full details including rules, config, state

**US-14:** As a user, I want to update my strategy status so that I can move it through its lifecycle.
- [ ] Status transitions: draft → inactive → paper → live → archived

**US-15:** As a user, I want to backtest a strategy against historical data so that I can evaluate its performance.
- [ ] Supports multiple date range modes (explicit, lookback, from-date-to-now)
- [ ] Returns sharpe, sortino, calmar, max drawdown, win rate
- [ ] Returns full trade history with entry/exit details

**US-16:** As a user, I want to evaluate my strategy against current market data so that it can generate trade signals.
- [ ] Loads open positions, checks SL/TP/signal exits
- [ ] Evaluates entry conditions for new positions
- [ ] Persists orders, positions, and trades
- [ ] Stateful execution across evaluations

**US-17:** As a user, I want to deposit funds to a strategy and withdraw from it so that I can fund and manage my trading.
- [ ] Requires explicit human confirmation
- [ ] Only user-confirmed financial action

### 4. Knowledge Base

**US-18:** As a user, I want to search trading docs, glossary, and educational content so that I can learn while I trade.
- [ ] Full-text search across trading documentation
- [ ] Glossary term lookup
- [ ] Browse by tag or category

---

## User Flow Diagrams

Four flows cover all 18 stories.

### Flow 1: Wallet Setup & DEX Swap

```mermaid
flowchart TD
    A[User: I want to trade] --> B{Has wallet?}
    B -->|No| C[Hank: wallet_create]
    C --> D[Store keys locally<br/>Display address + warnings]
    D --> E[User funds wallet<br/>HUMAN CONFIRMATION]
    B -->|Yes| F[Hank: oneinch_balances]
    E --> F
    F --> G[Display balances]
    G --> H[User: Swap X for Y]
    H --> I[Hank: dex_supported_venues<br/>+ dex_supported_pairs]
    I --> J[Hank: dex_get_quote]
    J --> K[Display quote + fees]
    K --> L{User approves?}
    L -->|No| M[Abort]
    L -->|Yes| N{ERC-20 token?}
    N -->|Yes| O[Hank: dex_approve_token]
    O --> P[Sign + dex_broadcast]
    P --> Q[Hank: dex_tx_status<br/>wait for confirmation]
    N -->|No| R[Hank: dex_prepare_swap]
    Q --> R
    R --> S[Sign + dex_broadcast]
    S --> T[Hank: dex_tx_status<br/>wait for confirmation]
    T --> U[Swap complete<br/>Display tx hash]
```

**Covers:** US-1, US-2, US-3, US-4, US-5

---

### Flow 2: Strategy Creation & Backtesting

```mermaid
flowchart TD
    A[User: Build me a strategy] --> B[Hank: GET /signals<br/>or POST /signals/search]
    B --> C[Present available signals<br/>by category]
    C --> D[User selects signals<br/>for entry + exit rules]
    D --> E{Valid composition?}
    E -->|No| F[Explain constraint<br/>Ask user to revise]
    F --> D
    E -->|Yes| G[Hank: POST /strategies<br/>with entry + exit rules]
    G --> H[Strategy created<br/>status=inactive<br/>execution_config defaults loaded]
    H --> I{Backtest?}
    I -->|Yes| J[Hank: POST /backtesting/backtest<br/>with strategy_json + date range]
    J --> K[Return metrics:<br/>sharpe, sortino, max drawdown,<br/>win rate, trade history]
    K --> L{User satisfied?}
    L -->|No| M[Tweak rules or params]
    M --> G
    L -->|Yes| N[Strategy ready<br/>for deployment]
    I -->|No| N
```

**Covers:** US-11, US-12, US-13, US-15

Composition constraint: entry = 1 TRIGGER + 0+ FILTERs, exit = 0–1 TRIGGER + 0+ FILTERs.

---

### Flow 3: Strategy Deployment & Execution

```mermaid
flowchart TD
    A[User: Deploy my strategy] --> B[Hank: GET strategy by id]
    B --> C[Display strategy details]
    C --> D[User: Deposit funds<br/>HUMAN CONFIRMATION]
    D --> E[Deposit transaction executed]
    E --> F[Hank: PATCH strategy status<br/>paper or live]
    F --> G[Strategy active]
    G --> H[Loop: Hank: POST execution evaluate]
    H --> I{Open positions?}
    I -->|Yes| J[Check SL/TP/time/signal exits]
    J --> K{Exit triggered?}
    K -->|Yes| L[Generate exit order<br/>Persist position close]
    K -->|No| M[Hold position]
    I -->|No| N[Check entry signals]
    N --> O{Entry triggered?}
    O -->|Yes| P[Generate entry order<br/>Persist new position]
    O -->|No| Q[No action]
    L --> R[Display new orders<br/>and execution state]
    M --> R
    P --> R
    Q --> R
    R --> S{Continue?}
    S -->|Yes| H
    S -->|No| T[User: Withdraw funds<br/>HUMAN CONFIRMATION]
    T --> U[Hank: PATCH status=inactive<br/>Withdraw transaction executed]
```

**Covers:** US-13, US-14, US-16, US-17

---

### Flow 4: Research & Learning

```mermaid
flowchart TD
    A[User query] --> B{Query type?}
    B -->|Price/market| C[Hank: GET /crypto-assets/market-data<br/>or /ohlcv]
    C --> D[Display current price,<br/>volume, 24h/7d change,<br/>OHLCV series]
    B -->|Market regime| E[Hank: GET /crypto-assets/global-market<br/>+ /trending]
    E --> F[Display BTC dominance,<br/>total market cap,<br/>trending assets]
    B -->|Smart money| G[Hank: GET /smart-money/netflows<br/>+ /holdings<br/>+ /flow-intelligence]
    G --> H[Display flows by wallet type,<br/>holdings, concentration]
    B -->|Portfolio| I[Hank: oneinch_portfolio_value<br/>+ pnl + tokens + defi<br/>+ history]
    I --> J[Display total value,<br/>P&L, holdings,<br/>transaction history]
    B -->|Learning| K[Hank: kb_search<br/>or kb_glossary_lookup]
    K --> L[Display docs,<br/>glossary, backlinks]
    D --> M[User: next action]
    F --> M
    H --> M
    J --> M
    L --> M
```

**Covers:** US-6, US-7, US-8, US-9, US-10, US-18
