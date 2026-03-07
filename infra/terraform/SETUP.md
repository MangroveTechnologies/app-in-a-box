# Terraform Setup

## Prerequisites

1. GCP project created
2. Terraform 1.5+ installed
3. GCS bucket for Terraform state
4. OIDC workload identity configured for GitHub Actions

## First-Time Setup

### 1. Create Terraform state bucket

```bash
gsutil mb -p YOUR_GCP_PROJECT -l us-central1 gs://YOUR_GCP_PROJECT-terraform-state
gsutil versioning set on gs://YOUR_GCP_PROJECT-terraform-state
```

### 2. Initialize and apply

```bash
cd infra/terraform
terraform init -backend-config=backend-dev.hcl
terraform plan -var-file=environment-dev.tfvars
terraform apply -var-file=environment-dev.tfvars
```

### 3. Set up OIDC for GitHub Actions

Create workload identity pool and provider:

```bash
gcloud iam workload-identity-pools create "github-pool" \
  --location="global" \
  --display-name="GitHub Actions Pool" \
  --project=YOUR_GCP_PROJECT

gcloud iam workload-identity-pools providers create-oidc "github-provider" \
  --location="global" \
  --workload-identity-pool="github-pool" \
  --display-name="GitHub Provider" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --project=YOUR_GCP_PROJECT
```

Grant the service account permissions:

```bash
gcloud iam service-accounts add-iam-policy-binding \
  "github-actions-deployer@YOUR_GCP_PROJECT.iam.gserviceaccount.com" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/github-pool/attribute.repository/MangroveTechnologies/YOUR_REPO_NAME" \
  --project=YOUR_GCP_PROJECT
```

### 4. Add GitHub secrets

- `GCP_WORKLOAD_IDENTITY_PROVIDER`: `projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/github-pool/providers/github-provider`
- `GCP_SERVICE_ACCOUNT_EMAIL`: `github-actions-deployer@YOUR_GCP_PROJECT.iam.gserviceaccount.com`

### 5. Create Secret Manager secret

```bash
echo '{"db_password":"your-password","api_keys":"key1,key2","redis_url":"redis://..."}' | \
  gcloud secrets versions add app-config-dev --data-file=- --project=YOUR_GCP_PROJECT
```

## Outputs

After `terraform apply`:
- `service_url` -- Cloud Run service URL
- `artifact_registry_repo` -- AR repository path
