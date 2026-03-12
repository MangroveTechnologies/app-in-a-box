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

- 💰 **x402 payments** -- Working endpoint that charges $0.05 USDC on Base via the [Coinbase facilitator](https://docs.cdp.coinbase.com/x402/welcome)
- 🔑 **API key auth** -- Subscribers bypass payments entirely
- 🔓 **Free endpoints** -- Health, echo, docs -- always open
- 🤖 **Dual protocol** -- REST (`/api/v1/*`) and MCP (`/mcp`) on one port
- 📖 **Auto-docs** -- Swagger UI, OpenAPI 3.0, and MCP tool catalog generated from code
- ☁️ **Deploy-ready** -- Dockerfile, Terraform (GCP Cloud Run), GitHub Actions CI/CD
- 🐘 **Optional database** -- PostgreSQL + Redis available via Docker profiles when you need them

<details>
<summary>📋 Table of Contents</summary>

- [Quick Start](#-quick-start)
- [Try the x402 Endpoint](#-try-the-x402-endpoint)
- [Three-Tier Access Model](#-three-tier-access-model)
- [Discovery & Documentation](#-discovery--documentation)
- [x402 Payment Configuration](#-x402-payment-configuration)
- [Architecture](#-architecture)
- [Adding Your Own Endpoints](#-adding-your-own-endpoints)
- [Full Stack Mode](#-full-stack-mode)
- [Deploy to GCP](#-deploy-to-gcp)
- [Configuration Reference](#-configuration-reference)
- [Project Structure](#-project-structure)
- [Built With](#-built-with)
- [License](#-license)

</details>

---

## 🚀 Quick Start

All you need is [Docker](https://docs.docker.com/get-docker/). No GCP account, no database, no blockchain wallet.

**1. Clone the repo**

```bash
git clone https://github.com/MangroveTechnologies/x402-app-template.git
cd x402-app-template
```

**2. Create your local config**

The template ships with an example config that's ready to run on the x402.org testnet facilitator. Copy it to create your local config file (which is gitignored -- your secrets and project-specific settings go here):

```bash
cp src/config/local-example-config.json src/config/local-config.json
```

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

## 💰 Try the x402 Endpoint

The template includes a live x402-gated endpoint at `/api/v1/easter-egg`. This is a real payment endpoint -- when called without credentials, it responds with HTTP 402 and tells the caller exactly how to pay $0.05 USDC on Base.

**Hit the endpoint with no credentials:**

```bash
curl -s http://localhost:8080/api/v1/easter-egg | python3 -m json.tool
```

You'll get back a `402 Payment Required` response containing:
- The **network** to pay on (`eip155:84532` for Base Sepolia testnet)
- The **USDC contract** address
- The **deposit address** where payment goes
- The **amount** in base units (50000 = $0.05)
- The **facilitator URL** that verifies and settles the payment

This is everything an x402-enabled client needs. The [Coinbase x402 SDK](https://github.com/coinbase/x402) handles the rest automatically -- sign the payment, retry the request, receive the content.

**Now try with an API key** (subscribers get free access):

```bash
curl -s http://localhost:8080/api/v1/easter-egg -H "X-API-Key: dev-key-1"
```

> 💡 **Want to make a real payment?** See `scripts/test_x402_mainnet.py` for a working end-to-end example using the Coinbase x402 SDK with a funded wallet.

---

## 🔐 Three-Tier Access Model

Every endpoint in the template falls into one of three tiers:

| Tier | No credentials | API key | x402 payment |
|:-----|:--------------|:--------|:-------------|
| 🔓 **Free** | ✅ | ✅ | ✅ |
| 🔑 **Auth-gated** | ❌ 401 | ✅ | ❌ 401 |
| 💰 **x402-gated** | 💳 402 + payment details | ✅ Free | ✅ Paid |

**API key holders get everything for free.** Public agents pay per-call for x402 endpoints. Free endpoints are always open.

Try all three:

```bash
# 🔓 Free -- no credentials needed
curl http://localhost:8080/api/v1/echo?hello=world

# 🔑 Auth-gated -- 401 without key, 201 with key
curl -s http://localhost:8080/api/v1/items
curl -X POST http://localhost:8080/api/v1/items \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-key-1" \
  -d '{"name":"Widget"}'

# 💰 x402-gated -- 402 without credentials, 200 with key
curl -s http://localhost:8080/api/v1/easter-egg
curl -s http://localhost:8080/api/v1/easter-egg -H "X-API-Key: dev-key-1"
```

---

## 📖 Discovery & Documentation

All discovery endpoints are free. No auth required.

### For Agents

| Endpoint | Format | What it tells you |
|:---------|:-------|:-----------------|
| `GET /openapi.json` | OpenAPI 3.0 | Every route, parameter, and response model |
| `GET /api/v1/docs/tools` | JSON | Every MCP tool with access tier, parameters, and pricing |

```bash
# See all available MCP tools, what they cost, and how to call them
curl -s http://localhost:8080/api/v1/docs/tools | python3 -m json.tool
```

### For Humans

| Endpoint | What you get |
|:---------|:------------|
| `/docs` | 🖥️ Swagger UI -- interactive API explorer |
| `/redoc` | 📄 ReDoc -- clean reference docs |

Open [http://localhost:8080/docs](http://localhost:8080/docs) in your browser.

---

## ⚙️ x402 Payment Configuration

All x402 settings live in your per-environment JSON config file:

| Key | What it does | Testnet default | Mainnet example |
|:----|:------------|:----------------|:----------------|
| `X402_FACILITATOR_URL` | Payment facilitator | `https://x402.org/facilitator` | `https://api.cdp.coinbase.com/platform/v2/x402` |
| `X402_NETWORK` | Blockchain network | `eip155:84532` (Sepolia) | `eip155:8453` (Base) |
| `X402_PAY_TO` | Your deposit address | `0xdAC6...` | Your address |
| `X402_USDC_CONTRACT` | USDC token contract | `0x036CbD...` (test) | `0x833589...` (mainnet) |
| `X402_EASTER_EGG_PRICE` | Price in base units | `50000` ($0.05) | `50000` ($0.05) |
| `X402_CDP_API_KEY_ID` | CDP API key | (empty) | From [CDP portal](https://docs.cdp.coinbase.com/) |
| `X402_CDP_API_KEY_SECRET` | CDP API secret | (empty) | From CDP portal |

**Two facilitators are supported:**

| Facilitator | Networks | API key | Cost |
|:------------|:---------|:--------|:-----|
| [x402.org](https://x402.org) | Base Sepolia (testnet) | Not needed | Free |
| [CDP](https://docs.cdp.coinbase.com/x402/welcome) | Base, Solana, Polygon (mainnet) | Required | 1,000 free tx/month |

The default config uses x402.org (testnet). Switch to CDP for mainnet by updating the config values and adding your CDP API keys.

---

## 🏗️ Architecture

```
FastAPI app (port 8080)
│
├── /health                     🔓 Free
├── /docs                       🖥️ Swagger UI (for humans)
├── /openapi.json               🤖 OpenAPI 3.0 (for agents)
│
├── /api/v1/
│   ├── /docs/tools             🤖 MCP tool catalog (for agents)
│   ├── /echo                   🔓 Free -- request reflection
│   ├── /items/*                🔑 Auth-gated -- CRUD demo
│   └── /easter-egg             💰 x402-gated -- $0.05 USDC on Base
│
└── /mcp                        🤖 MCP Streamable HTTP transport
    ├── echo                    🔓 Free
    ├── items_*                 🔑 Auth-gated
    └── easter_egg              💰 x402-gated
```

REST and MCP serve the same business logic on the same port. Agents choose their preferred protocol.

---

## ➕ Adding Your Own Endpoints

### REST endpoint

1. Create `src/api/routes/your_route.py` with a FastAPI `APIRouter`
2. Create `src/services/your_service.py` with business logic
3. Include in `src/api/router.py`:
   ```python
   from src.api.routes.your_route import router as your_router
   api_router.include_router(your_router, tags=["your-tag"])
   ```

> 💡 Pydantic response models and docstrings are automatically picked up by the OpenAPI spec and Swagger UI. No manual documentation step.

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

## 🐘 Full Stack Mode

The default setup runs just the app -- no database, no cache. When you need PostgreSQL and Redis:

```bash
cp src/config/local-full-example-config.json src/config/local-config.json
docker compose --profile full up -d --build
```

The `full` profile starts PostgreSQL 16 and Redis 7 alongside the app. The config loader validates that DB and Redis keys are properly set when they're present in your config file.

---

## ☁️ Deploy to GCP

### Bootstrap

When you're ready to deploy, run the bootstrap script to replace placeholder values across Terraform, CI/CD, and config files:

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

See `infra/terraform/SETUP.md` for prerequisites (GCP project, state bucket, OIDC workload identity).

### CI/CD

GitHub Actions workflow at `.github/workflows/deploy-cloudrun.yaml`. Manual trigger by default -- uncomment the push or PR triggers in the YAML when ready.

Required GitHub secrets:
- `GCP_WORKLOAD_IDENTITY_PROVIDER`
- `GCP_SERVICE_ACCOUNT_EMAIL`

---

## 📝 Configuration Reference

All config lives in per-environment JSON files at `src/config/`. Only two env vars: `ENVIRONMENT` (selects config file) and `GCP_PROJECT_ID` (for Secret Manager).

| File | Purpose |
|:-----|:--------|
| `local-example-config.json` | Local dev (minimal, x402 only) |
| `local-full-example-config.json` | Local dev (full stack with DB + Redis) |
| `test-config.json` | pytest |
| `dev-config.json` | Development (Secret Manager refs) |
| `prod-config.json` | Production (Secret Manager refs) |

> 💡 Copy an example to `local-config.json` to get started. This file is gitignored -- your secrets stay local.

**Key categories** in `configuration-keys.json`:

| Category | Behavior |
|:---------|:---------|
| `required` | Always validated at startup. App fails without them. |
| `full_app_keys` | Validated only if present in your config. Absent = app runs without those features. Present but empty = startup fails (catches misconfiguration). |

Secret Manager syntax: `"secret:secret-name:property"`

---

## 📁 Project Structure

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
    x402/config.py          Payment config (from app_config)
    x402/models.py          Payment data models
    x402/middleware.py       x402 payment decorator
    x402/facilitator.py     Facilitator HTTP client
    x402/errors.py          Error hierarchy
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

## 🛠️ Built With

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

## 📄 License

Distributed under the MIT License.

---

<div align="center">

**[x402 Protocol](https://www.x402.org/)** · **[Coinbase x402 SDK](https://github.com/coinbase/x402)** · **[Coinbase Developer Platform](https://docs.cdp.coinbase.com/x402/welcome)** · **[MangroveTechnologies](https://github.com/MangroveTechnologies)**

</div>
