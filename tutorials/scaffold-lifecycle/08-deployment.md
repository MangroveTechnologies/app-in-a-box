# Chapter 8: Deployment

## What Happens

Deploy the trading app to production.

## Local Testing

```bash
# Build and start
docker compose up -d --build

# Verify health
curl http://localhost:9080/health

# Test an endpoint
curl http://localhost:9080/api/v1/echo -X POST -H "Content-Type: application/json" -d '{"message": "hello"}'

# Test auth endpoint
curl http://localhost:9080/api/v1/marketplace/listings -H "X-API-Key: dev-key-1"
```

## GCP Cloud Run (Optional)

1. Set up Terraform:
```bash
cd infra/terraform
terraform init -backend-config=backend-dev.hcl
terraform plan -var-file=environment-dev.tfvars
```

2. Deploy via GitHub Actions or manual push

## CI/CD Verification

After pushing:
```bash
gh run list --limit 5
gh run watch
```

## Congratulations!

You've completed the tutorial. Your trading app is:
- Built with proper requirements, spec, and architecture
- Tested with TDD
- Packaged with a Claude Code plugin
- Ready for production deployment
