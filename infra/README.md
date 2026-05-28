# Wistia Phase 3 — Infrastructure

CloudFormation templates and deploy/teardown scripts for the AWS deployment.
The plan, rationale, and per-PR breakdown live in
[`context_vault/status/phase3_plan.md`](../context_vault/status/phase3_plan.md);
the decision to use CloudFormation is recorded in
[ADR-008](../context_vault/decisions/2026-05-27_cloudformation-iac.md).

## Layout

```
infra/
  cloudformation/
    foundation.yaml      # PR 1 — S3 data lake + artifacts buckets
    ingest.yaml          # PR 2 — Lambda ingestion (TBD)
    transforms.yaml      # PR 3 — Glue jobs + Workflow (TBD)
    dashboard.yaml       # PR 4 — ECR + ECS + ALB (TBD)
    monitoring.yaml      # PR 5 — Alarms + SNS (TBD)
  scripts/
    deploy.ps1           # Wrapper: validate + deploy + print outputs
```

Each PR in Phase 3 adds one template and extends the deploy script's
`-Stack` allowlist.

## Prerequisites

- AWS CLI v2 installed and authenticated (`aws sts get-caller-identity`
  should return your account).
- Default region set to `us-east-1`:
  `aws configure get region` should print `us-east-1`.
- AWS Budgets alarm in place (see
  [`phase3_plan.md` § 0.3](../context_vault/status/phase3_plan.md)).

## Deploy

```powershell
./infra/scripts/deploy.ps1 -Stack foundation
```

The wrapper validates the template, deploys (creates or updates the stack),
and prints the stack outputs.

To deploy a non-prod environment:

```powershell
./infra/scripts/deploy.ps1 -Stack foundation -Env dev
```

## Verify

After deploy, confirm in the console:

1. **CloudFormation → Stacks → `wistia-foundation`** → status `CREATE_COMPLETE`.
2. **S3 → Buckets** → both `wistia-datalake-<account>-us-east-1` and
   `wistia-artifacts-<account>-us-east-1` exist with SSE-S3 encryption and
   public access blocked.

Or via CLI:

```powershell
aws cloudformation describe-stacks --stack-name wistia-foundation `
    --query 'Stacks[0].StackStatus'
```

## Tear down

Reverse-dependency order. Foundation last because downstream stacks reference
its exports.

```powershell
# Once compute stacks exist, delete them first:
# aws cloudformation delete-stack --stack-name wistia-monitoring
# aws cloudformation delete-stack --stack-name wistia-dashboard
# aws cloudformation delete-stack --stack-name wistia-transforms
# aws cloudformation delete-stack --stack-name wistia-ingest

# Empty the data buckets before deleting the foundation stack —
# CFN refuses to delete non-empty buckets.
aws s3 rm s3://wistia-datalake-<account>-us-east-1 --recursive
aws s3 rm s3://wistia-artifacts-<account>-us-east-1 --recursive

aws cloudformation delete-stack --stack-name wistia-foundation
```

A full teardown script (`teardown.ps1`) is added in PR 5.
