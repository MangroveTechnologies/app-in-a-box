#!/bin/bash
# SessionStart hook — routes the agent to the correct first action.
#
# This repo ships a ready-to-run Mangrove trading bot. The default path
# for a fresh clone is:
#   1. Read .claude/rules/trading-bot-workflow.md
#   2. Eager-load the full MCP toolset
#   3. Call list_wallets + list_strategies to detect fresh state
#   4. If fresh, deliver Stage 0 greeter (security primer + wallet fork)
#
# The /onboard skill is a SEPARATE path for users who want to rebrand the
# template into a different app (NOT a trading bot). It must be invoked
# explicitly by the user — never auto-fired on a fresh clone, or workshop
# attendees get routed into a 4-phase design flow they don't need.
#
# A gitignored marker file at .claude/.onboarded indicates the user has
# explicitly run /onboard. If present, the hook surfaces the committed
# Project Context (their persona + project identity) so the rebrand
# persists across sessions. If absent, the hook tells the agent: you're
# the trading bot — go to Stage 0.

MARKER=".claude/.onboarded"
CLAUDE_FILE="CLAUDE.md"

if [ ! -f "$MARKER" ]; then
  cat <<'EOF'
FRESH CLONE — TRADING BOT MODE.

This repo is a ready-to-run Mangrove trading bot. Your first actions:

1. Read .claude/rules/trading-bot-workflow.md — specifically the
   "Stage 0 — First-run greeting" section.
2. Eager-load the full MCP toolset per that rule file.
3. Call list_wallets and list_strategies to determine trigger state.
4. If list_wallets is empty, deliver the Stage 0 greeter exactly as
   the rule specifies: brief introduction, the 6-bullet security
   primer, a status sanity check, then ask "existing wallet or new?"
5. Proceed per the user's answer.

DO NOT invoke the /onboard skill. That skill is only for users who
explicitly want to rebrand this template into a DIFFERENT project
(not a trading bot). Workshop attendees and trading-bot users never
need it. If you feel tempted to invoke /onboard on a fresh clone,
stop and re-read this message.

Your default persona is the one described in trading-bot-workflow.md
(concise, security-conscious, strategy-first). Any CLAUDE.md
"Default Persona" block that says "product owner" is template
boilerplate from the rebrand path — ignore it unless .claude/.onboarded
exists.
EOF
  exit 0
fi

if [ ! -f "$CLAUDE_FILE" ]; then
  echo "Onboarding marker is present but CLAUDE.md is missing. Something is wrong with the project setup."
  exit 0
fi

# Rebrand path: marker present means user has explicitly run /onboard.
# Surface the Project Context they configured so the rebrand persona
# and project identity carry across sessions.
CONTEXT=$(awk '/^## Project Context/{found=1; next} /^## /{if(found) exit} found{print}' "$CLAUDE_FILE" \
  | grep -v '^$' \
  | grep -v '^<!--')

if [ -z "$CONTEXT" ]; then
  echo "Onboarding marker is present but Project Context in CLAUDE.md is empty. Re-run /onboard to repopulate, or remove .claude/.onboarded to return to default trading-bot mode."
else
  echo "User has run /onboard — using their rebrand context: $CONTEXT"
fi

exit 0
