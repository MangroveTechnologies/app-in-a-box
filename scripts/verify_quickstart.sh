#!/usr/bin/env bash
# verify_quickstart.sh — prove defi-agent is set up correctly.
#
# Checks (in order):
#   1. Docker is installed + running
#   2. server/src/config/local-config.json exists and has a non-placeholder API key
#   3. docker compose up --build succeeds
#   4. GET /health returns 200 within 30 seconds
#   5. GET /api/v1/agent/status returns 200 (free discovery)
#   6. GET /api/v1/agent/tools with X-API-Key returns the expected tool count
#   7. Logs emit the expected startup events (db.migrated, scheduler.started, app.startup)
#
# Exits 0 on success, non-zero on failure. Target runtime under 300 seconds
# from a cold clone (Docker first-build included).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

BASE_URL="${BASE_URL:-http://localhost:8080}"
HEALTH_TIMEOUT_S=30
START_TIME=$(date +%s)

# -- helpers ----------------------------------------------------------------

GREEN="\033[32m"; RED="\033[31m"; YELLOW="\033[33m"; DIM="\033[2m"; CLR="\033[0m"

step() { printf "${YELLOW}==>${CLR} %s\n" "$1"; }
ok()   { printf "${GREEN}  ✓${CLR} %s\n" "$1"; }
fail() { printf "${RED}  ✗${CLR} %s\n" "$1" >&2; exit 1; }
info() { printf "${DIM}    %s${CLR}\n" "$1"; }

elapsed() { echo $(( $(date +%s) - START_TIME )); }

# -- 1. Docker available ----------------------------------------------------

step "1. Docker available"
if ! command -v docker >/dev/null 2>&1; then
    fail "docker not found on PATH — install from https://docs.docker.com/get-docker/"
fi
if ! docker info >/dev/null 2>&1; then
    fail "docker daemon not running — start Docker Desktop or dockerd"
fi
ok "docker is installed and running"

# -- 2. Config present ------------------------------------------------------

step "2. server/src/config/local-config.json exists + has a real API key"
CFG="server/src/config/local-config.json"
if [ ! -f "$CFG" ]; then
    fail "$CFG missing — run: cp server/src/config/local-example-config.json $CFG && edit"
fi
if grep -q "REPLACE_WITH" "$CFG"; then
    fail "$CFG still contains REPLACE_WITH placeholder — set a real MANGROVE_API_KEY"
fi
if ! grep -q '"MANGROVE_API_KEY"' "$CFG"; then
    fail "$CFG missing MANGROVE_API_KEY"
fi
ok "config looks good"

# -- 3. docker compose up ---------------------------------------------------

step "3. docker compose up --build (first build may take ~60s)"
# Ensure ./agent.db is a file (not a directory) before compose bind-mounts it.
# Docker Desktop on macOS creates missing mount targets as directories,
# which breaks SQLite. A plain `touch` makes it a zero-byte file that
# SQLite will happily open and migrate.
if [ -d "./agent.db" ]; then
    rmdir ./agent.db 2>/dev/null || fail "./agent.db exists as a non-empty directory — remove it manually"
fi
if [ ! -e "./agent.db" ]; then
    touch ./agent.db
fi
if ! docker compose up -d --build >/dev/null 2>&1; then
    fail "docker compose up failed — rerun without redirect to see errors"
fi
ok "container started"

# Cleanup on exit ONLY IF the user asks us to.
cleanup() {
    if [ "${VERIFY_STOP_ON_EXIT:-0}" = "1" ]; then
        docker compose down >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT

# -- 4. /health reachable ---------------------------------------------------

step "4. waiting for /health (up to ${HEALTH_TIMEOUT_S}s)"
for i in $(seq 1 $HEALTH_TIMEOUT_S); do
    if curl -fsS "$BASE_URL/health" >/dev/null 2>&1; then
        ok "/health returned 200 after ${i}s"
        break
    fi
    if [ "$i" = "$HEALTH_TIMEOUT_S" ]; then
        fail "/health did not respond within ${HEALTH_TIMEOUT_S}s — check: docker compose logs"
    fi
    sleep 1
done

# -- 5. /status (free) ------------------------------------------------------

step "5. GET /api/v1/agent/status"
STATUS_JSON="$(curl -fsS "$BASE_URL/api/v1/agent/status")" \
    || fail "/status request failed"
VERSION="$(echo "$STATUS_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("version",""))')"
if [ -z "$VERSION" ]; then
    fail "/status did not return a version field: $STATUS_JSON"
fi
ok "agent version $VERSION"

# -- 6. /tools with X-API-Key -----------------------------------------------

step "6. GET /api/v1/agent/tools with API key"
API_KEY="$(python3 -c "import json; print(json.load(open('$CFG')).get('API_KEYS','').split(',')[0].strip())")"
if [ -z "$API_KEY" ]; then
    fail "could not read API_KEYS from $CFG"
fi

TOOLS_JSON="$(curl -fsS -H "X-API-Key: $API_KEY" "$BASE_URL/api/v1/agent/tools")" \
    || fail "/tools request failed"

TOOL_COUNT="$(echo "$TOOLS_JSON" | python3 -c 'import json,sys; print(len(json.load(sys.stdin).get("tools",[])))')"
if [ "$TOOL_COUNT" -lt 22 ]; then
    fail "expected >=22 tools, got $TOOL_COUNT"
fi
ok "tool catalog returned $TOOL_COUNT tools"

# -- 7. Startup log events --------------------------------------------------

step "7. verifying startup log events"
LOGS="$(docker compose logs --no-color 2>&1 || true)"
for event in "db.migrated" "scheduler.started" "app.startup"; do
    if ! echo "$LOGS" | grep -q "$event"; then
        fail "startup log event '$event' not found — check: docker compose logs"
    fi
done
ok "db.migrated + scheduler.started + app.startup all present"

# -- summary ----------------------------------------------------------------

TOTAL="$(elapsed)"
printf "\n${GREEN}✓ quickstart verified in ${TOTAL}s${CLR}\n\n"
info "defi-agent is running at ${BASE_URL}"
info "point Claude Code at .mcp.json.example (copy into your project)"
info "stop with: docker compose down"
