---
name: create-strategy
description: >-
  Use when the user wants to build a new trading strategy — "build me a
  momentum play on ETH", "find a strategy for BTC", "I want to trade X",
  "make a strategy", or after Stage 0 greeter when the wallet is ready
  and the user is moving into Stage 2 (Author) of trading-bot-workflow.md.
  Drives the author → backtest path using reference strategies (Mechanism
  2) and KB-grounded parameter choices (Mechanism 1) so parameters are
  evidence-backed, not library-default guesses. Wraps
  search_reference_strategies + build_strategy_from_reference +
  create_strategy_autonomous + create_strategy_manual + kb_search.
---

# Create Strategy Skill

The agent's job in this skill: turn a loose user goal ("momentum on ETH")
into a strategy config with **specific signals and specific parameters
backed by evidence**, not library defaults.

Two mechanisms drive "intuition":

- **Mechanism 2 (reference strategies) — the primary path.** Curated
  known-good configs. The agent searches these FIRST, presents matches
  to the user, and materializes the chosen one exactly. Zero parameter
  guessing for the common case.
- **Mechanism 1 (KB-grounded parameters) — the fallback.** When
  references don't fit (unusual asset, unusual goal, or user wants to
  modify), the agent is REQUIRED to call `kb_search` for every signal
  it picks before finalizing params. No library-default fallback.

A third mechanism (mined parameter priors from the 1.4M-strategy DB)
will land via MangroveAI endpoint after MangroveOracle issue #156. This
skill will transparently benefit once the SDK exposes it — no rewrite
needed here.

## Trigger

Activate when the user:

- Explicitly asks for a strategy ("build me...", "make a strategy", "find me...")
- Is in Stage 2 of `trading-bot-workflow.md` (wallet ready, wants to author)
- Says "trade X", "start running", "put money to work" and a strategy doesn't yet exist

Do NOT activate if the user is asking questions about an existing strategy (use `/monitor-trades` instead) or wants to promote/pause one (use `/promote-strategy`).

## Input — What to Collect

The agent needs four pieces of info before searching references. ORDER these in the order the user volunteered them; if they gave everything in one message, skip straight to Phase A (FAST ADVANCE):

1. **asset** — symbol (BTC, ETH, SOL, etc.). REQUIRED.
2. **timeframe** — 5m / 15m / 30m / 1h / 4h / 1d. Default 1h if user unclear. **1m is NOT supported** — the server will reject it. If the user asks for 1m, say: "1m isn't supported on the Mangrove data source; the smallest is 5m, but I'd recommend 1h for a first strategy — less noise, faster to backtest."
3. **goal / style** — natural language. Used for category detection (momentum, mean_reversion, trend_following, breakout, volatility).
4. **appetite for trades** — high-frequency (many small edges) vs. swing (fewer, bigger moves). Affects which references to recommend.

FAST ADVANCE: if the user's first message has asset + strategy_type + timeframe, skip the Q&A and go straight to Phase A. Infer the rest (knowledge level, sentiment) from tone — don't ask unnecessary clarifying questions.

Example FAST ADVANCE triggers:
- "Build a momentum strategy for ETH on 1h" → asset=ETH, timeframe=1h, goal=momentum
- "Give me a trend following BTC 4h setup" → asset=BTC, timeframe=4h, goal=trend_following

## Phase A — Search References (ALWAYS DO THIS FIRST)

Call `search_reference_strategies(asset, timeframe, goal_hint)`. You will get back up to 5 ranked candidates, each with:

- `id` (e.g. `ref-004`)
- `label` (human-readable)
- `description` (why this works)
- `entry_signals` + `exit_signals` (names, types, params)
- `category`
- `notes` (tuning hints)

Present the top 2-3 to the user, ranked. For each: show the label, the signal names (not param values — too noisy), the category, and one sentence from `description`. Ask: "Want to use one of these, or should I design something custom?"

If `search_reference_strategies` returns 0 results or only low-score matches: jump to **Phase C (Custom build, KB-grounded)**.

## Phase B — Build from Reference (PREFERRED)

User picks a reference (by id or label). Call `build_strategy_from_reference(reference_id, timeframe=<user's>, name=<optional>)`.

You get back a `create_strategy_manual`-compatible payload. Pass it directly to `create_strategy_manual(...)` — DO NOT modify `entry`, `exit`, or `execution_config`. The whole point of Mechanism 2 is that these values came from strategies that already backtested well.

Only adjustable fields:

- `timeframe` override (already handled by build_strategy_from_reference)
- `name` (cosmetic)

If the user wants to TWEAK the reference (e.g. "but use RSI(9) not RSI(14)"): acknowledge their change, then move to Phase C's KB-citation discipline BEFORE applying the tweak. Don't change params without citation.

## Phase C — Custom Build (KB-GROUNDED, Mechanism 1)

Use this path when:
- Reference search returned nothing useful
- User explicitly wants something unusual (e.g. "combine Ichimoku and Bollinger breakouts")
- User wants to tweak a reference's parameters

**For each signal you consider, you MUST:**

1. Call `kb_search(query="<signal_name> parameters <asset> <timeframe>")`. Example: `kb_search("MACD parameters ETH 1h")`.
2. Read the top 1-3 results. Extract the recommended parameter range or default.
3. In your response, CITE the KB result verbatim (or paraphrase + attribute): "KB recommends MACD(8, 21, 5) for 1h crypto — tighter than the stock 12/26/9 because 1h bars have less noise than daily."
4. Only then write the param values into the strategy.

**Do NOT use library-default params without KB citation.** If the KB has nothing, say so: "KB doesn't have guidance on this specific (signal, asset, timeframe) combo. I'll use the signal's declared default [X] but flag it — consider running a wider backtest to validate."

