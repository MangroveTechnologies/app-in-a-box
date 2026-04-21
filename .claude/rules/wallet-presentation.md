# Wallet Presentation Rules

These rules govern how the agent presents wallet-related tool output to the user. They apply to `create_wallet`, `get_balances`, and any future wallet tooling.

## Defaults — do not ask

When creating a wallet, assume these defaults and state them to the user. **Do not ask the user to choose.**

- **Chain:** `evm`
- **Network:** `mainnet`
- **Chain ID:** `8453` (Base)

If the user asks for an alternative (other EVM chain, testnet, XRPL), say:

> "Base mainnet is the default for v1. Additional chain/network support rolls out via the repo — check the tutorials and release notes."

Then proceed with the default unless the user explicitly insists.

## Creating a wallet — output format

When `create_wallet` returns, the response contains a `seed_phrase` (private key) field and a `deposit_instructions` field. Present them carefully.

### NEVER

- **Never** echo the `seed_phrase` / private key in a formatted code block.
- **Never** repeat the key in prose.
- **Never** highlight, bold, or re-surface the key. The tool's own warning is sufficient — do not amplify it by re-pasting.
- **Never** ask the user to copy the key inline. Direct them to back it up from the raw tool response (or their password manager / hardware wallet).

### ALWAYS

- **Always** display the wallet **address** (not the key) in a copy-friendly code block, with a clear label.
- **Always** include the block explorer link for the chain:
  - Base mainnet → `https://basescan.org/address/<ADDRESS>`
  - Ethereum mainnet → `https://etherscan.io/address/<ADDRESS>`
  - Arbitrum → `https://arbiscan.io/address/<ADDRESS>`
  - (extend as chains are added)
- **Always** include deposit instructions: small test amount first, verify via `get_balances` before sending more.
- **Always** remind the user the private key was shown in the raw tool response and is now encrypted on disk — tell them to back it up from that response before moving on.

### Template

```
Wallet created on Base mainnet.

Address:
0x...

Block explorer: https://basescan.org/address/0x...

Deposit a small test amount (1–5 USDC) first, then I'll verify with get_balances.

⚠️ Your private key appeared once in the raw tool response above. Back it up now (password manager, hardware wallet, paper). It is encrypted on disk and cannot be retrieved again via the API.
```

## Checking balances — output format

- Render non-zero balances only unless the user asks for full detail.
- Convert raw token amounts to human-readable units (USDC has 6 decimals, most ERC-20s have 18).
- Show the token symbol, not the contract address, when known. Contract address in parentheses for verification.

## Rationale

Workshop attendees have repeatedly confused prominent private-key code blocks with deposit addresses. The fix is presentational: address gets the spotlight, key stays unformatted in the raw response.
