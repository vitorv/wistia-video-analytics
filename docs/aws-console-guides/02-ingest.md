# PR 2 — Ingest (Lambda + EventBridge): AWS Console Walkthrough

> A pure web-UI version of what `infra/cloudformation/ingest.yaml` deploys,
> plus the post-deploy operations (invoke, view logs, inspect IAM, update
> code, tear down) you'll routinely run in the console.
>
> **Outcome:** an AWS Lambda function in `us-east-1` named `wistia-prod-ingest`
> that pulls the Wistia Stats API and writes raw JSON to
> `s3://wistia-datalake-<account>-us-east-1/landing/`. An EventBridge rule
> exists on a daily 06:00 UTC cron schedule, **DISABLED** — PR 5 will enable
> it for the 7-day production run.
>
> **Three paths** are documented below:
> - **Path A** (recommended): upload the Lambda zip to S3, upload `ingest.yaml`
>   to the CloudFormation console, supply the API token at parameter time, and
>   click "Create stack." Same outcome as the CLI deploy in PR 2.
> - **Operating section**: invoke the Lambda manually, read CloudWatch Logs,
>   inspect the EventBridge rule and IAM role. These are the day-to-day tasks
>   you'll do in the console regardless of how the stack got deployed.
> - **Manual setup (Path B)** is intentionally not covered. PR 1 had two
>   resources; PR 2 has five with cross-references. The CFN-via-console path
>   exists exactly to spare you from clicking each one through manually.

---

## Prerequisites

1. **PR 1 already deployed** — the `wistia-foundation` stack must exist in
   `us-east-1` because PR 2 imports its bucket exports. If not, follow
   [`01-foundation.md`](01-foundation.md) first.
2. **Region locked to N. Virginia (us-east-1)** — top-right region dropdown.
   Re-check this on *every* console page; the dropdown is sticky per tab but
   not per session.
3. **A Wistia API token** — the project's bearer token. It's in `.env`
   locally as `WISTIA_API_TOKEN`. You'll paste it into a `NoEcho` parameter
   field during stack creation; the value is never displayed after that.
4. **A built Lambda zip** — `build/lambda.zip` produced by
   `infra/scripts/package-lambda.ps1`. If you don't have one, run:
   ```powershell
   ./infra/scripts/package-lambda.ps1
   ```
   The script installs runtime deps into `build/lambda/`, copies `src/common`
   + `src/ingestion`, and produces a ~15.5 MB zip at `build/lambda.zip`.
5. Your **AWS account ID** (12 digits). Find it via the username menu
   top-right of the console, or `aws sts get-caller-identity --query Account`.

In the bucket names below, substitute your account ID for `<account>`.

---

## Path A — Upload the zip, then deploy `ingest.yaml`

### Step A1 — Upload the Lambda zip to the artifacts bucket

The CFN template references the zip at a specific S3 location; that object
must exist before the Lambda resource creates.

URL: <https://us-east-1.console.aws.amazon.com/s3/home?region=us-east-1>

