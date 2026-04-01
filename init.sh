#!/usr/bin/env bash
set -euo pipefail

# x402-app-template bootstrap script (non-interactive, agent-friendly)
# Usage: ./init.sh --name my-service --gcp-project my-gcp-project [--region us-central1]

NAME=""
GCP_PROJECT=""
REGION="us-central1"

while [[ $# -gt 0 ]]; do
  case $1 in
    --name) NAME="$2"; shift 2 ;;
    --gcp-project) GCP_PROJECT="$2"; shift 2 ;;
    --region) REGION="$2"; shift 2 ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

if [[ -z "$NAME" || -z "$GCP_PROJECT" ]]; then
  echo "Usage: ./init.sh --name <service-name> --gcp-project <gcp-project-id> [--region <region>]"
  exit 1
fi

echo "Bootstrapping: $NAME (GCP: $GCP_PROJECT, Region: $REGION)"

# Replace placeholders across all files
find . -type f \( -name "*.py" -o -name "*.json" -o -name "*.yaml" -o -name "*.yml" \
  -o -name "*.tf" -o -name "*.tfvars" -o -name "*.hcl" -o -name "*.toml" \
  -o -name "*.md" -o -name "*.env*" -o -name "Dockerfile" \) \
  -not -path "./.git/*" -not -path "./venv/*" -not -path "./__pycache__/*" \
  -exec sed -i "s/YOUR_SERVICE_NAME/$NAME/g" {} + \
  -exec sed -i "s/YOUR_GCP_PROJECT/$GCP_PROJECT/g" {} + \
  -exec sed -i "s/YOUR_TERRAFORM_STATE_BUCKET/${GCP_PROJECT}-terraform-state/g" {} +

# Update pyproject.toml project name
sed -i "s/x402-app-template/$NAME/g" server/pyproject.toml

# Update FastAPI title
sed -i "s/x402 App Template/$NAME/g" server/src/app.py

# Update MCP server name
sed -i "s/x402-app-template/$NAME/g" server/src/mcp/server.py

# Derive display name from service name (capitalize, replace hyphens with spaces)
SERVICE_NAME="$NAME"
DISPLAY_NAME=$(echo "$NAME" | sed 's/-/ /g' | awk '{for(i=1;i<=NF;i++) $i=toupper(substr($i,1,1)) substr($i,2)}1')

# Update branding.json
if [ -f branding.json ]; then
    sed -i '' "s/\"project_name\": \"app-in-a-box\"/\"project_name\": \"$SERVICE_NAME\"/" branding.json
    sed -i '' "s/\"display_name\": \"App-in-a-Box\"/\"display_name\": \"$DISPLAY_NAME\"/" branding.json
fi

echo ""
echo "Done. Files updated with:"
echo "  Service name: $NAME"
echo "  GCP project:  $GCP_PROJECT"
echo "  Region:       $REGION"
echo ""
echo "Next steps:"
echo "  1. cp server/src/config/local-example-config.json server/src/config/local-config.json"
echo "  2. docker compose up -d --build"
echo "  3. curl http://localhost:8080/health"
echo ""

# Self-delete
rm -f init.sh init-interactive.sh
