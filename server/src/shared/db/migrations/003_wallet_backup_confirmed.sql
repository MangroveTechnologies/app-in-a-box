-- Backup-confirmation gate for live trading.
--
-- The wallet secret is encrypted at rest by the agent's master key. If the
-- master key is ever lost (disk failure, bad config migration, container
-- destroyed without preserving agent-data/), the encrypted_secret in
-- `wallets` becomes permanently undecryptable — the agent can no longer
-- sign for that wallet, and funds become unrecoverable unless the user
-- has an off-agent backup of the plaintext secret (e.g. in a password
-- manager or hardware wallet).
--
-- `backup_confirmed_at` is set when the user has explicitly confirmed
-- they've saved the secret outside the agent (via `./scripts/confirm-
-- backup.sh`, which flips this flag — the confirm script does NOT see or
-- transmit the secret itself, it just sets the flag by wallet address).
--
-- The agent MUST refuse `execute_swap` and `update_strategy_status → live`
-- for wallets where this column is NULL. Paper mode is unaffected (no
-- real funds at risk). This turns the "user forgot to back up" scenario
-- from a silent disaster into a blocking gate.

ALTER TABLE wallets ADD COLUMN backup_confirmed_at TEXT;
CREATE INDEX IF NOT EXISTS idx_wallets_backup_confirmed ON wallets(backup_confirmed_at);
