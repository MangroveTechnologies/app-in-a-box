# Wallet Presentation Rules

These rules govern how the agent presents wallet operations. They apply to `create_wallet`, `import_wallet`, `get_balances`, and any future wallet tooling.

## Core invariant — the agent NEVER sees plaintext keys

After the phase-2 security rework, wallet secrets flow **out-of-band**. They never enter MCP tool responses, so they never enter Claude Code's conversation context.

- `create_wallet` returns a `vault_token` (opaque, TTL-bound, single-read). The user runs `./scripts/reveal-secret.sh <vault_token>` in a terminal to see the plaintext.
- `import_wallet` accepts a `vault_token` (obtained by the user running `./scripts/stash-secret.sh` first). It never accepts a raw key as an argument.
- Reveal-on-demand for existing wallets is via `./scripts/reveal-secret.sh --address <addr>`, also out-of-band.

**If a user pastes a private key or mnemonic into chat**, `.claude/hooks/block-wallet-secrets.sh` will intercept and refuse the prompt. The hook returns a message directing them to `stash-secret.sh`. Do not try to work around this.

## Defaults — do not ask

When creating a wallet, assume these defaults and state them to the user:

- **Chain:** `evm`
- **Network:** `mainnet`
- **Chain ID:** `8453` (Base)

If the user asks for an alternative, proceed with the default but mention:

> "Base mainnet is the default for v1. Other EVM chains / testnets / XRPL roll out later — check the release notes."

## Presenting `create_wallet` output

### NEVER

- **Never** echo `vault_token` or any wallet secret in prose more than the one time you present the tool's response.
- **Never** ask the user to paste a private key. If they want to import an existing wallet, direct them to `./scripts/stash-secret.sh`.
- **Never** quote, screenshot, or "save" the vault_token after the user has run `reveal-secret.sh` — the vault entry is consumed on reveal; the id is useless afterward.

### ALWAYS

- **Always** display the wallet **address** in a copy-friendly code block, with a clear label.
- **Always** include the block explorer link:
  - Base mainnet → `https://basescan.org/address/<ADDRESS>`
  - Ethereum mainnet → `https://etherscan.io/address/<ADDRESS>`
  - Arbitrum → `https://arbiscan.io/address/<ADDRESS>`
- **Always** tell the user to back up the secret NOW using the `reveal_cmd` from the tool response.
- **Always** explain `master_key_source` in plain language so the user knows where their encryption key lives on this machine.
- **Always** describe the `secret_type` so the user picks the right MetaMask import path (`private_key` → Import Account → Private Key; `mnemonic` → Import Account → Secret Recovery Phrase).
- **Always** surface the `backup_required` flag: live trading is gated until the user runs `confirm-backup.sh`.

### Template for `create_wallet`

```
Wallet created on Base mainnet.

Address:
{ADDRESS}

Block explorer: https://basescan.org/address/{ADDRESS}

Your secret (type: {SECRET_TYPE}) is encrypted at rest with a Fernet
master key stored in {PLAIN_ENGLISH_MASTER_KEY_SOURCE}. Back it up now:

  {REVEAL_CMD}

Run that in a terminal — it opens the secret ONCE and only in your
terminal, never in this chat. Save the output in a password manager,
hardware wallet, or paper. After saving, unlock live trading for this
wallet with:

  ./scripts/confirm-backup.sh {ADDRESS}

Deposit 1-5 USDC to start. I'll verify via get_balances before you send
more.
```

Where `{PLAIN_ENGLISH_MASTER_KEY_SOURCE}` maps from the tool's `master_key_source` field:

| `master_key_source` | Plain English |
|---|---|
| `keyfile` | your local keyfile at `./agent-data/master.key` (chmod 600) |
| `generated_keyfile` | your local keyfile at `./agent-data/master.key` — just created for you, chmod 600 |
| `keychain` | your OS keychain (macOS Keychain / Linux Secret Service / Windows Credential Manager) |

## Presenting `import_wallet` output

Only call `import_wallet` with a `vault_token` the user obtained from `stash-secret.sh`. If they paste a raw key, DO NOT CALL the tool with the key — the hook will block upstream, but also refuse semantically.

### Template for `import_wallet`

```
Wallet imported on Base mainnet.

Address:
{ADDRESS}

Block explorer: https://basescan.org/address/{ADDRESS}

Your secret is already backed up (you just typed it into stash-secret.sh —
that's what gave you the vault_token). The agent auto-confirmed the backup,
so live trading is already unlocked for this wallet.

Run get_balances to verify it's the wallet you expected.
```

## Instructing the user to paste their key — NEVER

If the user says "I want to import my existing wallet" or "here's my key"
(without actually pasting it yet — they will be blocked by the hook if
they do), your response template:

```
I can't accept private keys or mnemonics in chat — the hook will refuse
them, and even if it didn't, they'd end up in your transcript file.

To import your existing wallet safely, open a terminal (VSCode's
integrated terminal works — Cmd+` / Ctrl+`) and run:

  ./scripts/stash-secret.sh

It prompts for the key with input hidden (no echo) and prints a short
vault_token. Come back here, tell me "import wallet vault_token <ID>", and
I'll call the import_wallet tool with that id. Your key will never
touch this conversation.
```

## Checking balances

- Render non-zero balances only unless the user asks for full detail.
- Convert raw token amounts to human-readable units (USDC = 6 decimals, most ERC-20s = 18).
- Show token symbols, not contract addresses, when known. Address in parentheses for verification.

## Rationale

Workshop attendees repeatedly confused private keys with deposit addresses, pasted keys into chat (leaking them to transcripts + Anthropic), and forgot to back up before depositing funds. The phase-2 architecture + this rule file + the regex hook + the backup gate together make those failure modes unavailable at the system level, not just "please don't" conventions.
