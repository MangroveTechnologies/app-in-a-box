<div align="center">
  <a href="https://github.com/MangroveTechnologies/x402-app-template">
    <img src="assets/logo.png" alt="Mangrove" width="120" height="112">
  </a>

  <h1>x402 App Template</h1>

  <p>
    <strong>Build APIs that get paid per-call.</strong><br>
    A service template using the <a href="https://www.x402.org/">x402 payment protocol</a> on Base.
  </p>

  <p>
    <a href="#-quick-start">Quick Start</a>
    &nbsp;&middot;&nbsp;
    <a href="#-try-the-x402-endpoint">Try x402</a>
    &nbsp;&middot;&nbsp;
    <a href="https://www.x402.org/">x402 Protocol</a>
    &nbsp;&middot;&nbsp;
    <a href="https://docs.cdp.coinbase.com/x402/welcome">Coinbase Docs</a>
  </p>

  <p>
    <img src="https://img.shields.io/badge/python-3.11+-blue?logo=python&logoColor=white" alt="Python">
    <img src="https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white" alt="FastAPI">
    <img src="https://img.shields.io/badge/x402-USDC_on_Base-0052FF?logo=coinbase&logoColor=white" alt="x402">
    <img src="https://img.shields.io/badge/MCP-Streamable_HTTP-purple" alt="MCP">
    <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
  </p>
</div>

---

## What is this?

When an agent calls your API, instead of checking a subscription or API key, the server can respond with **HTTP 402 Payment Required** -- here's what it costs, here's how to pay. The agent's wallet signs the payment, retries the request, and gets the response. No subscriptions. No billing dashboard. Just HTTP and USDC.

This template gives you a working service with that flow built in, plus everything you need to build your own x402-enabled API:

