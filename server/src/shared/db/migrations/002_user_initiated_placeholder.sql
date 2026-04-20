-- Seed a "user-initiated" placeholder strategy row so trades from the
-- /dex/swap route (which don't belong to any real strategy) can satisfy
-- the trades.strategy_id FK.
--
-- Safe to re-run: ON CONFLICT DO NOTHING.

INSERT OR IGNORE INTO strategies
    (id, mangrove_id, name, asset, timeframe, status,
     entry_json, exit_json, execution_config_json,
     generation_report_json, created_at, updated_at)
VALUES
    ('user-initiated', 'user-initiated', 'User-initiated trades', '', '1h', 'archived',
     '[]', '[]', '{}', NULL,
     '2026-04-20T00:00:00+00:00', '2026-04-20T00:00:00+00:00');
