# Chapter 03 — Setup

*10 minutes. No funds required. First chapter with actual commands.*

Goal: clone the repo, run the setup script, verify the server is up,
register the MCP server with Claude Code, and see the Stage 0 greeter
fire in a fresh Claude Code session.

## Before you start

You should already have these installed (see
[`docs/workshop-prereqs.md`](../../docs/workshop-prereqs.md) if not):

- **Python 3.11 or newer** (`python3 --version` to check)
- **Git** (`git --version`)
- **Claude Code CLI** (`claude --version`; install via
  `npm install -g @anthropic-ai/claude-code`)
- **A Mangrove API key** (the workshop facilitator will hand one out,
  or grab one from https://mangrovedeveloper.ai)
- **VSCode** (recommended — the integrated terminal makes things
  smoother)
- **Git Bash** if you're on Windows (macOS and Linux use their
  built-in shells)

All four commands should print a version and exit cleanly. If any
don't, stop and fix that before continuing — setup won't work with
missing pieces.

## 1. Clone the repo

```bash
cd ~/Desktop   # or wherever you keep projects
git clone https://github.com/MangroveTechnologies/app-in-a-box.git defi-agent
cd defi-agent
```

You'll end up in a directory with `README.md`, `scripts/`, `server/`,
`tutorials/`, and a handful of other things. Verify:

```bash
ls
```

Should show at least: `README.md`, `scripts/`, `server/`, `tutorials/`,
`docs/`, `docker-compose.yml`.

## 2. Run setup

One command does everything:

```bash
./scripts/setup.sh
```

First run takes about 60 seconds. It does, in order:

1. Copies `server/src/config/local-example-config.json` to
   `local-config.json` if it doesn't exist.
2. Asks for your `MANGROVE_API_KEY`. Paste it when prompted. (Or
   pre-set via `./scripts/setup.sh --api-key <key>` for non-interactive
   setups.)
