#!/bin/bash
# Checks if CLAUDE.md Project Context section has been populated.
# If empty → inject reminder to run /onboard.
# If populated → inject the project context so the agent has it immediately.

CLAUDE_FILE="CLAUDE.md"

if [ ! -f "$CLAUDE_FILE" ]; then
  echo "CLAUDE.md not found. Something is wrong with the project setup."
  exit 0
fi

# Extract everything after "## Project Context" until the next ## or EOF
CONTEXT=$(awk '/^## Project Context/{found=1; next} /^## /{if(found) exit} found{print}' "$CLAUDE_FILE" \
  | grep -v '^$' \
  | grep -v '^<!--')

if [ -z "$CONTEXT" ]; then
  echo "ONBOARDING REQUIRED: The Project Context section in CLAUDE.md is empty. This is a fresh project that has not been set up yet. You MUST run /onboard before doing anything else. Do not skip this step. Greet the user warmly and begin the onboarding conversation."
else
  echo "Project is onboarded. Context: $CONTEXT"
fi

exit 0