- Click into the bucket **`wistia-artifacts-<account>-us-east-1`**.
- Click **Create folder** → name it **`lambda`** → Create folder.
  (Folders in S3 are a UI convention — they're just key prefixes.)
- Click into the new **`lambda/`** folder.
- Click **Upload** → **Add files** → select your local **`build/lambda.zip`**.
- Confirm:
  - Destination: `s3://wistia-artifacts-<account>-us-east-1/lambda/`
  - The file appears in the file list with size ~15.5 MB.
- Click **Upload** at the bottom → confirmation banner appears.

After upload, the **full key** is `lambda/ingest.zip` — but only if you
uploaded the file named exactly `lambda.zip`. If your local file was
named differently (e.g., `wistia-ingest-2026-05-28.zip`), rename the S3
object back to `ingest.zip` (Object actions → Rename). The CFN template
hardcodes `S3Key: lambda/ingest.zip`.

### Step A2 — Start a new stack in CloudFormation

URL: <https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1>

- Stack list → **Create stack** → **With new resources (standard)**.
- **Prerequisite — Prepare template** → **Choose an existing template**.
- **Specify template** → **Upload a template file** → Choose file →
  select **`infra/cloudformation/ingest.yaml`** from your local repo.
- Click **Next**.

### Step A3 — Specify stack details

- **Stack name**: `wistia-ingest`
  (Must match the PR 2 plan name — downstream PRs assume it.)

- **Parameters**:
  - `Env`: choose **`prod`** (must match what you used for PR 1).
  - `WistiaApiToken`: **paste the Wistia API bearer token**. The field is
    masked because of `NoEcho: true`; the value won't appear in console or
    `describe-stack` output after this.
  - `ScheduleExpression`: leave the default **`cron(0 6 * * ? *)`** (06:00 UTC
    daily). Changing it now still has no effect — the rule deploys DISABLED
    regardless; PR 5 is what flips it on.

Click **Next**.

### Step A4 — Configure stack options

- **Tags**: add the same project tags as PR 1 if you want consistency:
  - Key `project` = Value `wistia`
  - Key `env` = Value `prod`

- **Permissions** → **IAM role**: leave blank (uses your console session's
  permissions).

- **Capabilities** at the bottom: this template creates a *named* IAM role
  (`wistia-prod-lambda-ingest-role`), so AWS requires explicit
  acknowledgement. **Check** the box that says
  **"I acknowledge that AWS CloudFormation might create IAM resources with custom names."**

  (This is what `--capabilities CAPABILITY_NAMED_IAM` accomplishes via CLI.)

- **Stack failure options**: leave on the default ("Roll back all stack
  resources").

Click **Next**.

### Step A5 — Review and submit

Confirm:
- Stack name `wistia-ingest`
- Parameters: `Env=prod`, `WistiaApiToken=****` (hidden), `ScheduleExpression=cron(0 6 * * ? *)`
- IAM acknowledgement is checked
- "Resources" preview lists: `LambdaExecRole`, `IngestFunction`, `IngestLogGroup`, `IngestSchedule`, `IngestSchedulePermission`

Click **Submit**. Status moves to `CREATE_IN_PROGRESS` (yellow). Reaches
`CREATE_COMPLETE` (green) in ~30 seconds. The **Events** tab streams
progress; the **Resources** tab fills in as resources are created.

### Step A6 — Verify outputs

On the stack detail page:

- **Outputs** tab — three entries:
  - `IngestFunctionName` = `wistia-prod-ingest`
  - `IngestFunctionArn` = `arn:aws:lambda:us-east-1:<account>:function:wistia-prod-ingest`
  - `IngestScheduleName` = `wistia-prod-ingest-daily`

  The first two have **Export names** (`wistia-prod-ingest-function`,
  `...-arn`); future PRs can consume them via `!ImportValue`.

- **Resources** tab — five rows with deep-links to each service console.

### Step A7 — Pre-seed the watermark (one-time bootstrap)

**Important** — read this before invoking the Lambda for the first time.

The very first Lambda invocation will run a **full backfill from
`BACKFILL_FLOOR_DATE = 2024-03-01`**, which is 14+ months of paginated event
data. That doesn't fit in the 5-minute Lambda timeout. You'll see a "Task
timed out" error in CloudWatch and nothing will land in S3.

The fix is a one-time pre-seed of the watermark object in S3 to recent
dates, so the first real invoke is incremental.

In the **S3 console**:

- Open `wistia-datalake-<account>-us-east-1` → click **Create folder** →
  name it `state` → Create.
- Inside `state/`, click **Upload** → **Add files** → select a local file
  named `watermark.json` containing:
  ```json
  {
    "events": {
      "gskhw4w4lm": "2026-05-26T00:00:00+00:00",
      "v08dlrgr7v": "2026-05-26T00:00:00+00:00"
    },
    "by_date": {
      "gskhw4w4lm": "2026-05-25",
      "v08dlrgr7v": "2026-05-25"
    }
  }
  ```
  (Adjust the dates to "a few days before the current UTC date." The events
  watermarks should be timezone-aware ISO-8601 with `+00:00`.)

- After upload, the final key is `state/watermark.json`.

Subsequent invocations are incremental and finish in seconds — they update
the watermark in place at the end of each successful run.

---

## Operating PR 2 in the console

These are the operations you'll run regularly regardless of how the stack
got deployed.

### Manually invoke the Lambda

URL: <https://us-east-1.console.aws.amazon.com/lambda/home?region=us-east-1#/functions/wistia-prod-ingest>

- Click the **Test** tab.
- If you don't have a test event yet: **Create new test event** → Event name
  `manual` → Event JSON: `{}` (the handler ignores the payload). **Save**.
- Click **Test** (the orange button next to the event selector).

After a few seconds (a few minutes on the first non-seeded run), you'll see
either:

- **Success**: green status, **Execution result: succeeded**, response
  payload shows the run summary:
  ```json
  {
    "media": {
      "gskhw4w4lm": {"events": 0, "by_date": 4, "media_metadata": 1},
      "v08dlrgr7v": {"events": 0, "by_date": 4, "media_metadata": 1}
    },
    "had_errors": false
  }
  ```
  Below: log output (a tail of the most recent CloudWatch log stream — same
  JSON-line format as local runs).

- **Task timed out**: red status. Means you skipped the bootstrap (Step A7)
  or the watermark drifted way back. Re-seed and retry.

### Read CloudWatch Logs

URL: <https://us-east-1.console.aws.amazon.com/cloudwatch/home?region=us-east-1#logsV2:log-groups/log-group/$252Faws$252Flambda$252Fwistia-prod-ingest>

(Or: CloudWatch console → **Log groups** → click `/aws/lambda/wistia-prod-ingest`.)

- **Retention**: 14 days (pinned by the CFN template; AWS deletes older log
  events automatically). The CFN template provisions this log group
  explicitly so retention is managed.
- **Log streams** — one per Lambda *execution environment* (not per invocation
  — warm invocations share a stream). Latest at the top.
- Click the most recent stream — each line is a JSON object emitted by the
  shared `src.common.logging.JsonFormatter`:
  ```json
  {"ts": "2026-05-28T04:00:05Z", "level": "INFO", "logger": "src.ingestion.pipeline",
   "msg": "ingestion run starting media_ids=['gskhw4w4lm', 'v08dlrgr7v'] ..."}
  ```
- Useful sub-filters at the top of the stream view:
  - `{ $.level = "ERROR" }` — show only error lines.
  - `"fetched page"` — confirm pagination behavior.
  - `"watermark store saved"` — confirm the run completed successfully.

### Inspect the EventBridge schedule rule

URL: <https://us-east-1.console.aws.amazon.com/events/home?region=us-east-1#/rules>

(Or: Amazon EventBridge → **Rules** → click `wistia-prod-ingest-daily`.)

- **State**: should read **Disabled** (red dot). PR 5 flips this on.
- **Schedule**: `cron(0 6 * * ? *)` — fires at 06:00 UTC daily.
- **Targets**: one target = the Lambda function ARN.
- **Monitoring** tab shows invocation metrics (zero entries while disabled).

If you ever need to test the schedule (without enabling it):
- Click **Edit** → **Next** → **Next** → temporarily change state to
  **Enable**, save, wait for one invocation, then disable again. **Don't
  forget to disable** — leaving it on starts daily AWS billing for the
  pipeline.

### Inspect the IAM role

URL: <https://us-east-1.console.aws.amazon.com/iam/home#/roles>

(Or: IAM → **Roles** → click `wistia-prod-lambda-ingest-role`.)

- **Trust relationships** tab — JSON shows `lambda.amazonaws.com` can assume
  this role.
- **Permissions** tab — two policies attached:
  - **`AWSLambdaBasicExecutionRole`** (AWS managed) — grants CloudWatch Logs
    `CreateLogStream` + `PutLogEvents` on any log group. Standard for every
    Lambda.
  - **`data-lake-rw`** (inline) — grants `s3:GetObject`/`PutObject` on
    `arn:aws:s3:::wistia-datalake-<account>-us-east-1/*` and `s3:ListBucket`
    on the bucket itself. Notice it scopes to the data lake only — Lambda
    cannot read or write the artifacts bucket, the foundation bucket policy
    (none today), or any other S3 bucket.

This is the least-privilege configuration. If you ever need the Lambda to
read additional buckets, edit the inline policy (or change the template and
redeploy).

### Inspect S3 for landed data

URL: <https://us-east-1.console.aws.amazon.com/s3/buckets/wistia-datalake-561764228129-us-east-1?region=us-east-1&tab=objects>

(Or: S3 → bucket `wistia-datalake-<account>-us-east-1`.)

After a successful invocation you should see:
- `landing/events/media_id=gskhw4w4lm/ingest_date=2026-05-28/data_*.json`
- `landing/events/media_id=v08dlrgr7v/ingest_date=2026-05-28/data_*.json`
- `landing/by_date/media_id=...` (same pattern)
- `landing/media_metadata/media_id=...` (same pattern)
- `state/watermark.json` (updated after each successful run)

Click into any landing file → **Object actions → Query with S3 Select** →
SQL `SELECT * FROM s3object` shows the JSON envelope:
```json
{
  "ingestion_metadata": {
    "endpoint": "by_date",
    "media_id": "gskhw4w4lm",
    "ingest_timestamp": "2026-05-28T04:00:05+00:00",
    "ingest_date": "2026-05-28",
    "record_count": 4
  },
  "records": [...]
}
```

---

## Updating the Lambda code

When you change `src/ingestion/...` and want the live Lambda to pick it up:

1. Re-run `./infra/scripts/package-lambda.ps1` locally — produces a new
   `build/lambda.zip`.
2. In the S3 console, navigate to `wistia-artifacts-.../lambda/ingest.zip`
   → **Upload** → overwrite the existing object. (Or **Actions → Delete**
   then re-upload — same outcome.)
3. **Important**: the CloudFormation stack does **not** detect that the S3
   object changed (the template still points at the same key). To force
   Lambda to pick up the new zip, do one of:
   - **Console**: Lambda function → **Code** tab → scroll to **Image deploy** /
     **Function code source** → click **Edit** → **Save** (a no-op edit
     triggers a code refresh from the S3 source).
   - **CLI**:
     ```powershell
     aws lambda update-function-code `
         --function-name wistia-prod-ingest `
         --s3-bucket wistia-artifacts-<account>-us-east-1 `
         --s3-key lambda/ingest.zip
     ```
4. Verify by invoking the Lambda and checking the most recent log stream —
   the "INIT_START" line should show a fresh timestamp (cold start with new code).

If you'd rather every PR ship a new key (`lambda/ingest-<sha>.zip`), update
`ingest.yaml`'s `S3Key` parameter at deploy time. Not needed for this project.

---

## Tear down

In reverse-dependency order:

1. **CloudFormation console** → `wistia-ingest` → **Delete** (top-right) →
   confirm. Status moves to `DELETE_IN_PROGRESS` → `DELETE_COMPLETE` in
   ~30 seconds. AWS deletes the Lambda, the IAM role, the log group, the
   EventBridge rule, and the Lambda permission in dependency order.
2. The artifacts bucket still has `lambda/ingest.zip` — leave it (next
   re-deploy uses it) or delete it via S3 console if you're tearing down
   the whole project.

The foundation stack (S3 buckets) is **not** touched by deleting the
ingest stack — those persist with all the data still inside.

---

## Troubleshooting

### Stack create fails with "Source bucket key does not exist"

The Lambda resource references `s3://...lambda/ingest.zip` but you haven't
uploaded the zip yet. Run Step A1 first, then redeploy.

### Lambda invocation times out at 5 minutes

The watermark hasn't been pre-seeded → Lambda is trying a full backfill
from `2024-03-01`. Run Step A7. Then re-invoke.

### Lambda invocation errors with `RuntimeError: WISTIA_API_TOKEN not set`

The token parameter wasn't passed at stack creation, or you redeployed and
didn't supply it again. Stack updates with `NoEcho` parameters require the
value to be re-supplied each time — CFN doesn't keep the old value.

### Lambda invocation errors with S3 `AccessDenied`

The IAM role probably points at the wrong bucket. Open the role's inline
policy and confirm the bucket name in the `Resource` ARN matches the actual
data lake bucket. The `wistia-prod-` prefix on the role and the
`wistia-${Env}-` import in the policy must agree on `Env`.

### "ResourceConflict" on stack create

A previous deploy left an orphan IAM role with the same name (CFN doesn't
clean up IAM roles automatically on `DELETE_FAILED`). In the IAM console,
manually delete `wistia-prod-lambda-ingest-role`, then retry the stack
create.

### EventBridge rule shows "Enabled" but I didn't change anything

Someone (or you, earlier) clicked **Enable** in the console. That's a drift
from CFN — the template specifies `State: DISABLED`. To revert: edit the
rule → set State to **Disabled** → save. Or run any subsequent
`aws cloudformation deploy` on the ingest stack and CFN will reconcile it
back to DISABLED.

---

## Related references

- [`infra/cloudformation/ingest.yaml`](../../infra/cloudformation/ingest.yaml) — the source template this guide reproduces
- [`infra/scripts/package-lambda.ps1`](../../infra/scripts/package-lambda.ps1) — the zip builder this guide assumes you've already run
- [`infra/README.md`](../../infra/README.md) — CLI-based deploy + tear-down
- [`01-foundation.md`](01-foundation.md) — PR 1's console walkthrough (prerequisite)
