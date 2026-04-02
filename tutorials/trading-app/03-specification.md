# Chapter 3: Specification

## What Happens

The `/specification` skill generates API contracts, data models, and error handling from your requirements.

## Expected API Endpoints

Based on the trading app requirements:

### Free Tier
- `POST /api/v1/echo` — Connectivity test
- `GET /api/v1/docs/tools` — Tool discovery

### Auth-Gated
- `GET /api/v1/marketplace/listings` — List marketplace offerings
- `GET /api/v1/marketplace/listings/{id}` — Get listing details
- `GET /api/v1/dex/quote` — Get swap quote
- `GET /api/v1/wallet/balance/{address}` — Check wallet balance
- `GET /api/v1/wallet/history/{address}` — Transaction history

### x402-Gated (optional)
- `POST /api/x402/dex/swap` — Execute swap (costs per transaction)

## Expected Output

- `docs/specification.md` with full API contracts and data models
- Your approval before moving on

## Next

Proceed to [Chapter 4: Architecture](04-architecture.md)
