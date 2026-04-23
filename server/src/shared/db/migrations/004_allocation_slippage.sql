-- Migration 004: allocation.slippage_pct
--
-- Add per-allocation slippage tolerance so cron-driven live swaps use
-- the user's declared risk tolerance, not a silent fallback.
--
-- Units: DECIMAL (0.005 = 0.5%). Capped at 0.0025 (0.25%) in the
-- Pydantic input layer (src/services/strategy_service.py
-- StrategyAllocationInput). Nullable in DB so existing allocation rows
-- from pre-migration states survive — the cron path raises on None
-- rather than silently falling back.

ALTER TABLE allocations ADD COLUMN slippage_pct REAL;
