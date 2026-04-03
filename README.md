<div align="center">
  <a href="https://github.com/MangroveTechnologies/app-in-a-box">
    <img src="assets/icon.png" alt="Mangrove" width="120" height="112">
  </a>

  <h1>App-in-a-Box</h1>

  <p>
    <strong>Ship faster with Claude Code.</strong><br>
    A general-purpose FastAPI + Claude Code development template by <a href="https://mangrovedeveloper.ai">Mangrove Technologies</a>.
  </p>

  <p>
    <a href="https://github.com/MangroveTechnologies/app-in-a-box/actions/workflows/ci.yml">
      <img src="https://github.com/MangroveTechnologies/app-in-a-box/actions/workflows/ci.yml/badge.svg" alt="CI">
    </a>
    <a href="https://github.com/MangroveTechnologies/app-in-a-box/blob/main/LICENSE">
      <img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License">
    </a>
  </p>
</div>

---

## What's in the Box

- **FastAPI** backend with REST + MCP dual protocol
- **Claude Code development framework** — 4-phase design lifecycle (requirements → spec → architecture → plan)
- **Agent-driven onboarding** — conversational setup that learns your project
- **Claude Code plugin** — ready-made plugin for your app's end users
- **Three-tier access control** — free, API key auth, x402 payment-gated
- **PostgreSQL + Redis** — optional, via Docker profiles
- **Docker + Terraform** — container-ready with GCP Cloud Run IaC
- **GitHub Actions CI/CD** — lint, test, deploy
- **Tutorial** — build a trading app step-by-step

## Quick Start

### With Claude Code (Recommended)

```bash
git clone https://github.com/MangroveTechnologies/app-in-a-box.git my-app
cd my-app
claude
```

The agent walks you through setup. No prior knowledge needed.

### Without Claude Code

```bash
git clone https://github.com/MangroveTechnologies/app-in-a-box.git my-app
cd my-app
./init.sh --name my-app --gcp-project my-gcp-project --region us-central1
docker compose up -d --build
curl http://localhost:8080/health
```

## Development Lifecycle

App-in-a-box includes a design-first workflow powered by Claude Code skills:

| Phase | Skill | Output |
|-------|-------|--------|
| Onboarding | `/onboard` | Project identity, branding, context |
| Requirements | `/requirements` | User stories, flow diagrams |
| Specification | `/specification` | API contracts, data models |
| Architecture | `/architecture` | System diagrams, module decisions |
| Planning | `/plan` | Implementation tasks |
| Building | Product owner agent | Working application |

## Tutorial

Build a trading app using the Mangrove developer API:

```bash
claude
> /tutorial
```

Or read the docs in `tutorials/trading-app/`.

## Project Structure

```
app-in-a-box/
├── .claude/          # Development framework (skills, agents, rules)
├── server/           # FastAPI application
├── plugin/           # Claude Code plugin for end users
├── tutorials/        # Tutorial reference docs
├── docs/             # Generated design documents
├── assets/           # Branding files
├── branding.json     # Branding configuration
└── init.sh           # Non-interactive setup
```

## Branding

App-in-a-box is Mangrove-branded by default. To re-skin:

1. Edit `branding.json` with your project name, org, colors
2. Replace files in `assets/` with your logos and icons
3. Run `./init.sh` to propagate changes

---

## User Guide

Everything you need to go from zero to a running application.

### Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| **Python** | 3.10+ | [python.org](https://www.python.org/downloads/) or `brew install python` |
| **Docker** | 20+ | [docker.com](https://docs.docker.com/get-docker/) |
| **Claude Code** | Latest | `npm install -g @anthropic-ai/claude-code` |
| **Git** | 2.x | [git-scm.com](https://git-scm.com/) |

Claude Code requires an Anthropic API key. Set it before your first session:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

Or Claude Code will prompt you to sign in on first launch.

### Step 1: Clone the Repo

```bash
git clone https://github.com/MangroveTechnologies/app-in-a-box.git my-app
cd my-app
```

> **Tip:** Replace `my-app` with your project name. The onboarding agent will rename everything for you.

### Step 2: Start Claude Code

```bash
claude
```

Claude detects a fresh app-in-a-box project and begins the onboarding conversation. It will ask you:

1. **What are you building?** — Describe your app in plain language
2. **Why are you building it?** — The problem it solves
3. **What's your experience level?** — So the agent calibrates its guidance
4. **Any preferences?** — Coding style, conventions, libraries
5. **Project identity** — Name, description, branding

The agent updates `branding.json` and `CLAUDE.md` with your answers. When you approve, it hands off to the next phase.

### Step 3: Design Lifecycle

After onboarding, run each skill in order. Each phase produces a document in `docs/` and waits for your approval before proceeding.

#### `/requirements`

The agent interviews you about what your app needs to do, then produces:
- User stories (As a ___, I want ___, so that ___)
- 3+ mermaid user flow diagrams covering 95% of use cases
- Written to `docs/requirements.md`

Review the diagrams and stories. Edit anything that's off. When satisfied, approve to proceed.

#### `/specification`

From your approved requirements, the agent generates:
- API endpoint contracts (method, path, request/response, errors)
- Data models with field types and constraints
- Auth flows and error handling strategy
- Written to `docs/specification.md`

#### `/architecture`

From the approved spec, the agent produces:
- System architecture diagram (mermaid)
- Data flow diagram
- Sequence diagrams for key operations
- Component diagram
- Folder/file hierarchy
- Module retention decisions (what stays, what gets removed)
- Written to `docs/architecture.md`

This is the **subtractive setup** step. App-in-a-box ships with everything (x402 payments, PostgreSQL, Redis, auth middleware). The architecture phase determines what your app actually needs and marks the rest for removal.

#### `/plan`

From the approved architecture, the agent generates:
- Phased implementation plan with numbered tasks
- Dependencies between tasks
- Agent assignments (which subagent handles each task)
- Cleanup step to remove unused scaffold modules
- Written to `docs/implementation-plan.md`

### Step 4: Build

After you approve the plan, the product-owner agent activates. It reads `docs/implementation-plan.md` and drives implementation by delegating tasks to the agent workforce (backend-developer, frontend-developer, test-engineer, etc.).

You stay in the loop — the product owner checks in for approval at key milestones.

### Step 5: Run Locally

```bash
# App only
docker compose up -d --build
curl http://localhost:8080/health

# App + PostgreSQL + Redis
docker compose up -d --build --profile full
```

Or run without Docker:

```bash
cd server
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
ENVIRONMENT=local python -m uvicorn src.app:app --host 0.0.0.0 --port 8080 --reload
```

### Step 6: Run Tests

```bash
cd server
pip install -r requirements.txt
pytest
```

Or with Docker:

```bash
docker compose run --rm app pytest
```

### Step 7: Deploy

#### GCP Cloud Run (included)

```bash
cd infra/terraform
terraform init -backend-config=backend-dev.hcl
terraform plan -var-file=environment-dev.tfvars
terraform apply -var-file=environment-dev.tfvars
```

GitHub Actions CI/CD is pre-configured:
- **ci.yml** — Runs lint (ruff) + tests (pytest) on every push and PR
- **deploy-cloudrun.yaml** — Builds and deploys to Cloud Run on push to `main`

---

## Installing the Plugin

The `plugin/` directory contains a Claude Code plugin for **end users** of your app (not for development — development skills live in `.claude/`).

### For Development (Load Locally)

While building your app, load the plugin for a single session:

```bash
claude --plugin-dir ./plugin
```

### For Distribution

After your app is deployed, users install your plugin:

```bash
# Clone or download your published repo
git clone https://github.com/your-org/your-app.git
cd your-app

# Add to local plugin marketplace and install
claude plugin marketplace add ./plugin
claude plugin install your-app
```

Or load without installing:

```bash
claude --plugin-dir /path/to/your-app/plugin
```

### Plugin Structure

```
plugin/
├── .claude-plugin/
│   └── plugin.json       # Plugin manifest (name, version, author)
├── .mcp.json              # MCP server connection config
├── commands/
│   └── help.md            # /help slash command
├── skills/
│   └── app/SKILL.md       # Main skill for tool interactions
├── hooks/
│   ├── hooks.json         # Hook definitions
│   └── context.json       # Context injection on prompt submit
└── README.md
```

Customize by editing the files above. Add new slash commands as `.md` files in `commands/`. Update `skills/app/SKILL.md` with descriptions of your app's tools.

---

## Tutorial: Build a Trading App

App-in-a-box includes a hands-on tutorial that walks you through building a trading app against the Mangrove developer API.

```bash
claude
> /tutorial
```

The tutorial covers 8 chapters:

| Chapter | Topic |
|---------|-------|
| 0 | Overview and setup |
| 1 | Your first endpoint |
| 2 | MCP tool registration |
| 3 | Service layer pattern |
| 4 | Authentication |
| 5 | x402 payments |
| 6 | Testing |
| 7 | Docker and local development |
| 8 | Deployment to Cloud Run |

Reference docs are in `tutorials/trading-app/` if you prefer to read ahead.

---

## Non-Interactive Setup

If you prefer to skip the agent conversation and bootstrap manually:

```bash
./init.sh --name my-service --gcp-project my-gcp-project --region us-central1
```

This replaces placeholder values across all config files, updates `branding.json`, and self-deletes. You can then run the design lifecycle skills (`/requirements`, `/specification`, etc.) separately, or skip them entirely and start coding.

---

## Re-skinning / Branding

App-in-a-box is Mangrove-branded by default. To use your own brand:

1. **Edit `branding.json`:**
   ```json
   {
     "project_name": "my-project",
     "display_name": "My Project",
     "org_name": "My Org",
     "tagline": "What my project does",
     "urls": {
       "homepage": "https://myproject.com",
       "docs": "https://docs.myproject.com",
       "repository": "https://github.com/my-org/my-project"
     },
     "colors": {
       "primary": "#1a1a2e",
       "secondary": "#16213e",
       "accent": "#e94560"
     },
     "prefix": "my"
   }
   ```

2. **Replace files in `assets/`:**
   - `logo.svg` — Light background logo
   - `logo-dark.svg` — Dark background logo
   - `icon.png` — Square icon (120x120 recommended)
   - `banner.png` — Banner image for README/docs

3. **Run `./init.sh`** or let the `/onboard` skill handle it during agent setup.

---

## FAQ

**Q: Do I need to use every phase of the design lifecycle?**
No. You can skip straight to coding. The skills are there to help you think through your app before building — especially useful if you're not sure what you need yet.

**Q: Can I use this without Claude Code?**
Yes. The server is a standard FastAPI app. Run `./init.sh`, edit the code, and deploy normally. The Claude Code skills and plugin are optional.

**Q: What gets removed during the architecture phase?**
Depends on your app. If you don't need x402 payments, the payment middleware and x402 routes are removed. If you don't need PostgreSQL, the DB config and init scripts are removed. The agent explains what it's removing and why.

**Q: Can I add removed modules back later?**
Yes. The git history preserves everything. You can also re-clone the template and copy modules back in.

**Q: How do I add a new endpoint?**
See the "Adding Endpoints" section in [CLAUDE.md](CLAUDE.md). Short version: create a route, create a service, register both, write tests.

## License

MIT
