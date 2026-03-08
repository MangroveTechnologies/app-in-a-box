# x402-app-template

## Start Here

```bash
# Local development
cp src/config/local-example-config.json src/config/local-config.json
docker compose up -d --build
curl http://localhost:8080/health

# Run tests
ENVIRONMENT=test pytest tests/ -v

# Run specific test markers
ENVIRONMENT=test pytest tests/ -m fast -v
ENVIRONMENT=test pytest tests/ -m integration -v
```

## What This Is

FastAPI + MCP service template for GCP Cloud Run. Dual protocol (REST + MCP on single port), three-tier access control, Terraform IaC, OIDC CI/CD.

## Architecture

Single FastAPI process serving:
- REST API at `/api/v1/*`
- MCP server at `/mcp` (Streamable HTTP via FastMCP)
- Health check at `/health`
- Auto-documentation at `/docs` (Swagger, for humans), `/openapi.json` (OpenAPI 3.0, for agents), `/api/v1/docs/tools` (MCP tool catalog, for agents)

### Three-Tier Access Model

| Tier | No credentials | API key | x402 payment |
|------|---------------|---------|-------------|
| Free | OK | OK | OK |
| Auth-gated | 401 | OK | 401 |
| x402-gated | 402 | OK (free) | OK (paid) |

API key holders bypass all payment requirements.

## Project Structure

```
src/
  app.py              -- FastAPI factory, MCP mount
  config.py           -- Config singleton
  health.py           -- Health check
  api/router.py       -- REST router
  api/routes/         -- Endpoint modules
  services/           -- Business logic
  mcp/server.py       -- FastMCP instance
  mcp/tools.py        -- MCP tool definitions
  shared/auth/        -- API key middleware
  shared/x402/        -- x402 payment middleware
  shared/db/          -- PostgreSQL utils
  config/             -- Per-env JSON configs
tests/                -- pytest tests
infra/terraform/      -- GCP infrastructure
```

## Configuration

- `ENVIRONMENT` env var selects config file (local/dev/test/prod)
- JSON files in `src/config/` with `secret:name:property` syntax for Secret Manager
- All required keys validated at startup (fails fast on missing keys)

## Key Conventions

- Routes go in `src/api/routes/`, services in `src/services/`
- MCP tools registered in `src/mcp/tools.py` via `register(server)` pattern
- Both REST and MCP call the same service layer (no duplication)
- Tests mirror source: `src/api/routes/items.py` -> `tests/test_items.py`
- Test config uses plain values (no Secret Manager in tests)
- `ENVIRONMENT=test` must be set before running pytest

## Adding Endpoints

### New REST route
1. Create `src/api/routes/your_route.py` with `APIRouter`
2. Create `src/services/your_service.py` with logic
3. Include router in `src/api/router.py`

### New MCP tool
1. Add tool function inside `register()` in `src/mcp/tools.py`
2. Add `register_tool(ToolEntry(...))` call for the discovery catalog
3. Call same service layer as REST

### Auto-documentation
- Pydantic response models and docstrings on routes are auto-included in OpenAPI spec and Swagger UI
- MCP tools must be registered in both the FastMCP server and the discovery catalog (`src/mcp/registry.py`)
- No manual doc build step -- everything is generated at runtime from code

### Access control
- Free: no decorator
- Auth: validate `X-API-Key` header via `validate_api_key()`
- x402: see `src/api/routes/easter_egg.py` for pattern

## Deployment

- **Local**: `docker compose up -d --build` (app + postgres + redis)
- **Cloud**: Terraform provisions Cloud Run, AR, Secret Manager, IAM
- **CI/CD**: Push to main triggers GitHub Actions (OIDC -> build -> push -> deploy)

## x402 Payment

- Chain: Base (EVM)
- Asset: USDC
- Facilitator: https://x402.org/facilitator
- Easter egg: $0.05 to `0xdAC6843ccA8B8c127d9d10EdB327fb0ddb2a5576`

---

## Project-Specific Rules

Add your project-specific conventions below this line.