Composition rules (TRIGGER vs FILTER) — from MangroveAI signal spec:

- **Entry**: EXACTLY ONE TRIGGER + ZERO OR MORE FILTERS
- **Exit**: ZERO OR ONE TRIGGER + ZERO OR MORE FILTERS
- **NEVER a FILTER without a TRIGGER in the same group**
- If the user doesn't specify exits explicitly, use `exit: []` — the volatility-based stop-loss + take-profit are AUTOMATIC at entry, not exit rules
- Each signal does ONE thing (Single Responsibility). Don't stack two momentum triggers; don't mix concepts.

When the config is ready, call `create_strategy_manual(...)` with it.

## Phase D — Autonomous path (FALLBACK when user says "just pick something")

If the user doesn't want to choose a reference or design custom, call `create_strategy_autonomous(goal, asset, timeframe)` with the user's goal text. The server generates N candidates, backtests them in bulk, and returns the winner.

Autonomous is the "I don't care, you decide" escape hatch. It's NOT the primary path — references are. Use autonomous when:
- User explicitly says "pick for me" / "surprise me" / "you decide"
- Phase A returned nothing AND Phase C is too much friction for the user's patience
- You've tried Phase B/C and the user rejected the results

Under no circumstances go straight to Phase D as the first move. Always try Phase A first.

## Phase E — Backtest

Regardless of which phase built the strategy, hand off to backtesting immediately:

```
backtest_strategy(strategy_id, mode="full")
```

Omit `lookback_*` and date fields unless the user asked for a specific window — `backtest_service` picks a timeframe-aware default via `recommended_lookback_months(timeframe)`: 3 months for 5m/15m/30m/1h, 6 months for 4h, 12 months for 1d.

Overrides go through the single `config` dict (matches `trading_defaults.json` keys). Example:
```
backtest_strategy(strategy_id, mode="full", lookback_hours=24, config={"slippage_pct": 0.002})
```

## Phase F — Review (PASS/FAIL against threshold_spec)

Evaluate the backtest against 6 fixed thresholds from `server/src/services/data/threshold_spec.json` (copied verbatim from MangroveAI — `git diff` vs upstream is the drift check):

| Metric | Threshold | Direction |
|---|---|---|
| `sortino_ratio` | ≥ 1.5 | higher is better |
| `sharpe_ratio` | ≥ 1.2 | higher is better |
| `calmar_ratio` | ≥ 1.0 | higher is better |
| `irr_annualized` | ≥ 0.15 | higher is better |
| `max_drawdown` | ≤ 0.7 | lower is better |
| `win_rate` | ≥ 0.25 | higher is better |

**Decision rule:**
- **PASS** iff ALL six thresholds satisfied
- **MARGINAL** if 4-5 of 6 satisfied (worth iterating; not ready for live)
- **FAIL** if ≤ 3 of 6 satisfied (redesign or reject)

### Present the verdict

Always show the user:
1. The verdict (PASS / MARGINAL / FAIL)
2. Per-threshold breakdown — actual value vs threshold, ✓ or ✗ per row
3. Next-step recommendation based on verdict:
   - **PASS** → "Promote to paper (unrestricted) or live (requires allocation + backup confirmation). Which?"
   - **MARGINAL** → "Iterate: widen backtest window, tweak params, or try a different reference. Want me to rerun with {specific change}?"
   - **FAIL** → "This won't work as-is. Options: pick a different reference, change the goal, or accept it's not a viable strategy right now."

### Never fabricate metrics

If the `metrics` dict is missing, empty, or any field is null, **say so explicitly** — do not invent values. Quote the exact SDK response:

> "The backtest response is missing `sharpe_ratio` — I can't verdict against the threshold. This usually means the SDK couldn't compute it (too few trades, or the data provider returned insufficient history). Options: rerun with a longer window, or check `resolved_window` in the response to confirm the window the server actually used."

Likewise: if `total_trades == 0`, every ratio metric is meaningless (division by zero or undefined). Report it as **INSUFFICIENT_TRADES** — not PASS, not FAIL. Suggest widening the window or loosening signal filters.

## Prohibited

- **Never** claim a signal is "firing" based on catalog listing alone. Only `evaluate_strategy` output can claim that.
- **Never** fabricate backtest metrics. If `metrics` missing from a tool response, say so.
- **Never** use library-default params in Phase C without KB citation.
- **Never** modify a reference's params in Phase B — move to Phase C if the user wants changes.
- **Never** invent signal names not returned by `list_signals` or a reference strategy. If you don't have a name, call `list_signals` first.
- **Never** place a FILTER without a TRIGGER in the same group (entry or exit).
- **Never** recommend 1m timeframes — server rejects them.

## Never Default to Swap Router

Manual swaps (`get_swap_quote` / `execute_swap`) are a fallback. Only route there if the strategy layer is down (`search_reference_strategies` + `create_strategy_autonomous` both fail), and disclose it.

## Summary — Decision Tree

```
User wants a strategy
│
├─→ Phase A: search_reference_strategies(asset, timeframe, goal_hint)
│       │
│       ├─ ≥1 good match → present to user → pick → Phase B
│       ├─ 0 good matches → Phase C
│       └─ user says "just pick" → Phase D (autonomous)
│
├─ Phase B: build_strategy_from_reference + create_strategy_manual
│       (signals + params copied exactly, timeframe applied)
│
├─ Phase C: kb_search each signal → cite → create_strategy_manual
│       (custom, evidence-backed)
│
└─ Phase D: create_strategy_autonomous(goal, asset, timeframe)
        (server generates + backtests N candidates, returns winner)

→ backtest_strategy (timeframe-aware default window)
→ /review-backtest skill (PASS/FAIL verdict)
→ /promote-strategy skill (draft → paper → live)
```
