# PR 5 — Production Run + Close-out: AWS Console Walkthrough

> Final slice of Phase 3. Web-UI version of what `monitoring.yaml`
> deploys + the schedule changes to `ingest.yaml` and `transforms.yaml`,
> plus the day-by-day operations (read alarms, watch the daily run,
> capture metrics, tear down) for the 7-day production window.
>
> **Outcome:** a fully automated daily pipeline. EventBridge fires the
> Lambda at 06:00 UTC; a Glue SCHEDULED trigger fires the workflow at
> 06:15 UTC; CloudWatch alarms + EventBridge rules notify the
> `vitordverissimo@gmail.com` SNS subscription on any failure; the
> dashboard reads each day's fresh Gold.

---

## Prerequisites

1. **PRs 1 + 2 + 3 + 4 already deployed.** All four stacks should be in
   `CREATE_COMPLETE` / `UPDATE_COMPLETE` and the dashboard URL should
   serve real Gold data (Session 11 backfilled it).
2. **Region locked to N. Virginia (us-east-1).** Top-right region picker
   on every console page.
3. **AWS Budgets alarm** at $30/month (already configured during
   pre-flight — confirm at
   <https://us-east-1.console.aws.amazon.com/billing/home?region=us-east-1#/budgets>).

---

## Phase A — Deploy `monitoring.yaml`

### Step A1 — Upload + deploy via CloudFormation

URL: <https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1>

- Stack list → **Create stack** → **With new resources (standard)**.
- **Upload a template file** → select
  `infra/cloudformation/monitoring.yaml` from the repo.
- **Stack name**: `wistia-monitoring`.
- **Parameters**:
  - `Env`: **`prod`** (matches the other stacks).
  - `AlertEmail`: **`vitordverissimo@gmail.com`** (override if you want
    alerts elsewhere).
- **Capabilities**: this template doesn't create named IAM resources;
  no acknowledgement checkbox needed.
- **Submit**.

Stack reaches `CREATE_COMPLETE` in ~30 seconds (no slow resources here).

### Step A2 — Confirm the SNS email subscription

**This step is mandatory.** Without it, the SNS topic exists but
silently drops every event — no emails will ever arrive.

1. Check inbox at `vitordverissimo@gmail.com` for an email titled
   **"AWS Notification — Subscription Confirmation"** from
   `no-reply@sns.amazonaws.com`. AWS sends it within a minute of the
   stack reaching `CREATE_COMPLETE`.
2. Click the **Confirm subscription** link inside.
3. Confirm in the AWS console: **SNS → Topics → `wistia-prod-alerts` →
   Subscriptions tab** → status should flip from `PendingConfirmation`
   to `Confirmed`.

> **Email tends to land in spam for this AWS account** (Budgets emails
> also landed there). Check the spam folder if it's not in the inbox.

URL: <https://us-east-1.console.aws.amazon.com/sns/v3/home?region=us-east-1#/topic/arn:aws:sns:us-east-1:561764228129:wistia-prod-alerts>

### Step A3 — Verify the Lambda error alarm

URL: <https://us-east-1.console.aws.amazon.com/cloudwatch/home?region=us-east-1#alarmsV2:>

- One alarm: **`wistia-prod-ingest-errors`**.
- State: should be `OK` (no errors in the last 5 minutes).
- Click in → **Actions** tab → confirm `In ALARM: <SNS topic ARN>` and
  `OK: <SNS topic ARN>` are both wired.

### Step A4 — Verify the Glue failure EventBridge rule

URL: <https://us-east-1.console.aws.amazon.com/events/home?region=us-east-1#/rules>

- Rule **`wistia-prod-glue-job-failures`** should exist and be `Enabled`.
- **Event pattern** tab shows the JSON pattern — sanity-check it covers
  `state: [FAILED, TIMEOUT, STOPPED]` and the three job names.
- **Targets** tab shows 1 target: the SNS topic ARN.

---

## Phase B — Activate the daily schedules

Two stack updates to flip from "deploys exist but are paused" to "runs
every day at 06:00 + 06:15 UTC".

### Step B1 — Re-deploy `wistia-ingest`

The ingest template now has `State: ENABLED` on the EventBridge rule.

```powershell
aws cloudformation deploy `
  --stack-name wistia-ingest `
  --template-file infra/cloudformation/ingest.yaml `
  --capabilities CAPABILITY_NAMED_IAM `
  --parameter-overrides Env=prod WistiaApiToken=$Token `
  --region us-east-1
```

Status moves from `UPDATE_IN_PROGRESS` → `UPDATE_COMPLETE` in ~30s.

Confirm in the console: **EventBridge → Rules → `wistia-prod-ingest-daily`**
→ **Enabled**.

### Step B2 — Re-deploy `wistia-transforms` (trigger swap)

The transforms template now has a `ScheduledStartTrigger` resource
replacing the old `StartTrigger` (which was ON_DEMAND). CFN deletes the
old trigger by its known name (`wistia-prod-on-demand-start`) and
creates the new one (`wistia-prod-scheduled-start`).

> This swap is the lesson from `troubleshooting/known_issues.md` #12:
> Glue triggers can't have their `Type` changed in place, and CFN can't
> replace a custom-named resource without renaming it.

```powershell
aws cloudformation deploy `
  --stack-name wistia-transforms `
  --template-file infra/cloudformation/transforms.yaml `
  --capabilities CAPABILITY_NAMED_IAM `
  --parameter-overrides Env=prod `
  --region us-east-1
```

Confirm in the console: **Glue Studio → Workflows →
`wistia-prod-transforms` → Graph** → the starting node is now
**`wistia-prod-scheduled-start (SCHEDULED)`** instead of the old
on-demand one, and the schedule expression matches
`cron(15 6 * * ? *)`.

The conditional `BronzeToSilver` and `SilverToGold` triggers are
unchanged.

---

## Operating the 7-day production window

### Daily 1-minute check

| Where | What you're looking for |
| --- | --- |
| **CloudWatch → Alarms** | `wistia-prod-ingest-errors` state = `OK`. If `In alarm`, click in and read the metric chart. |
| **EventBridge → Rules → wistia-prod-ingest-daily** | Right side: **Metrics → Invocations** chart shows one tick per day. |
| **Lambda → wistia-prod-ingest → Monitor → Logs** | Latest log stream timestamp from today; no exceptions. |
| **Glue Studio → Workflows → wistia-prod-transforms → Run history** | Today's run row, status `Completed`. Statistics tab shows 3 SucceededActions. |
| **S3 → wistia-datalake-… → landing/{events,by_date}/** | New ingest-date partitions for today. |
| **The dashboard URL** | Last-7-days table includes today's row. |

Add a daily entry to `context_vault/status/session_log.md` (one line:
`Day N — all green` or `Day N — Lambda errored at 06:00 UTC; cause was X`).

### Reading a failure alert

The email from SNS includes the failing component:

- **Lambda alarm email** ("Threshold Crossed: ..."): jump straight to
  CloudWatch Logs `/aws/lambda/wistia-prod-ingest` and read the most
  recent stream.
- **Glue job failure email** ("Wistia Glue job wistia-prod-X entered
  state FAILED..."): use the **jobRunId** in the email to jump to
  `/aws-glue/jobs/output` or `/aws-glue/jobs/error` and filter by that
  ID. The `severity` and `message` fields in the email usually surface
  the root cause directly.

### Manual workflow re-run (recovery)

If a Glue job fails mid-workflow and you fix the underlying issue, the
workflow doesn't auto-retry. Re-run manually:

> ⚠ **The workflow no longer has an ON_DEMAND starting trigger** as of
> PR 5 — `aws glue start-workflow-run` will return success but fire
> zero jobs (known issue #11). And `start-job-run` runs the job
> **outside** any workflow run, so the conditional triggers don't
> observe its state change and won't chain Silver and Gold (known
> issue #16). Recovery options:
>
> 1. **Wait for the next cron tick** (06:15 UTC daily) — simplest;
>    no manual action needed.
> 2. **Run each job manually in sequence** with `aws glue start-job-run
>    --job-name wistia-prod-bronze`, wait for SUCCEEDED, then the same
>    for Silver, then Gold. Doable but tedious for ad-hoc recovery.
> 3. **Temporarily restore an ON_DEMAND trigger** via the console
>    (Glue Studio → Workflows → `wistia-prod-transforms` → Add
>    trigger → ON_DEMAND), `start-workflow-run`, then delete the
>    trigger. Creates drift; reconcile by re-deploying
>    `transforms.yaml` after.

---

## Day 7 — close-out

### Capture metrics

Run from local:

```powershell
# Total daily invocations of the Lambda over the last 7 days
aws cloudwatch get-metric-statistics `
  --namespace AWS/Lambda --metric-name Invocations `
  --dimensions Name=FunctionName,Value=wistia-prod-ingest `
  --start-time (Get-Date).AddDays(-7).ToUniversalTime().ToString("o") `
  --end-time   (Get-Date).ToUniversalTime().ToString("o") `
  --period 86400 --statistics Sum --region us-east-1

# Glue job-run counts for each job (succeeded vs failed)
foreach ($j in @("bronze","silver","gold")) {
  aws glue get-job-runs --job-name "wistia-prod-$j" `
    --region us-east-1 --max-items 14 `
    --query 'JobRuns[].{StartedOn:StartedOn,State:JobRunState,Runtime:ExecutionTime}' `
    --output table
}

# Spend for the period
aws ce get-cost-and-usage `
  --time-period "Start=$((Get-Date).AddDays(-7).ToString('yyyy-MM-dd')),End=$((Get-Date).ToString('yyyy-MM-dd'))" `
  --granularity DAILY --metrics UnblendedCost `
  --group-by Type=DIMENSION,Key=SERVICE `
  --region us-east-1
```

Record findings in `status/phase3_plan.md` § "Findings" section.

### Tear down (default plan)

```powershell
./infra/scripts/teardown.ps1 -WhatIf      # preview
./infra/scripts/teardown.ps1              # confirm prompt, then live
```

The script:

1. Empties the ECR repo `wistia-prod-dashboard` (batch-delete-image).
2. Empties both S3 buckets recursively.
3. Deletes the 5 CloudFormation stacks in reverse dependency order,
   waiting for each to fully disappear before moving to the next.

Total time: ~5-10 minutes. Daily run rate after: **~$0/day**.

### Keep running (alternative)

If you skip the tear-down, the pipeline keeps running on the daily
schedule indefinitely. **~$25/month** (mostly the ALB hours +
ECS Fargate task hours). The Budgets alarm at $30/month will catch any
unexpected spend.

You can also do a hybrid: tear down everything except `wistia-foundation`
(keeps the data lake bucket so the historical Gold survives), then redeploy
the rest later. Run the script through stack 4 only (manually skip
foundation) for that.

---

## What you should be able to point at after PR 5

1. **CloudFormation → wistia-monitoring** — `CREATE_COMPLETE`. 4 resources
   (SNS topic + topic policy + CloudWatch alarm + EventBridge rule).
2. **SNS → wistia-prod-alerts → Subscriptions** — 1 subscription,
   `Status: Confirmed`.
3. **EventBridge → wistia-prod-ingest-daily** — `Enabled`.
4. **Glue Studio → wistia-prod-transforms → Graph** — starting trigger
   is the new SCHEDULED one; no ON_DEMAND trigger remains.
5. **CloudWatch → wistia-prod-ingest-errors** — `OK` state.
6. **CloudWatch → /aws/lambda/wistia-prod-ingest** — one log stream per
   day after the schedule fires.
7. **The dashboard** — updates daily with the latest by_date numbers.
