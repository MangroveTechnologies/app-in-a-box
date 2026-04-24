# Chapter 4: Architecture

## What Happens

The `/architecture` skill designs the system and generates mermaid diagrams.

## Expected Diagrams

1. **System architecture** — Trading app ↔ Mangrove API, with internal layers
2. **Data flow** — Request → auth → service → Mangrove API → response
3. **Sequence diagram** — DEX swap flow showing multi-step interaction
4. **Component diagram** — Internal server structure
5. **Folder hierarchy** — Complete file tree

## Module Decisions

For the trading app, expect:
- **Keep:** PostgreSQL (transaction history), MCP tools, API key auth, Docker, CI/CD
- **Remove:** Redis (not needed for this app), x402 payments (optional, depends on your choice)

## Expected Output

- `docs/architecture.md` with all diagrams and module decisions
- Your approval before moving on

## Next

Proceed to [Chapter 5: Implementation Plan](05-implementation.md)
