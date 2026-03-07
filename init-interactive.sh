#!/usr/bin/env bash
set -euo pipefail

# gcp-app-template bootstrap script (interactive, human-friendly)
# Prompts for values, then calls init.sh

echo "=== gcp-app-template bootstrap ==="
echo ""

read -rp "Service name (e.g. my-service): " NAME
read -rp "GCP project ID: " GCP_PROJECT
read -rp "GCP region [us-central1]: " REGION
REGION="${REGION:-us-central1}"

echo ""
echo "Will configure:"
echo "  Service name: $NAME"
echo "  GCP project:  $GCP_PROJECT"
echo "  Region:       $REGION"
echo ""
read -rp "Proceed? [Y/n] " CONFIRM
CONFIRM="${CONFIRM:-Y}"

if [[ "$CONFIRM" =~ ^[Yy]$ ]]; then
  ./init.sh --name "$NAME" --gcp-project "$GCP_PROJECT" --region "$REGION"
else
  echo "Aborted."
fi
