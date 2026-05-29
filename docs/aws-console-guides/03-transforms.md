# PR 3 — Transforms (Glue Workflow): AWS Console Walkthrough

> A pure web-UI version of what `infra/cloudformation/transforms.yaml`
> deploys, plus the post-deploy operations (run the workflow, inspect job
> logs, read the DAG visualization, redeploy a code change) you'll
> routinely run in the console.
>
> **Outcome:** three AWS Glue 5.0 ETL jobs in `us-east-1` —
> `wistia-prod-bronze`, `-silver`, `-gold` — wired into a single Glue
> Workflow `wistia-prod-transforms` with conditional triggers chaining
> them in order. The starting trigger is **ON_DEMAND**
> (`wistia-prod-on-demand-start`) so `start-workflow-run` works for manual
> verification. PR 5 replaces this with a SCHEDULED trigger of a different
> name for the 7-day production cron — a Glue workflow can only have one
> starting trigger, so this is either-or.
>
> **Two paths** are documented below:
> - **Path A** (recommended): upload the transforms zip + 3 entry-point
>   scripts to S3, then upload `transforms.yaml` to the CloudFormation
>   console. Same outcome as the CLI deploy.
> - **Operating section**: how to run the workflow manually from the
>   console, read the DAG, drill into a failed job, view CloudWatch logs.

---

## Prerequisites

1. **PRs 1 + 2 already deployed** — the `wistia-foundation` stack must exist
   (transforms imports its bucket exports), and the data lake bucket must
   have **at least one successful ingest run's data** under `landing/`.
   The transforms read from `landing/` and would produce empty Gold tables
   otherwise (which is technically a valid outcome, but you won't see
   anything interesting to verify).
2. **Region locked to N. Virginia (us-east-1)**.
3. **A built transforms zip** — `build/transforms.zip` produced by
   `infra/scripts/package-transforms.ps1`. Tiny (~11 KB) because Glue 5.0
   provides Spark and Python 3.11 at runtime; we only bundle our own
   pure-Python code.
4. The three **Glue entry-point scripts**:
   - `src/transforms/glue/bronze_job.py`
   - `src/transforms/glue/silver_job.py`
   - `src/transforms/glue/gold_job.py`

If you don't have the zip + scripts, run:

```powershell
./infra/scripts/package-transforms.ps1
```

(Without `-Upload` it just builds locally — Path A's S3 step uploads them
through the console.)

---

## Path A — Upload artifacts, then deploy `transforms.yaml`

### Step A1 — Upload the transforms zip + 3 Glue scripts to the artifacts bucket

URL: <https://us-east-1.console.aws.amazon.com/s3/home?region=us-east-1>

- Click into the bucket **`wistia-artifacts-<account>-us-east-1`**.
- Click **Create folder** → name it **`glue`** → Create.
- Click into the new `glue/` folder.
- Click **Upload** → **Add files** → select all four files:
  - `build/transforms.zip`
  - `src/transforms/glue/bronze_job.py`
  - `src/transforms/glue/silver_job.py`
  - `src/transforms/glue/gold_job.py`
- Click **Upload**.

The final keys should be:
- `glue/transforms.zip`
- `glue/bronze_job.py`
- `glue/silver_job.py`
- `glue/gold_job.py`

(The CFN template hardcodes these exact keys.)

### Step A2 — Start a new stack in CloudFormation

URL: <https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1>

- Stack list → **Create stack** → **With new resources (standard)**.
- **Choose an existing template** → **Upload a template file** → select
  **`infra/cloudformation/transforms.yaml`** from your local repo.
- Click **Next**.

### Step A3 — Specify stack details

- **Stack name**: `wistia-transforms`
- **Parameters**:
  - `Env`: **`prod`** (must match the foundation stack).
  - `GlueVersion`: leave default **`5.0`** (matches our local PySpark
    3.5.x + Python 3.11).
  - `WorkerType`: leave default **`G.1X`** (1 DPU = 4 vCPU / 16 GB; the
    minimum for `glueetl` jobs — `G.025X` is streaming-only).
  - `NumberOfWorkers`: leave default **`2`** (plenty for our small data).
  - `ScheduleExpression`: leave default **`cron(15 6 * * ? *)`** (06:15 UTC
    daily, 15 minutes after the Lambda ingest). Not used in PR 3 (entry
    trigger is ON_DEMAND); kept for PR 5 which replaces the trigger with
    a SCHEDULED one using this cron.