- :moneybag: **x402 payments** -- Working endpoint that accepts USDC on Base via the [Coinbase facilitator](https://docs.cdp.coinbase.com/x402/welcome)
- :key: **API key auth** -- Subscribers bypass payments entirely
- :unlock: **Free endpoints** -- Health, echo, docs -- always open
- :robot: **Dual protocol** -- REST (`/api/v1/*`) and MCP (`/mcp`) on one port
- :book: **Auto-docs** -- Swagger UI, OpenAPI 3.0, and MCP tool catalog generated from code
- :cloud: **Deploy-ready** -- Dockerfile, Terraform (GCP Cloud Run), GitHub Actions CI/CD
- :elephant: **Optional database** -- PostgreSQL + Redis available via Docker profiles when you need them

<details>
<summary>:clipboard: Table of Contents</summary>

- [Quick Start](#rocket-quick-start)
- [Try the x402 Endpoint](#moneybag-try-the-x402-endpoint)
- [Three-Tier Access Model](#closed_lock_with_key-three-tier-access-model)
- [Discovery & Documentation](#book-discovery--documentation)
- [x402 Configuration](#gear-x402-configuration)
- [Architecture](#building_construction-architecture)
- [Adding Your Own Endpoints](#heavy_plus_sign-adding-your-own-endpoints)
- [Full Stack Mode](#elephant-full-stack-mode)
- [Deploy to GCP](#cloud-deploy-to-gcp)
- [Configuration Reference](#pencil-configuration-reference)
- [Project Structure](#open_file_folder-project-structure)
- [Built With](#hammer_and_wrench-built-with)
- [License](#page_facing_up-license)

</details>

---

## :rocket: Quick Start

All you need is [Docker](https://docs.docker.com/get-docker/). No GCP account, no database, no blockchain wallet.

**1. Clone the repo**

```bash
git clone https://github.com/MangroveTechnologies/x402-app-template.git
cd x402-app-template
```

**2. Create your local config**

```bash
cp src/config/local-example-config.json src/config/local-config.json
```

This creates your local config file, which is gitignored. The default config uses the **Base Sepolia testnet** -- no real money, safe to experiment with.

**3. Start the service**

```bash
docker compose up -d --build
```

**4. Verify it's running**

```bash
curl http://localhost:8080/health
```

You should see `{"status": "healthy", ...}`. That's it -- you're running.

---

## :moneybag: Try the x402 Endpoint

The template includes a live x402-gated endpoint at `/api/x402/easter-egg`. When called without credentials, it responds with HTTP 402 and the payment details a client needs to complete the transaction.

### Testnet (default)

The quick start config uses Base Sepolia testnet. No real money involved.

**Hit the endpoint with no credentials:**

```bash
curl -s -D - http://localhost:8080/api/x402/easter-egg
```

You'll see an `HTTP 402` response with a `payment-required` header containing a base64-encoded JSON payload. Decode it to see the payment details:

```bash
curl -s -D - http://localhost:8080/api/x402/easter-egg 2>/dev/null \
  | grep "payment-required:" | cut -d' ' -f2 \
  | python3 -c "import sys,base64,json; h=sys.stdin.read().strip(); print(json.dumps(json.loads(base64.b64decode(h+'='*(4-len(h)%4))),indent=2))"
```

The response includes the network, asset contract, amount, deposit address, and facilitator URL. This is everything an x402-enabled client needs to sign a payment and retry the request. The [Coinbase x402 SDK](https://github.com/coinbase/x402) handles this automatically.

**With an API key** (subscribers get free access):

```bash
curl -s http://localhost:8080/api/x402/easter-egg -H "X-API-Key: dev-key-1"
```

### Mainnet

Once you've verified the flow on testnet, switch to Base mainnet by updating `X402_FACILITATOR_URL` in your `local-config.json`:

```json
{
  "X402_FACILITATOR_URL": "https://api.cdp.coinbase.com/platform/v2/x402",
  "X402_NETWORK": "eip155:8453",
  "X402_USDC_CONTRACT": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
  "X402_CDP_API_KEY_ID": "your-cdp-key-id",
  "X402_CDP_API_KEY_SECRET": "your-cdp-key-secret"
}
```

Restart and hit the same endpoint:

```bash
docker compose restart app
curl -s http://localhost:8080/api/x402/easter-egg | python3 -m json.tool
```

Same endpoint, same 402 response -- but now the payment requirements point to Base mainnet and real USDC. CDP API keys are available from the [Coinbase Developer Platform](https://docs.cdp.coinbase.com/). See [docs/configuration.md](docs/configuration.md) for the full setup guide.

> :warning: **Always verify on testnet first.** The testnet facilitator uses test USDC on Base Sepolia -- no real funds at risk.

---

## :closed_lock_with_key: Three-Tier Access Model

Every endpoint falls into one of three tiers:

| Tier | No credentials | API key | x402 payment |
|:-----|:--------------|:--------|:-------------|
| :unlock: **Free** | :white_check_mark: | :white_check_mark: | :white_check_mark: |
| :key: **Auth-gated** | :x: 401 | :white_check_mark: | :x: 401 |
| :moneybag: **x402-gated** | :credit_card: 402 + payment details | :white_check_mark: Free | :white_check_mark: Paid |

**API key holders get everything for free.** Public agents pay per-call for x402 endpoints. Free endpoints are always open.

Try all three:

```bash
# :unlock: Free -- no credentials needed
curl http://localhost:8080/api/v1/echo?hello=world

# :key: Auth-gated -- 401 without key, 201 with key
curl -s http://localhost:8080/api/v1/items
curl -X POST http://localhost:8080/api/v1/items \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-key-1" \
  -d '{"name":"Widget"}'

# :moneybag: x402-gated -- 402 without credentials, 200 with key
curl -s http://localhost:8080/api/x402/easter-egg
curl -s http://localhost:8080/api/x402/easter-egg -H "X-API-Key: dev-key-1"
```

---

## :book: Discovery & Documentation

All discovery endpoints are free. No auth required.

### For Agents

| Endpoint | Format | What it tells you |
|:---------|:-------|:-----------------|
| `GET /openapi.json` | OpenAPI 3.0 | Every route, parameter, and response model |
| `GET /api/v1/docs/tools` | JSON | Every MCP tool with access tier, parameters, and pricing |

```bash
curl -s http://localhost:8080/api/v1/docs/tools | python3 -m json.tool
```

### For Humans

| Endpoint | What you get |
|:---------|:------------|
| `/docs` | :desktop_computer: Swagger UI -- interactive API explorer |
| `/redoc` | :page_facing_up: ReDoc -- clean reference docs |

Open [http://localhost:8080/docs](http://localhost:8080/docs) in your browser.

---

## :gear: x402 Configuration

All x402 settings live in your per-environment JSON config file (`src/config/local-config.json`):

| Key | What it does |
|:----|:------------|
| `X402_FACILITATOR_URL` | Payment facilitator endpoint |
| `X402_NETWORK` | Blockchain network (CAIP-2 format) |
| `X402_PAY_TO` | Deposit address for payments |
| `X402_USDC_CONTRACT` | USDC token contract address |
| `X402_EASTER_EGG_PRICE` | Price in base units (50000 = $0.05) |
| `X402_CDP_API_KEY_ID` | CDP API key (mainnet only) |
| `X402_CDP_API_KEY_SECRET` | CDP API secret (mainnet only) |

**Two facilitators are supported:**

| Facilitator | Networks | API key required | Cost |
|:------------|:---------|:-----------------|:-----|
| [x402.org](https://x402.org) | Base Sepolia (testnet) | No | Free |
| [CDP](https://docs.cdp.coinbase.com/x402/welcome) | Base, Solana, Polygon | Yes | 1,000 free tx/month |

Pre-built config files are provided for both:

| Config file | What it includes |
|:------------|:----------------|
| `local-example-config.json` | x402 on Base Sepolia (testnet) |
| `local-full-example-config.json` | Same + PostgreSQL + Redis |

To change a value, edit your `local-config.json` and restart the app.

---

## :building_construction: Architecture

```
FastAPI app (port 8080)
|
+-- /health                     :unlock: Free
+-- /docs                       :desktop_computer: Swagger UI (for humans)
+-- /openapi.json               :robot: OpenAPI 3.0 (for agents)
|
+-- /api/v1/                    Free + auth-gated
|   +-- /docs/tools             :robot: MCP tool catalog (for agents)
|   +-- /echo                   :unlock: Free -- request reflection
|   +-- /items/*                :key: Auth-gated -- CRUD demo
|
+-- /api/x402/                  Payment-gated
|   +-- /easter-egg             :moneybag: $0.05 USDC on Base
|
+-- /mcp                        :robot: MCP Streamable HTTP transport
    +-- echo                    :unlock: Free
    +-- items_*                 :key: Auth-gated
    +-- easter_egg              :moneybag: x402-gated
```

REST and MCP serve the same business logic on the same port. Agents choose their preferred protocol.

---

## :heavy_plus_sign: Adding Your Own Endpoints

### REST endpoint

1. Create `src/api/routes/your_route.py` with a FastAPI `APIRouter`
2. Create `src/services/your_service.py` with business logic
3. Include in `src/api/router.py`:
   ```python
   from src.api.routes.your_route import router as your_router
   api_router.include_router(your_router, tags=["your-tag"])
   ```

> :bulb: Pydantic response models and docstrings are automatically picked up by the OpenAPI spec and Swagger UI.

### MCP tool

Add a tool function in `src/mcp/tools.py` inside `register()`, plus a catalog entry:

```python
@server.tool()
async def your_tool(param: str) -> str:
    """Description for agents."""
    return json.dumps(your_service_function(param))

register_tool(ToolEntry(
    name="your_tool",
    description="Description for agents.",
    access="free",  # or "auth" or "x402"
    parameters=[ToolParam(name="param", type="string", required=True)],
))
```

### x402-gated endpoint

Add the route pattern to `x402_routes` in `src/app.py`. The official x402 SDK middleware handles the 402 response, payment verification, and on-chain settlement automatically.

---

## :elephant: Full Stack Mode

The default setup runs just the app -- no database, no cache. When you need PostgreSQL and Redis:

```bash
cp src/config/local-full-example-config.json src/config/local-config.json
docker compose --profile full up -d --build
```

The `full` profile starts PostgreSQL 16 and Redis 7 alongside the app.

---

## :cloud: Deploy to GCP

### Bootstrap

When you're ready to deploy, run the bootstrap script to replace placeholder values:

```bash
# For agents (non-interactive):
./init.sh --name my-service --gcp-project my-gcp-project --region us-central1

# For humans (interactive):
./init-interactive.sh
```

### Terraform

```bash
cd infra/terraform
terraform init -backend-config=backend-dev.hcl
terraform plan -var-file=environment-dev.tfvars
terraform apply -var-file=environment-dev.tfvars
```

See `infra/terraform/SETUP.md` for prerequisites.

### CI/CD

GitHub Actions workflow at `.github/workflows/deploy-cloudrun.yaml`. Manual trigger by default -- uncomment the push or PR triggers when ready.

Required GitHub secrets:
- `GCP_WORKLOAD_IDENTITY_PROVIDER`
- `GCP_SERVICE_ACCOUNT_EMAIL`

---

## :pencil: Configuration Reference

All config lives in per-environment JSON files at `src/config/`. Only two env vars: `ENVIRONMENT` (selects config file) and `GCP_PROJECT_ID` (for Secret Manager).

| File | Purpose |
|:-----|:--------|
| `local-example-config.json` | Testnet (Base Sepolia) |
| `local-full-example-config.json` | Testnet + PostgreSQL + Redis |
| `test-config.json` | pytest |
| `dev-config.json` | Development (Secret Manager refs) |
| `prod-config.json` | Production (Secret Manager refs) |

> :bulb: Copy an example to `local-config.json` to get started. This file is gitignored -- your secrets stay local.

**Key categories** in `configuration-keys.json`:

| Category | Behavior |
|:---------|:---------|
| `required` | Always validated at startup. App fails without them. |
| `full_app_keys` | Validated only if present in your config. Absent = app runs without those features. Present but empty = startup fails. |

Secret Manager syntax: `"secret:secret-name:property"`

See [docs/configuration.md](docs/configuration.md) for the full configuration guide, including GCP Secret Manager setup for production. AWS support is coming soon.

---

## :open_file_folder: Project Structure

```
src/
  app.py                    FastAPI app, x402 middleware, MCP mount
  config.py                 Config singleton (JSON + Secret Manager)
  health.py                 Health check
  api/
    router.py               REST router (/api/v1)
    routes/
      docs.py               MCP tool catalog
      echo.py               Free endpoint
      items.py              Auth-gated CRUD
      easter_egg.py         x402-gated endpoint
  services/
    items.py                Items business logic
    easter_egg.py           Easter egg message
  mcp/
    server.py               FastMCP server
    tools.py                MCP tool definitions
    registry.py             Tool discovery catalog
  shared/
    auth/middleware.py       API key validation
    x402/config.py          Payment config (reads from app_config)
    db/pool.py              PostgreSQL connection
    db/exceptions.py        DB error hierarchy
    gcp_secret_utils.py     Secret Manager client
  config/                   Per-env JSON config files
tests/                      30 tests
infra/terraform/            GCP Cloud Run IaC
.github/workflows/          CI/CD (manual trigger)
scripts/                    x402 payment test scripts
```

---

## :hammer_and_wrench: Built With

| Component | Technology |
|:----------|:-----------|
| Framework | [FastAPI](https://fastapi.tiangolo.com/) + [uvicorn](https://www.uvicorn.org/) |
| Agent protocol | [FastMCP](https://github.com/jlowin/fastmcp) (Streamable HTTP) |
| Payments | [x402 Python SDK](https://github.com/coinbase/x402) (Coinbase) |
| Database | PostgreSQL 16 (optional) |
| Cache | Redis 7 (optional) |
| IaC | [Terraform](https://www.terraform.io/) (GCP Cloud Run) |
| CI/CD | GitHub Actions (OIDC workload identity) |

---

## :page_facing_up: License

Distributed under the MIT License.

---

<div align="center">

**[x402 Protocol](https://www.x402.org/)** · **[Coinbase x402 SDK](https://github.com/coinbase/x402)** · **[Coinbase Developer Platform](https://docs.cdp.coinbase.com/x402/welcome)** · **[MangroveTechnologies](https://github.com/MangroveTechnologies)**

</div>
