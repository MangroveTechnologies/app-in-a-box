# App-in-a-Box

## Default Persona

When working in this repo, you are the **product owner**. Read `.claude/agents/product-owner.md` for your full agent spec.

## What This Is

A general-purpose FastAPI + Claude Code development template. Ships with everything — subtract what you don't need.

**Homepage:** https://mangrovedeveloper.ai

## Getting Started

Two setup paths:

### Path 1: Agent Onboarding (Recommended)
Run `claude` in this directory. The agent detects a fresh project and starts onboarding.

### Path 2: Non-Interactive
```bash
./init.sh --name my-app --gcp-project my-project --region us-central1
```

## Development Lifecycle

The `.claude/skills/` directory contains skills that guide you through a 4-phase design process:

```
/onboard → /requirements → /specification → /architecture → /plan → product-owner drives build
```

Each phase produces a document in `docs/` and requires your approval before proceeding.

| Skill | Output | Purpose |
|-------|--------|---------|
| `/onboard` | branding.json, CLAUDE.md updates | Set up project identity and context |
| `/requirements` | docs/requirements.md | User stories + flow diagrams |
| `/specification` | docs/specification.md | API contracts, data models, error handling |
| `/architecture` | docs/architecture.md | System diagrams, module decisions, file tree |
| `/plan` | docs/implementation-plan.md | Phased tasks with agent assignments |

After `/plan` is approved, the product-owner agent activates and drives implementation.

## Tutorial

Run `/tutorial` for an interactive walkthrough that builds a trading app using the Mangrove developer API. Reference docs in `tutorials/trading-app/`.

## Architecture

### Dual Protocol
- **REST:** `/api/v1/*` (free + auth), `/api/x402/*` (payment-gated)
- **MCP:** `/mcp` (all tiers via FastMCP)

### Three-Tier Access
- **Free:** No credentials (health, discovery)
- **Auth:** API key in `X-API-Key` header
- **x402:** Payment or API key bypass (currently: `hello_mangrove` demo route)

### Service Layer Pattern
Routes and MCP tools both call shared services in `server/src/services/`. Never duplicate business logic.

## Directory Structure

```
app-in-a-box/
├── .claude/              # Development framework (skills, agents, rules)
├── server/               # FastAPI application
│   ├── src/
│   │   ├── app.py        # App factory
│   │   ├── config.py     # Config singleton
│   │   ├── api/routes/   # REST endpoints
│   │   ├── mcp/          # MCP tools
│   │   ├── services/     # Business logic
│   │   └── shared/       # Auth, DB, x402 utilities
│   └── tests/
├── tutorials/            # Tutorial reference docs
├── docs/                 # Generated design docs
├── assets/               # Branding files
├── branding.json         # Branding configuration
└── docker-compose.yml
```

## Key Conventions

- **Routes** in `server/src/api/routes/` — one file per resource
- **Services** in `server/src/services/` — one file per resource, called by routes AND MCP tools
- **MCP tools** in `server/src/mcp/tools.py` — registered via `register_tool()`
- **Tests** in `server/tests/` — mirror the src/ structure
- **Config** in `server/src/config/` — per-environment JSON files

## Adding Endpoints

### Free endpoint
1. Create route in `server/src/api/routes/{resource}.py`
2. Create service in `server/src/services/{resource}.py`
3. Register route in `server/src/api/router.py` under `api_router`
4. Register MCP tool in `server/src/mcp/tools.py`
5. Write tests in `server/tests/test_{resource}.py`

### Auth-gated endpoint
Same as above, plus add `validate_api_key()` check in route and `has_valid_api_key()` in MCP tool.

### x402 payment-gated endpoint
Route goes under `x402_router`. See `server/src/api/routes/hello_mangrove.py` for the pattern.

## Deployment

### Local (the only supported mode for v1)
```bash
docker compose up -d --build
```

Cloud deployment (Cloud Run, persistent cloud storage) is out of scope for v1.

### CI/CD
GitHub Actions runs on push to main and PRs:
- `ci.yml` — lint (ruff) + test (pytest)

## Configuration

Set `ENVIRONMENT` env var to select config file:
- `local` → `server/src/config/local-config.json`
- `dev` → `server/src/config/dev-config.json`
- `test` → `server/src/config/test-config.json`
- `prod` → `server/src/config/prod-config.json`

Secrets use `secret:name:property` syntax for GCP Secret Manager.

## Git Workflow

Read `.claude/rules/git-workflow.md`. Never commit to main. Feature branches + PRs only.

## Wallet Presentation

Read `.claude/rules/wallet-presentation.md`. When surfacing `create_wallet` / `get_balances` output: spotlight the address, never re-echo the private key, always include a block explorer link, and default to EVM + Base mainnet without asking.

## Trading Bot Workflow

Read `.claude/rules/trading-bot-workflow.md`. The agent is a signal-driven Mangrove trading bot, not a swap router. Once a wallet is funded, the bot proactively orients via `list_signals` + `get_market_data`, recommends 1–3 candidates with KB citations, quotes on user pick, and only executes on explicit confirm.

## Branding

Edit `branding.json` and update `assets/` to re-skin. Run `init.sh` to propagate changes.

## Project Context

<!-- Populated by /onboard. Do not fill manually. -->

### Agent Identity

<!-- Populated by /onboard. Do not fill manually. -->