Click **Next**.

### Step A4 — Configure stack options

- **Tags** (optional): `project=wistia`, `env=prod` to match the other
  stacks.
- **Capabilities** at the bottom: this template creates a *named* IAM role
  (`wistia-prod-glue-service-role`), so check the
  **"I acknowledge that AWS CloudFormation might create IAM resources with custom names."** box.

Click **Next** → **Submit**.

### Step A5 — Wait for `CREATE_COMPLETE`

Status moves to `CREATE_IN_PROGRESS` (yellow). Reaches `CREATE_COMPLETE`
(green) in ~1 minute. The **Events** tab shows resources being created in
dependency order:
- `GlueServiceRole` → `TransformsWorkflow` → 3 Glue jobs (parallel)
- Then the 3 triggers (parallel)

**Resources** tab lists 8 resources total:
- 1 IAM role
- 1 Workflow
- 3 Jobs (BronzeJob, SilverJob, GoldJob)
- 3 Triggers (StartTrigger, BronzeToSilverTrigger, SilverToGoldTrigger)

---

## Operating PR 3 in the console

### View the workflow DAG visually

URL: <https://us-east-1.console.aws.amazon.com/gluestudio/home?region=us-east-1#/etl-jobs/workflows>

(Or: AWS Glue → **ETL jobs** → **Workflows** in the left nav → click `wistia-prod-transforms`.)

- **Graph** tab shows the DAG as a diagram:
  - Top node: `wistia-prod-on-demand-start` (trigger, ACTIVATED — fires on `start-workflow-run`)
  - Below: `wistia-prod-bronze` (job)
  - `wistia-prod-bronze-to-silver` (trigger, ACTIVATED)
  - `wistia-prod-silver` (job)
  - `wistia-prod-silver-to-gold` (trigger, ACTIVATED)
  - `wistia-prod-gold` (job)
- Click any node to see its details + recent runs.
- The graph is the same view a reader of `phase3_plan.md` § "Glue
  Workflow" expects to see.

### Run the workflow manually

In the workflow detail page (Glue Studio → Workflows → `wistia-prod-transforms`):

- Click **Actions → Run** (top-right).
- A modal pops up to confirm; click **Run**.
- A new row appears under **History** with status `RUNNING`.

Internally this issues a `StartWorkflowRun` API call. The workflow run is
visible under **Run history**, and the Glue scheduler kicks off the Bronze
job. The conditional triggers fire when each job succeeds, chaining Silver
and Gold.

**Total runtime**: ~5-10 minutes for our small data. Glue has a ~30-60
second cold-start per job (provisioning workers) regardless of the work
size — that dominates cost and runtime for small jobs.

(There is also a CLI path: `aws glue start-workflow-run --name wistia-prod-transforms`.)

### Watch a workflow run progress

Click into a `RUNNING` workflow run row:

- **History** tab shows the run's status, start time, statistics.
- **Graph** tab shows the same DAG with each job node colored by status:
  - Gray = not started yet
  - Yellow / blue = running
  - Green = succeeded
  - Red = failed
- Click a running job's node → **Job runs** → see the underlying
  `JobRunState` for the specific run ID.

You can refresh the page every minute or so — Glue Studio doesn't poll
live.

### Read a Glue job's CloudWatch logs

The fastest path from a failed job to its log lines:

1. Workflow detail → click the failed job node → **Job runs** → click the
   most recent run ID → **Output logs** (or **Error logs**).
2. This deep-links to CloudWatch Logs at the right log stream.

Glue's logs are noisier than Lambda's — each job emits:
- **Driver logs** (`/aws-glue/jobs/output`) — the Python script's stdout
  including our JSON-formatted log lines.
