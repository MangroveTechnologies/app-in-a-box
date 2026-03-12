# x402-app-template

## Start Here

```bash
# Local development
cp src/config/local-example-config.json src/config/local-config.json
docker compose up -d --build
curl http://localhost:8080/health

# Run tests
ENVIRONMENT=test pytest tests/ -v
```

## What This Is

FastAPI + MCP service template with x402 payments on Base. Dual protocol (REST + MCP on single port), three-tier access control, Terraform IaC, OIDC CI/CD.

## Architecture

Single FastAPI process serving:
- REST API at `/api/v1/*` (free + auth-gated)
- x402 API at `/api/x402/*` (payment-gated)
- MCP server at `/mcp` (Streamable HTTP via FastMCP)
- Health check at `/health`
- Auto-docs at `/docs`, `/openapi.json`, `/api/v1/docs/tools`

### Three-Tier Access Model

| Tier | No credentials | API key | x402 payment |
|------|---------------|---------|-------------|
| Free | OK | OK | OK |
| Auth-gated | 401 | OK | 401 |
| x402-gated | 402 | OK (free) | OK (paid) |

## Routing Convention

- `/api/v1/*` -- Free and auth-gated endpoints
- `/api/x402/*` -- x402 payment-gated endpoints
- `/mcp` -- MCP tools (all tiers)

## Configuration

- `ENVIRONMENT` env var selects config file (local/dev/test/prod)
- JSON files in `src/config/` with `secret:name:property` syntax for GCP Secret Manager
- Config file is the single source of truth -- edit and restart to change values
- Required keys validated at startup (fails fast on missing keys)
- Full_app_keys (DB, Redis) validated only if present in config file

### Secrets

- **Local/test**: Plain values in JSON config files
- **Dev/prod**: Use `secret:name:property` syntax to resolve from GCP Secret Manager
- **AWS**: Coming soon

## Key Conventions

- Free/auth routes in `src/api/routes/`, x402 routes also in `src/api/routes/`
- Services in `src/services/`
- MCP tools in `src/mcp/tools.py` via `register(server)` pattern
- Both REST and MCP call the same service layer (no duplication)
- Tests mirror source: `src/api/routes/items.py` -> `tests/test_items.py`
- `ENVIRONMENT=test` must be set before running pytest

## Adding Endpoints

### New free/auth route
1. Create `src/api/routes/your_route.py` with `APIRouter`
2. Create `src/services/your_service.py` with logic
3. Include in `api_router` in `src/api/router.py`

### New x402-gated route
1. Create route in `src/api/routes/`
2. Include in `x402_router` in `src/api/router.py`
3. Add route pattern to `x402_routes` in `src/app.py`

### New MCP tool
1. Add tool function inside `register()` in `src/mcp/tools.py`
2. Add `register_tool(ToolEntry(...))` for the discovery catalog
3. Call same service layer as REST
4. **Auth-gated tools**: Accept `api_key` parameter, validate with `has_valid_api_key()`
5. **x402-gated tools**: Accept `api_key` and `payment` parameters, verify payment via `src/shared/x402/server.py`

## x402 Payment

All x402 config in per-environment JSON files:
- `X402_FACILITATOR_URL` -- CDP production or x402.org testnet
- `X402_NETWORK` -- `eip155:8453` (Base mainnet) or `eip155:84532` (Sepolia)
- `X402_PAY_TO` -- address that receives payments
- `X402_USDC_CONTRACT` -- USDC token contract
- `X402_EASTER_EGG_PRICE` -- price in base units (50000 = $0.05)
- `X402_CDP_API_KEY_ID` / `X402_CDP_API_KEY_SECRET` -- for CDP facilitator

Switch to mainnet: update `X402_FACILITATOR_URL` and related values in `local-config.json`, then `docker compose restart app`

## Deployment

- **Local**: `docker compose up -d --build` (app only, or `--profile full` for DB + Redis)
- **Cloud**: Terraform provisions Cloud Run, AR, Secret Manager, IAM
- **CI**: `ci.yml` runs pytest + ruff on push/PR to main
- **Deploy**: Manual trigger via `deploy-cloudrun.yaml`

---

## Project-Specific Rules

Add your project-specific conventions below this line.
