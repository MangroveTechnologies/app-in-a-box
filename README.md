# x402-app-template

FastAPI + MCP service template for GCP Cloud Run. Dual protocol (REST + MCP), three-tier access control (free, auth-gated, x402-gated), auto-documentation, Terraform IaC, OIDC CI/CD.

Designed for agents first, humans second.

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

```bash
cp src/config/local-example-config.json src/config/local-config.json
docker compose up -d --build
```

### 3. Verify

```bash
# Health check (free)
curl http://localhost:8080/health

# Echo (free)
curl -X POST http://localhost:8080/api/v1/echo -H "Content-Type: application/json" -d '{"hello":"world"}'

# Create item (auth-gated -- requires API key)
curl -X POST http://localhost:8080/api/v1/items \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-key-1" \
  -d '{"name":"Widget","description":"A widget"}'

# Easter egg (x402-gated -- returns 402 payment requirements)
curl http://localhost:8080/api/v1/easter-egg

# Easter egg (free with API key)
curl http://localhost:8080/api/v1/easter-egg -H "X-API-Key: dev-key-1"
```

## Discovery and Documentation

Both agents and humans can discover the full API programmatically. All discovery endpoints are free, no auth required.

### For Agents

| Endpoint | Format | What it provides |
|----------|--------|-----------------|
| `GET /openapi.json` | OpenAPI 3.0 JSON | Full REST API spec -- every route, parameter, response model |
| `GET /api/v1/docs/tools` | JSON | MCP tool catalog -- names, parameters, access tiers, pricing |

An agent should call these two endpoints to fully understand the service before making any other requests or connecting via MCP.

**Example: discover MCP tools**
```bash
curl http://localhost:8080/api/v1/docs/tools | python3 -m json.tool
```

Returns:
```json
{
  "tools": [
    {
      "name": "echo",
      "description": "Echo a message back. Free, no auth required.",
      "access": "free",
      "parameters": [{"name": "message", "type": "string", "required": false}]
    },
    {
      "name": "easter_egg",
      "description": "Get the easter egg message. Costs $0.05 USDC on Base, or free with API key.",
      "access": "x402",
      "price": "$0.05 USDC",
      "network": "base",
      "parameters": []
    }
  ],
  "total": 5,
  "access_tiers": {
    "free": "No credentials required",
    "auth": "Requires X-API-Key header",
    "x402": "Requires x402 payment (or API key for free access)"
  }
}
```

### For Humans

| Endpoint | What it provides |
|----------|-----------------|
| `/docs` | Swagger UI -- interactive API explorer with try-it-out |
| `/redoc` | ReDoc -- clean API reference documentation |

Open `http://localhost:8080/docs` in a browser to explore the API interactively.

## What You Get

### Architecture

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

### Three-Tier Access Model

| Tier | No credentials | API key | x402 payment |
|------|---------------|---------|-------------|
| Free | OK | OK | OK |
| Auth-gated | 401 | OK | 401 |
| x402-gated | 402 + payment requirements | OK (free) | OK (paid) |

API key holders get full access to everything. Public agents pay per-call via x402 for gated endpoints.

### Infrastructure

| Component | Technology |
|-----------|-----------|
| Framework | FastAPI + uvicorn |
| MCP | FastMCP (Streamable HTTP at /mcp) |
| Documentation | OpenAPI 3.0 (auto-generated from code) |
| Database | PostgreSQL 16 (Cloud SQL in prod) |
| Cache | Redis 7 |
| Auth | API key (X-API-Key header) |
| Payments | x402 protocol (Base/USDC) |
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

Pydantic response models and docstrings on your route functions are automatically picked up by the OpenAPI spec and Swagger UI. No extra documentation step needed.

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
- **x402-gated**: Use the easter_egg endpoint as a reference pattern

## Deploy

### Terraform (first time)

```bash
cd infra/terraform
terraform init -backend-config=backend-dev.hcl
terraform plan -var-file=environment-dev.tfvars
terraform apply -var-file=environment-dev.tfvars
```

See `infra/terraform/SETUP.md` for prerequisites (GCP project, state bucket, OIDC setup).

### CI/CD (ongoing)

Push to `main` triggers GitHub Actions:
1. Docker build (linux/amd64)
2. Push to Artifact Registry
3. Deploy to Cloud Run

Requires GitHub secrets:
- `GCP_WORKLOAD_IDENTITY_PROVIDER`
- `GCP_SERVICE_ACCOUNT_EMAIL`

## Configuration

Per-environment JSON files in `src/config/`:

| File | Environment | Secrets |
|------|------------|---------|
| `local-example-config.json` | Local dev template | Plain values |
| `test-config.json` | pytest | Plain values |
| `dev-config.json` | Development | Secret Manager refs |
| `prod-config.json` | Production | Secret Manager refs |

Secret Manager reference syntax: `"secret:secret-name:property"`

Required config keys: `DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_PORT`, `DB_SSLMODE`, `CLOUD_SQL_CONNECTION_NAME`, `AUTH_ENABLED`, `API_KEYS`, `REDIS_URL`

## Project Structure

```
src/
  app.py                    -- FastAPI app, MCP mount, health check
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
      middleware.py          -- x402 payment decorator
      config.py             -- Payment config (chain, address, price)
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
tests/
  conftest.py               -- Fixtures
  test_*.py                 -- Test files (30 tests)
infra/terraform/            -- Terraform IaC
.github/workflows/          -- CI/CD
init.sh                     -- Bootstrap (for agents)
init-interactive.sh         -- Bootstrap (for humans)
```

## License

MIT