- **Executor logs** (`/aws-glue/jobs/error` for stderr) — Spark JVM logs.

Useful sub-filters in the CloudWatch view at the top of the stream:
- `{ $.level = "ERROR" }` — only error-level structured logs.
- `"bronze counts"` — find the per-endpoint row counts our script prints.

### Inspect a Glue job's configuration

URL: <https://us-east-1.console.aws.amazon.com/gluestudio/home?region=us-east-1#/etl-jobs>

Click a job (e.g., `wistia-prod-bronze`) → **Job details** tab:

- **Type**: Spark
- **Glue version**: Glue 5.0 (Spark 3.5.4, Python 3.11)
- **Language**: Python 3
- **Worker type**: G.1X (1 DPU = 4 vCPU / 16 GB)
- **Number of workers**: 2 (total 2 DPU)
- **Timeout**: 30 minutes
- **Number of retries**: 1
- **IAM role**: `wistia-prod-glue-service-role`
- **Script path**: `s3://wistia-artifacts-.../glue/bronze_job.py`
- **Python library path**: `s3://wistia-artifacts-.../glue/transforms.zip`
  (this is `--extra-py-files` — Glue adds it to PYTHONPATH inside each worker).
- **Job parameters**:
  - `--DATALAKE_BUCKET`: the data lake bucket name (used by the script to
    build `s3://` paths)
  - `--enable-continuous-cloudwatch-log`: `true` (verbose logging)
  - `--enable-metrics`: `true` (Glue worker metrics in CloudWatch)
  - `--job-language`: `python`

### Inspect the IAM service role

URL: <https://us-east-1.console.aws.amazon.com/iam/home#/roles>

Click `wistia-prod-glue-service-role` → **Permissions** tab — three
policies:

- **`AWSGlueServiceRole`** (AWS managed) — Glue's own logs, CloudWatch
  metrics, and access to internal Glue endpoints.
- **`data-lake-rw`** (inline) — `s3:GetObject` / `PutObject` /
  `DeleteObject` on `wistia-datalake-.../*` and `s3:ListBucket` on the
  bucket itself.
- **`artifacts-read`** (inline) — `s3:GetObject` on
  `wistia-artifacts-.../glue/*` and `s3:ListBucket` on the bucket. This is
  how Glue pulls the entry-point script and `transforms.zip` at job start.

### Spot-check S3 after a successful run

After a successful workflow run, S3 should have new prefixes under the
data lake bucket:

- `bronze/events/`
- `bronze/by_date/`
- `bronze/media_metadata/`
- `silver/events/`, `silver/by_date/`, `silver/media_metadata/`
- `gold/dim_media/`, `gold/dim_visitor/`, `gold/fact_media_engagement/`

Each is a directory of Parquet files (`part-*.snappy.parquet`). Glue
overwrites each layer on every run.

To peek at row counts without spinning up a separate query environment,
use **S3 → Object → Object actions → Query with S3 Select**:

- Format: **Apache Parquet**
- SQL: `SELECT COUNT(*) FROM s3object`

(For an interactive Parquet browsing experience, Athena or your local
Streamlit dashboard pointed at S3 are better fits — out of scope for this
guide.)

---

## Updating the transforms code

When you change `src/transforms/*.py` (any of the pure transforms or
helpers):

1. Re-run `./infra/scripts/package-transforms.ps1 -Upload` locally. This
   re-builds `build/transforms.zip` and overwrites the S3 object at
   `s3://wistia-artifacts-.../glue/transforms.zip`.
2. **No CFN or job redeployment needed.** Glue fetches the zip at job
   start — each new job run picks up the latest version automatically.
   This is different from Lambda, which caches the code zip and needs an
   explicit `update-function-code`.

When you change a Glue entry-point script (`src/transforms/glue/*_job.py`):

1. Same `./infra/scripts/package-transforms.ps1 -Upload` re-uploads the
   three scripts.
2. Glue picks up the new script on the next job run.

---

## Tear down

In reverse-dependency order:

1. **CloudFormation console** → `wistia-transforms` → **Delete**.
   Status moves to `DELETE_IN_PROGRESS` → `DELETE_COMPLETE` in ~30 seconds.
2. Glue stops/removes the 3 jobs, the workflow, the triggers, and the IAM
   role.
3. The artifacts bucket still has `glue/transforms.zip` + the 3 scripts —
   leave them or delete via the S3 console.
4. **The data in `bronze/`, `silver/`, `gold/` of the data lake bucket
   persists** — Glue doesn't delete S3 data on stack delete. If you want
   to empty those layers, S3 → bucket → select prefix → **Delete**.

---

## Troubleshooting

### `StartJobRun` returns `ConcurrentRunsExceededException`

Each job has `MaxConcurrentRuns: 1` (in `ExecutionProperty`). The previous
run is still active. Wait for it to finish, or check the **Job runs** tab
to see what's pending.

### Workflow run shows `COMPLETED` with `SucceededActions: 0`

The workflow ran but no triggers fired any jobs. Most common causes:
- The starting trigger was deleted or its type changed. Confirm via the
  Glue console → Workflows → `wistia-prod-transforms` → **Graph** that
  the ON_DEMAND trigger (`wistia-prod-on-demand-start`) is present.
- An upstream job is missing or renamed.

### Bronze job fails with `Path does not exist: s3://.../landing/events`

PR 2's Lambda hasn't been run yet (or the watermark wasn't pre-seeded and
the Lambda timed out without writing). Run the Lambda first per the PR 2
guide.

### Silver succeeds but Bronze didn't fire it

Did you start `wistia-prod-silver` directly via `start-job-run`? Conditional
triggers fire on job events but only within an active workflow run
context. To chain through the workflow, start the workflow (via
`start-workflow-run`) or start the Bronze job manually from within the
workflow run view.

### Glue job fails immediately with `ModuleNotFoundError: src`

The `--extra-py-files` parameter points at a missing or wrong S3 key.
Confirm `s3://wistia-artifacts-.../glue/transforms.zip` exists and was
re-uploaded after the last code change.

### Glue job fails with `botocore.exceptions.ClientError: AccessDenied`

The Glue service role's IAM policy doesn't grant the necessary S3
permissions. Check:
- `data-lake-rw` inline policy covers `Get/PutObject` on
  `<datalake-bucket>/*` and `ListBucket` on the bucket.
- `artifacts-read` covers `GetObject` on `<artifacts-bucket>/glue/*`.

### Job timeout (30 min) hit on Gold

For a 7-day production run our Gold layer stays tiny (<30K rows). If you're
back-filling and hit timeout, either:
- Bump `Timeout` in `transforms.yaml`'s `GoldJob.Properties`, or
- Bump `NumberOfWorkers` from 2 → 4 or upgrade `WorkerType` to G.2X.

### `start-workflow-run` doesn't actually fire Bronze

If the workflow's entry trigger is `SCHEDULED`-only, `start-workflow-run`
creates a run record but doesn't fire the trigger — SCHEDULED triggers
only fire on their cron. PR 3 uses an ON_DEMAND trigger
(`wistia-prod-on-demand-start`) specifically so manual workflow runs
work. If you've already deployed PR 5 (which replaces the trigger with
SCHEDULED), you can't manually start the workflow this way — flip the
SCHEDULED trigger to ACTIVATED and wait for the next cron tick, or
temporarily redeploy PR 3's template to swap the trigger back to
ON_DEMAND.

---

## Related references

- [`infra/cloudformation/transforms.yaml`](../../infra/cloudformation/transforms.yaml) — the source template
- [`infra/scripts/package-transforms.ps1`](../../infra/scripts/package-transforms.ps1) — the zip builder
- [`infra/README.md`](../../infra/README.md) — CLI-based deploy + tear-down
- [`02-ingest.md`](02-ingest.md) — PR 2's console walkthrough (prerequisite — Bronze reads what Lambda wrote)
- [`01-foundation.md`](01-foundation.md) — PR 1's console walkthrough (prerequisite — S3 buckets)