3. Asks for the `MANGROVEMARKETS_BASE_URL`. Accept the default
   (Mangrove's hosted URL) unless the facilitator told you otherwise.
4. Creates `agent-data/` (chmod 700) for durable state.
5. Builds a Python venv at `.venv/` and `pip install`s dependencies.
6. Starts the uvicorn server in the background on
   `http://localhost:9080`.
7. Waits for `/health` to return 200 before moving on.
8. Registers the MCP server with Claude Code via
   `claude mcp add -s local defi-agent http://localhost:9080/mcp/`.
9. Runs a quick verify pass — hits a few endpoints to confirm the
   tool catalog loaded.

If everything went well, the last thing you see is:

```
==> Done. Setup complete.
    Agent: http://localhost:9080
    PID:   12345  (agent-data/bare.pid)
    Logs:  agent-data/bare.log

    Restart Claude Code in this directory to load the 41 defi-agent
    tools. Then try: "Status check. List my wallets and strategies."
```

### If something went wrong

**"python3 not on PATH"** — install Python 3.11+ and rerun.

**"MANGROVE_API_KEY is still the placeholder"** — the prompt
misfired. Edit `server/src/config/local-config.json` and paste your
key into the `MANGROVE_API_KEY` field.

**"/health did not respond"** — the server started but failed to
come up. Check `agent-data/bare.log` for a traceback. Common causes:
port conflict (something else on 9080), missing Python dependency,
or a syntax error in the config file.

**Port 9080 is already taken** — if some other dev tool is using 9080
too, bind somewhere else:

```bash
# Kill the bg uvicorn if it started anyway
kill $(cat agent-data/bare.pid) 2>/dev/null

# Bind on a different port
BARE_PORT=9082 ./scripts/run-bare.sh &
```

Then also update your `.mcp.json` or re-register with Claude Code at
the new port.

## 3. Sanity-check the server

```bash
curl -s http://localhost:9080/health
```

Expected output:

```json
{"status":"healthy","timestamp":"2026-04-24T..."}
```

With your API key:

```bash
curl -s -H 'X-API-Key: dev-key-1' http://localhost:9080/api/v1/agent/status \
  | python3 -m json.tool
```

Expected: JSON with `version`, `wallets_count: 0`, `strategies` block
with all-zero counts, `active_cron_jobs: 0`, and a `db_path`.

The `dev-key-1` above is the **local** API key the agent uses to
authenticate your own requests. It's in
`server/src/config/local-config.json` under `API_KEYS`. This is NOT
your Mangrove API key — that's a separate thing the agent uses to
talk to Mangrove's hosted API.

## 4. Verify the MCP registration

```bash
claude mcp list
```

Expected: a line like

```
defi-agent: http://localhost:9080/mcp/ (HTTP) - ✓ Connected
```

If it says `✗ Failed to connect`, the MCP URL in Claude Code's
registration doesn't match where the server is actually listening.
Usually because port 9080 is squatted and the server is on a
different port. Re-register:

```bash
claude mcp remove defi-agent
claude mcp add -s local -t http defi-agent http://localhost:<PORT>/mcp/ \
  --header "X-API-Key: dev-key-1"
```

(Where `<PORT>` is whatever port your server actually landed on.)

## 5. First Claude Code session

**Close any existing Claude Code sessions** in this directory. Then
start fresh:

```bash
claude
```

Claude Code detects the `.mcp.json` and the local registration, loads
the 41 tools, and the Stage 0 greeter fires automatically. You'll
see something like:

> Hey — I'm your local Mangrove-powered trading bot. I live entirely
> on your machine — the strategy backend and knowledge base are
> remote, but your keys, database, and agent process are all local.
>
> Quick orientation before we touch anything:
>
> 1. Your keys stay on this machine. The master key lives in
>    `./agent-data/master.key` (chmod 600) or your OS keychain —
>    never sent anywhere.
> 2. Wallet secrets never enter this chat. When we create a wallet,
>    I'll hand you a `secret_id` and you'll run
>    `./scripts/reveal-secret.sh <id>` in a terminal to back it up.
> 3. Imports work the same way in reverse. Run
>    `./scripts/stash-secret.sh` in a terminal to import an existing
>    wallet.
> 4. Live trading is gated on backup confirmation
>    (`./scripts/confirm-backup.sh <address>`). Paper mode is
>    unrestricted.
> 5. Paper first, always. New strategies start in paper mode with
>    simulated fills.
> 6. Hooks block key pastes. If you fat-finger a key into chat,
>    it'll be refused — that's intentional.
>
> Do you have an existing wallet you want to use, or should I create
> a fresh one?

**For now, say: "Skip the wallet for now — I want to try paper
trading first."**

The bot will acknowledge, and you're ready for Chapter 04. If the
greeter doesn't fire — the bot just says "hey" without the orientation
— see troubleshooting below.

## Troubleshooting

### "The greeter didn't fire"

Usually one of three things:

1. **Tools didn't load.** The bot can't complete Stage 0 without
   calling `list_wallets` and `list_strategies`. If you see a
   "ToolSearch" call that returns nothing, or a "the defi-agent MCP
   server isn't connected" message, go back to step 4 and fix the
   MCP registration.
2. **You've already onboarded in this session.** If `.claude/.onboarded`
   exists, the greeter won't fire (it's designed for fresh clones).
   `rm .claude/.onboarded` to reset.
3. **Claude Code was started from the wrong directory.** MCP local
   registrations are keyed to the project directory. Make sure
   you're in `~/Desktop/defi-agent` (or wherever you cloned).

### "I see 24 tools instead of 41"

You're on an older version of the repo. `git pull origin main` to
get the latest, then restart the server:

```bash
kill $(cat agent-data/bare.pid) 2>/dev/null
./scripts/setup.sh --yes --no-mcp --no-verify
```

### "Hmm, not working" — the nuclear reset

```bash
# 1. Stop the server
kill $(cat agent-data/bare.pid) 2>/dev/null

# 2. Wipe all local state (strategies, trades, wallets, scheduler)
rm -rf agent-data/

# 3. Remove the MCP registration
claude mcp remove defi-agent 2>/dev/null

# 4. Re-setup from scratch
./scripts/setup.sh

# 5. Restart Claude Code in this directory
```

You'll lose any strategies or trades you'd started, but you'll be
back to a known-good state.

## What to take away

- The server is one Python process on `localhost:9080`. No Docker
  required.
- The MCP registration lives in `claude mcp list`. Keep them in
  sync — that's the single biggest thing that breaks after moving
  the repo or changing ports.
- The Stage 0 greeter is your signal that tools loaded correctly.
  If you see it, setup worked.

You now have a running trading bot with zero strategies and no
wallet. Next, we make something it can actually do.

→ [Chapter 04 — Your first strategy](04-your-first-strategy.md)
