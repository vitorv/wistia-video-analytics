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
    ingest.yaml          # PR 2 — Lambda ingestion + EventBridge schedule (DISABLED)
    transforms.yaml      # PR 3 — Glue jobs + Workflow (scheduled trigger DEACTIVATED)
    dashboard.yaml       # PR 4 — ECR + ECS + ALB (TBD)
    monitoring.yaml      # PR 5 — Alarms + SNS (TBD)
  scripts/
    deploy.ps1           # Wrapper: validate + deploy + print outputs
    package-lambda.ps1   # Builds the Lambda zip (and optionally uploads to S3)
    package-transforms.ps1  # Builds the transforms zip + uploads the 3 Glue job scripts
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

### Deploying the ingest stack (PR 2)

The ingest stack has two prerequisites the foundation stack doesn't:

1. **The Lambda zip must exist in the artifacts bucket** before deploy — the
   CFN template references `s3://wistia-artifacts-<acct>-us-east-1/lambda/ingest.zip`.
   Build + upload with:

   ```powershell
   ./infra/scripts/package-lambda.ps1 -Upload
   ```

2. **The Wistia API token must be passed at deploy time** as the
   `WistiaApiToken` parameter. The CFN template marks it `NoEcho`, so it
   doesn't show up in console / describe-stack output, but the value still
   needs to be supplied. The `deploy.ps1` wrapper does **not** read this
   from `.env` for you — invoke the AWS CLI directly:

   ```powershell
   $Token = (Get-Content .env | Select-String '^WISTIA_API_TOKEN=').Line.Split('=', 2)[1]
   aws cloudformation deploy `
       --stack-name wistia-ingest `
       --template-file infra/cloudformation/ingest.yaml `
       --capabilities CAPABILITY_NAMED_IAM `
       --parameter-overrides Env=prod WistiaApiToken=$Token
   ```

### Post-deploy bootstrap — pre-seed the watermark (one-time)

After the ingest stack deploys, **the very first Lambda invocation will run a
full backfill from `BACKFILL_FLOOR_DATE` (2024-03-01)**, which won't fit in
the 5-minute Lambda timeout. To avoid this, pre-seed the watermark in S3 to a
recent date *before* the first invoke:

```powershell
# Build a watermark JSON locally with recent dates for each media
$wm = @{
    events   = @{ gskhw4w4lm = "2026-05-26T00:00:00+00:00"; v08dlrgr7v = "2026-05-26T00:00:00+00:00" }
    by_date  = @{ gskhw4w4lm = "2026-05-25"; v08dlrgr7v = "2026-05-25" }
}
$wm | ConvertTo-Json | Out-File -Encoding utf8 build/seed-watermark.json
aws s3 cp build/seed-watermark.json s3://wistia-datalake-<account>-us-east-1/state/watermark.json
```

Subsequent invocations are incremental and finish in seconds.

### Invoking the ingest Lambda manually

```powershell
# Use --cli-read-timeout 0 since the CLI's default 60s is shorter than the
# Lambda's 300s timeout (matters mainly on the first/seed run).
aws lambda invoke `
    --function-name wistia-prod-ingest `
    --cli-binary-format raw-in-base64-out `
    --cli-read-timeout 0 `
    --payload '{}' `
    build/lambda-invoke-response.json
Get-Content build/lambda-invoke-response.json
```

The EventBridge schedule deploys `DISABLED` — manual invokes are how PR 2
gets verified. PR 5 flips the schedule to `ENABLED` to start the 7-day run.

### Deploying the transforms stack (PR 3)

Like the ingest stack, the transforms stack needs artifacts uploaded before
the deploy:

1. **Build + upload the transforms zip and 3 Glue job scripts**:

   ```powershell
   ./infra/scripts/package-transforms.ps1 -Upload
   ```

   This produces `build/transforms.zip` (~11 KB, pure-Python source only —
   Glue 5.0 provides Spark + Python 3.11 at runtime) and uploads it to
   `s3://wistia-artifacts-.../glue/transforms.zip`. It also uploads the
   three entry-point scripts to `s3://wistia-artifacts-.../glue/{bronze,silver,gold}_job.py`.

2. **Deploy the stack**:

   ```powershell
   ./infra/scripts/deploy.ps1 -Stack transforms
   ```

### Running the transforms workflow manually

The starting trigger in PR 3 is an **ON_DEMAND** trigger
(`wistia-prod-on-demand-start`) — a Glue workflow can only have one
starting trigger, and ON_DEMAND is the type that responds to
`start-workflow-run`. PR 5 replaces this with a SCHEDULED trigger of a
different name for the 7-day production cron.

To kick off a workflow run for verification:

```powershell
aws glue start-workflow-run --name wistia-prod-transforms
```

This returns a `RunId`. The workflow run fires Bronze, then the conditional
triggers chain Silver and Gold. Poll status with:

```powershell
aws glue get-workflow-run `
    --name wistia-prod-transforms `
    --run-id <RunId> `
    --query 'Run.[Status,Statistics]'
```

Total runtime is ~5-10 minutes for our small data (3 jobs × ~1-3 min each;
Glue cold-start adds ~30s per job).

### Updating the transforms code

When you change `src/transforms/*.py` (the pure transforms):

1. Re-run `./infra/scripts/package-transforms.ps1 -Upload` — rebuilds and
   re-uploads the zip.
2. Glue jobs reference the zip by S3 path; each new job run picks up the
   latest zip automatically (unlike Lambda, no `update-function-code`
   needed). The Spark workers fetch `transforms.zip` at job start.

When you change a Glue entry-point script (`src/transforms/glue/*_job.py`):

1. Same `./infra/scripts/package-transforms.ps1 -Upload` — it also re-uploads
   the 3 scripts.
2. Glue picks up the new script on the next job run.

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
