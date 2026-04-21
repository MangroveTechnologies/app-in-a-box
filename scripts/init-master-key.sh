#!/usr/bin/env bash
# init-master-key.sh — generate and persist the Fernet master key.
#
# Why this exists:
#   The agent encrypts wallet secrets with a Fernet master key. By
#   default the key lives in the OS keychain (macOS Keychain, Linux
#   Secret Service, Windows Credential Manager). Inside a Docker
#   container NONE of these backends are reachable — so without
#   MASTER_KEY_ENV_FALLBACK set, each container process generates a
#   fresh in-memory key that dies on restart, stranding any wallets
#   encrypted with it (agent.db rows become un-decryptable).
#
# What this does:
#   1. Ensures server/src/config/local-config.json exists
#   2. Reads MASTER_KEY_ENV_FALLBACK — if already set, no-op (idempotent)
#   3. Else: generates a Fernet key (32 random bytes, urlsafe-b64 encoded
#      via Python stdlib — no `cryptography` package needed on the host,
#      matches the exact format cryptography.fernet.Fernet.generate_key
#      produces) and writes it to the config field
#
# local-config.json is gitignored — the key stays on this machine only.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

CONFIG_FILE="server/src/config/local-config.json"

GREEN="\033[32m"; RED="\033[31m"; YELLOW="\033[33m"; DIM="\033[2m"; CLR="\033[0m"
step() { printf "${YELLOW}==>${CLR} %s\n" "$1"; }
ok()   { printf "${GREEN}  ✓${CLR} %s\n" "$1"; }
fail() { printf "${RED}  ✗${CLR} %s\n" "$1" >&2; exit 1; }
info() { printf "${DIM}    %s${CLR}\n" "$1"; }

# -- 1. python3 on PATH -----------------------------------------------------

step "1. python3 available"
if ! command -v python3 >/dev/null 2>&1; then
  fail "python3 not on PATH. Install Python 3 (macOS: 'brew install python@3.11'; Linux: distro package; Windows: python.org)."
fi
ok "python3 found: $(command -v python3)"

# -- 2. Local config present ------------------------------------------------

step "2. Local config present"
if [ ! -f "$CONFIG_FILE" ]; then
  fail "$CONFIG_FILE not found. Run 'cp server/src/config/local-example-config.json $CONFIG_FILE' first (quickstart step 2)."
fi
ok "$CONFIG_FILE found"

# -- 3. Inspect MASTER_KEY_ENV_FALLBACK -------------------------------------

step "3. Read MASTER_KEY_ENV_FALLBACK"
CURRENT="$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('MASTER_KEY_ENV_FALLBACK', ''))")"
if [ -n "$CURRENT" ]; then
  info "already set: ${CURRENT:0:8}... (length ${#CURRENT})"
  ok "idempotent — nothing to do"
  echo
  echo "Master key is already persisted. Wallet secrets encrypted with it"
  echo "will survive container rebuilds."
  exit 0
fi
info "empty — will generate a new key"

# -- 4. Generate + write Fernet key -----------------------------------------

step "4. Generate Fernet key and write to $CONFIG_FILE"
python3 - <<PY
import base64, json, os, sys

# Fernet.generate_key() source: base64.urlsafe_b64encode(os.urandom(32))
# We replicate it exactly without needing the 'cryptography' package on the host.
key = base64.urlsafe_b64encode(os.urandom(32)).decode()
assert len(key) == 44, f"unexpected key length: {len(key)}"

path = "$CONFIG_FILE"
with open(path) as f:
    cfg = json.load(f)
cfg["MASTER_KEY_ENV_FALLBACK"] = key
with open(path, "w") as f:
    json.dump(cfg, f, indent=2)
    f.write("\n")
print(f"  ok ({len(key)} chars)", file=sys.stderr)
PY
ok "written"

# -- 5. Sanity re-read ------------------------------------------------------

step "5. Sanity check"
WROTE="$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('MASTER_KEY_ENV_FALLBACK', ''))")"
if [ -z "$WROTE" ] || [ "${#WROTE}" -ne 44 ]; then
  fail "post-write verification failed"
fi
info "persisted: ${WROTE:0:8}... (length ${#WROTE})"
ok "verified"

echo
printf "${GREEN}Done.${CLR} Master key persisted to $CONFIG_FILE.\n\n"
echo "Next step: 'docker compose up -d --build' will pick up the key."
echo "Wallets created from here on survive container restarts."
echo
echo "NOTE: wallets created BEFORE this step were encrypted with an"
echo "in-memory key that is gone on rebuild. Their agent.db rows cannot"
echo "be decrypted by the new container. Recover funds off-agent via"
echo "the saved wallet secret (MetaMask → Import Account), then create"
echo "a fresh wallet under the persisted key."
