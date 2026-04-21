#!/bin/bash
# Checks whether the user has completed onboarding on THIS machine.
#
# Onboarding state is tracked via a gitignored marker file at
# .claude/.onboarded. This is intentionally per-user / per-clone state,
# not something that lives in the repo, so that anyone who clones a repo
# previously onboarded by someone else is still prompted to onboard
# themselves (the repo's CLAUDE.md may contain the maintainer's context,
# which is not the cloner's).
#
# If the marker is missing: inject a system reminder telling the agent to
# run /onboard before anything else.
#
# If the marker is present: inject the Project Context from CLAUDE.md so
# the agent picks up the user's configured identity + project immediately.

MARKER=".claude/.onboarded"
CLAUDE_FILE="CLAUDE.md"

if [ ! -f "$MARKER" ]; then
  echo "ONBOARDING REQUIRED: This clone has not been onboarded on this machine. The Project Context you may see in CLAUDE.md belongs to whoever last committed to this repo, not to the current user. You MUST run /onboard before doing anything else. Do not skip this step. Greet the user warmly and begin the onboarding conversation."
  exit 0
fi

if [ ! -f "$CLAUDE_FILE" ]; then
  echo "Onboarding marker is present but CLAUDE.md is missing. Something is wrong with the project setup."
  exit 0
fi

# Extract everything after "## Project Context" until the next ## or EOF
CONTEXT=$(awk '/^## Project Context/{found=1; next} /^## /{if(found) exit} found{print}' "$CLAUDE_FILE" \
  | grep -v '^$' \
  | grep -v '^<!--')

if [ -z "$CONTEXT" ]; then
  echo "Onboarding marker is present but Project Context in CLAUDE.md is empty. Re-run /onboard to repopulate, or remove .claude/.onboarded to start over."
else
  echo "Project is onboarded. Context: $CONTEXT"
fi

exit 0
