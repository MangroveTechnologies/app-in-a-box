# x402-app-template

FastAPI + MCP service template with built-in x402 payments on Base. Three-tier access control (free, auth-gated, x402-gated), dual protocol (REST + MCP), auto-documentation, Terraform IaC, GCP Cloud Run.

Designed for agents first, humans second.

## Try the x402 Payment Flow

The template ships with a working x402-gated endpoint. Hit it and see what happens:

```bash
# No credentials -- server returns 402 with payment requirements
curl -s http://localhost:8080/api/v1/easter-egg | python3 -m json.tool
```

The 402 response tells the agent exactly how to pay: network, asset, amount, and facilitator URL. An x402-enabled client (like the Coinbase x402 SDK) handles payment automatically -- sign, retry, done.

With an API key, the same endpoint is free:

```bash
curl -s http://localhost:8080/api/v1/easter-egg -H "X-API-Key: dev-key-1"
```

Returns: `"Thank you for supporting the project and strengthening the ecosystem"`

This is the three-tier access model in action:

| Tier | No credentials | API key | x402 payment |
|------|---------------|---------|-------------|
| **Free** | OK | OK | OK |
| **Auth-gated** | 401 | OK | 401 |
| **x402-gated** | 402 + payment requirements | OK (free) | OK (paid) |

## Quick Start

### 1. Clone and bootstrap

```bash
git clone https://github.com/MangroveTechnologies/x402-app-template.git my-service
cd my-service

# For agents (non-interactive):
./init.sh --name my-service --gcp-project my-gcp-project --region us-central1

# For humans (interactive):
./init-interactive.sh
```

### 2. Configure and run

Two modes:

**Minimal** -- Just the app, no PostgreSQL or Redis. Try x402 immediately:
```bash
cp src/config/local-minimal-config.json src/config/local-config.json
docker compose up -d --build
```

**Full stack** -- App + PostgreSQL + Redis (for DB-backed features):
```bash
cp src/config/local-example-config.json src/config/local-config.json
# Edit src/config/local-config.json -- set X402_PAY_TO to your deposit address
docker compose --profile full up -d --build
```

### 3. Verify all three tiers

```bash
# Free tier -- no credentials needed
curl http://localhost:8080/health
curl http://localhost:8080/api/v1/echo?hello=world

# Auth tier -- requires API key
curl -X POST http://localhost:8080/api/v1/items \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-key-1" \
  -d '{"name":"Widget","description":"A widget"}'

# x402 tier -- returns 402 with payment requirements (or free with API key)
curl http://localhost:8080/api/v1/easter-egg
curl http://localhost:8080/api/v1/easter-egg -H "X-API-Key: dev-key-1"
```

## x402 Payment Configuration

All x402 settings live in the per-environment JSON config files (`src/config/*.json`):

| Key | Description | Example (testnet) | Example (mainnet) |
|-----|-------------|-------------------|-------------------|
| `X402_FACILITATOR_URL` | Coinbase facilitator endpoint | `https://x402.org/facilitator` | `https://api.cdp.coinbase.com/platform/v2/x402` |
| `X402_NETWORK` | CAIP-2 chain identifier | `eip155:84532` (Sepolia) | `eip155:8453` (Base) |
| `X402_PAY_TO` | Your deposit address | `0xdAC6...` | `0xdAC6...` |
| `X402_USDC_CONTRACT` | USDC token contract | `0x036CbD...` (test) | `0x833589...` (mainnet) |
| `X402_EASTER_EGG_PRICE` | Price in base units (6 decimals) | `50000` ($0.05) | `50000` ($0.05) |
| `X402_CDP_API_KEY_ID` | CDP API key (mainnet only) | empty | `secret:...:cdp_api_key_id` |
| `X402_CDP_API_KEY_SECRET` | CDP API secret (mainnet only) | empty | `secret:...:cdp_api_key_secret` |

**Two facilitators supported:**
- **x402.org** (testnet) -- No API key needed. Base Sepolia only. Free.
- **CDP** (production) -- Requires CDP API keys. Base mainnet, Solana, Polygon. 1,000 free tx/month.

## Discovery and Documentation

Both agents and humans can discover the full API programmatically. All discovery endpoints are free.

### For Agents

| Endpoint | Format | What it provides |
|----------|--------|-----------------|
| `GET /openapi.json` | OpenAPI 3.0 JSON | Full REST API spec -- every route, parameter, response model |
| `GET /api/v1/docs/tools` | JSON | MCP tool catalog -- names, parameters, access tiers, pricing |

An agent should call these two endpoints to understand the service before making requests or connecting via MCP.

```bash
curl http://localhost:8080/api/v1/docs/tools | python3 -m json.tool
```

### For Humans

| Endpoint | What it provides |
|----------|-----------------|
| `/docs` | Swagger UI -- interactive API explorer |
| `/redoc` | ReDoc -- clean API reference |

## Architecture

```
FastAPI app (port 8080)
  |
  +-- /health                  (free)
  +-- /docs                    (Swagger UI -- for humans)
  +-- /openapi.json            (OpenAPI 3.0 spec -- for agents)
  +-- /api/v1/*                (REST endpoints)
  |     +-- /docs/tools        (MCP tool catalog -- for agents)
  |     +-- /echo              (free -- request reflection)
  |     +-- /items/*           (auth-gated -- CRUD demo)
  |     +-- /easter-egg        (x402-gated -- $0.05 USDC on Base)
  |
  +-- /mcp                     (MCP Streamable HTTP transport)
        +-- echo               (free)
        +-- items_*            (auth-gated)
        +-- easter_egg         (x402-gated)
```

### Infrastructure

| Component | Technology |
|-----------|-----------|
| Framework | FastAPI + uvicorn |
| MCP | FastMCP (Streamable HTTP at /mcp) |
| Payments | x402 protocol (Base/USDC, Coinbase facilitator) |
| Documentation | OpenAPI 3.0 (auto-generated from code) |
| Database | PostgreSQL 16 (Cloud SQL in prod) |
| Cache | Redis 7 |
| Auth | API key (X-API-Key header) |
| Config | Per-env JSON + GCP Secret Manager |
| IaC | Terraform (Cloud Run, AR, SM, IAM) |
| CI/CD | GitHub Actions (OIDC workload identity) |
| Container | Python 3.11-slim, uvicorn |

## Adding Your Own Routes

### REST endpoint

1. Create `src/api/routes/your_route.py` with a FastAPI `APIRouter`
2. Create `src/services/your_service.py` with business logic
3. Add to `src/api/router.py`:
   ```python
   from src.api.routes.your_route import router as your_router
   api_router.include_router(your_router, tags=["your-tag"])
   ```

Pydantic response models and docstrings are automatically picked up by the OpenAPI spec and Swagger UI.

### MCP tool

1. Add tool function in `src/mcp/tools.py` inside `register()`:
   ```python
   @server.tool()
   async def your_tool(param: str) -> str:
       """Description for agents."""
       result = your_service_function(param)
       return json.dumps(result)
   ```

2. Add catalog entry for agent discovery:
   ```python
   register_tool(ToolEntry(
       name="your_tool",
       description="Description for agents.",
       access="free",  # or "auth" or "x402"
       parameters=[ToolParam(name="param", type="string", required=True)],
   ))
   ```

### Access control

- **Free**: No decorator needed
- **Auth-gated**: Add `x_api_key: str = Header(None, alias="X-API-Key")` parameter and call `_require_auth(x_api_key)`
- **x402-gated**: Add route to `x402_routes` dict in `src/app.py` -- the middleware handles 402/verify/settle

## Configuration

All config lives in per-environment JSON files at `src/config/`. No env vars for app config (only `ENVIRONMENT` and `GCP_PROJECT_ID` are env vars).

| File | Environment | Mode |
|------|------------|------|
| `local-minimal-config.json` | Local dev (x402 only) | Minimal -- no DB keys |
| `local-example-config.json` | Local dev (full stack) | Full -- includes DB + Redis keys |
| `test-config.json` | pytest | Minimal |
| `dev-config.json` | Development | Full (Secret Manager refs) |
| `prod-config.json` | Production | Full (Secret Manager refs) |

**Key categories** (`src/config/configuration-keys.json`):
- `required` -- Always validated. App fails without them (auth, x402 settings).
- `full_app_keys` -- Validated only if present in your config file. If a full_app_key is present but empty, startup fails (catches misconfiguration). If absent, the app starts without those features.

Secret Manager syntax: `"secret:secret-name:property"`

## Deploy

### Terraform (first time)

```bash
cd infra/terraform
terraform init -backend-config=backend-dev.hcl
terraform plan -var-file=environment-dev.tfvars
terraform apply -var-file=environment-dev.tfvars
```

See `infra/terraform/SETUP.md` for prerequisites (GCP project, state bucket, OIDC setup).

### CI/CD

Manually trigger via GitHub Actions (workflow_dispatch). Uncomment push/PR triggers in `.github/workflows/deploy-cloudrun.yaml` when ready.

Requires GitHub secrets:
- `GCP_WORKLOAD_IDENTITY_PROVIDER`
- `GCP_SERVICE_ACCOUNT_EMAIL`

## Project Structure

```
src/
  app.py                    -- FastAPI app, x402 middleware, MCP mount
  config.py                 -- Config singleton (JSON + Secret Manager)
  health.py                 -- Health check payload
  api/
    router.py               -- REST router (/api/v1)
    routes/
      docs.py               -- MCP tool catalog endpoint
      echo.py               -- Free echo endpoint
      items.py              -- Auth-gated CRUD
      easter_egg.py         -- x402-gated endpoint
  services/
    items.py                -- Items business logic
    easter_egg.py           -- Easter egg response
  mcp/
    server.py               -- FastMCP server
    tools.py                -- MCP tool definitions
    registry.py             -- Tool discovery catalog
  shared/
    types.py                -- Pydantic base model
    auth/
      middleware.py          -- API key validation
    x402/
      config.py             -- Payment config (reads from app_config)
      middleware.py          -- x402 payment decorator
      models.py             -- Payment data models
      facilitator.py        -- Facilitator HTTP client
      errors.py             -- x402 error hierarchy
    db/
      pool.py               -- PostgreSQL connection
      exceptions.py         -- DB error hierarchy
    gcp_secret_utils.py     -- Secret Manager client
  config/
    configuration-keys.json -- Required config keys
    *.json                  -- Per-env config files
tests/                      -- 30 tests
infra/terraform/            -- Terraform IaC
.github/workflows/          -- CI/CD (manual trigger)
init.sh                     -- Bootstrap (for agents)
init-interactive.sh         -- Bootstrap (for humans)
```

## License

MIT
