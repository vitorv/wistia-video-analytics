# PR 4 — Dashboard (ECR + ECS Fargate + ALB): AWS Console Walkthrough

> A pure web-UI version of what `infra/cloudformation/dashboard.yaml`
> deploys, plus the post-deploy operations (push a new image, force a
> rollout, read container logs, inspect target health) you'll routinely
> run in the console.
>
> **Outcome:** a public ALB DNS name in `us-east-1` that serves the
> Streamlit dashboard from an ECS Fargate task. The container reads the
> Gold star schema directly from `s3://wistia-datalake-.../gold/` via
> `pandas` + `s3fs` — no Spark.
>
> **Two-phase deploy** (chicken-and-egg with ECR):
>
> 1. Deploy with `DeployService=false` → ECR repo, cluster, ALB, task def,
>    log group, IAM. No Service yet — the image doesn't exist.
> 2. Build + push the Docker image to the new ECR repo.
> 3. Re-deploy with `DeployService=true` → adds the ECS Service which
>    pulls the image, registers with the ALB target group, and goes live.

---

## Prerequisites

1. **PRs 1 + 2 + 3 already deployed.** The dashboard `Fn::ImportValue`s
   the data lake bucket from the foundation stack; the data only renders
   meaningfully once the Glue workflow from PR 3 has populated Gold.
2. **Region locked to N. Virginia (us-east-1).** Top-right region picker
   on every console page.
3. **Docker Desktop installed locally**, with the engine running. Verify
   with `docker version` (the `Server` block must be reachable, not just
   the `Client`).
4. **AWS CLI authenticated** as a user with ECR push permissions
   (`AdministratorAccess` is fine for this project).

---

## Step 0 — Discover your default VPC + public subnet IDs

The CFN template needs both as deploy-time parameters.

URL: <https://us-east-1.console.aws.amazon.com/vpcconsole/home?region=us-east-1#vpcs:>

- Click the **VPC ID** with **Default VPC = Yes**.
- Copy the **VPC ID** (e.g. `vpc-0abc123def...`).

Left nav → **Subnets**.

- Filter by your default VPC.
- The default VPC has one public subnet per AZ (typically 3–6 in
  `us-east-1`). Copy **all** their IDs as a comma-separated list, e.g.
  `subnet-aaa,subnet-bbb,subnet-ccc`.
- For the ALB, two AZs is the minimum; using all of them costs nothing
  extra and improves redundancy.

(CLI alternative is documented in the parameter description inside the
template itself.)

---

## Phase 1 — Initial deploy (`DeployService=false`)

### Step 1.1 — Start a new stack in CloudFormation

URL: <https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1>

- Stack list → **Create stack** → **With new resources (standard)**.
- **Prepare template**: **Choose an existing template** → **Upload a
  template file** → select `infra/cloudformation/dashboard.yaml` from your
  local repo.
- Click **Next**.

### Step 1.2 — Specify stack details

- **Stack name**: `wistia-dashboard`
- **Parameters**:
  - `Env`: **`prod`** (must match the foundation stack).
  - `DeployService`: **`false`** (no image in ECR yet).
  - `DefaultVpcId`: pick your default VPC from the drop-down (the
    `AWS::EC2::VPC::Id` parameter type populates a picker).
  - `DefaultPublicSubnetIds`: pick **at least two** of your default VPC's
    public subnets from the drop-down. Selecting all of them is fine.
  - `ContainerCpu` / `ContainerMemory`: leave defaults (`512` / `1024` =
    0.5 vCPU + 1 GB).
  - `ImageTag`: leave default **`latest`**.

Click **Next**.

### Step 1.3 — Configure stack options

- **Tags** (optional): add `project=wistia`, `env=prod` to match the
  other stacks.
- **Capabilities** at the bottom: this template creates *named* IAM roles
  (`wistia-prod-dashboard-exec-role`, `-task-role`) so check the
  **"I acknowledge that AWS CloudFormation might create IAM resources with custom names."** box.

Click **Next** → **Submit**.

### Step 1.4 — Wait for `CREATE_COMPLETE`

Status moves through `CREATE_IN_PROGRESS` (yellow) to `CREATE_COMPLETE`
(green) in ~3-5 minutes. The ALB provisioning is the slow step.

**Resources** tab lists 12 resources for Phase 1 (the 13th, `Service`, lands
in Phase 3):
- 1 ECR repository
- 1 ECS cluster
- 1 CloudWatch log group
- 2 IAM roles (exec + task)
- 2 security groups (ALB + ECS) + 1 SG ingress rule
- 1 ALB + 1 target group + 1 listener
- 1 ECS task definition

**No `Service` resource yet** — that's gated by the `ServiceEnabled`
condition (`DeployService=false`).

### Step 1.5 — Sanity-check the empty ECR repo

URL: <https://us-east-1.console.aws.amazon.com/ecr/repositories?region=us-east-1>

- Click into **`wistia-prod-dashboard`**.
- The **Images** tab is empty. That's expected — you push next.
- Copy the **URI** at the top of the page (e.g.
  `561764228129.dkr.ecr.us-east-1.amazonaws.com/wistia-prod-dashboard`).
  The build script discovers this automatically; it's still useful for a
  manual `docker push` if you ever bypass the script.

---

## Phase 2 — Build + push the image

From your local repo:

```powershell
./infra/scripts/build-dashboard-image.ps1
```

The script:

1. Confirms Docker Desktop is running.
2. Discovers your AWS account ID + ECR repo URI.
3. Reads `git rev-parse --short HEAD` for the immutable tag.
4. `aws ecr get-login-password | docker login` against the ECR registry.
5. `docker build -t <uri>:latest -t <uri>:<sha> .`
6. `docker push` both tags.

First build is ~3-4 minutes (pulls the `python:3.11-slim` base + installs
deps). Subsequent rebuilds are ~30 s if only code changed (Docker reuses
the deps layer).

### Verify in the ECR console

Refresh **ECR → Repositories → wistia-prod-dashboard → Images**:

- Two rows should appear: `latest` and `<git-sha>` (e.g. `a3f1b2c`).
- Each has an **Image scan status** that turns from `Scanning` to
  `Complete` after a minute. Click the scan to see CVE findings (none
  blocking for `python:3.11-slim`).

---

## Phase 3 — Turn on the Service (`DeployService=true`)

### Step 3.1 — Update the stack

URL: <https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1>

- Click into the **`wistia-dashboard`** stack.
- Top-right **Update** → **Use existing template** → **Next**.
- **Parameters**: change **`DeployService`** from `false` to **`true`**.
  Leave everything else.
- **Next** → **Next** → re-check the IAM capability box → **Submit**.

### Step 3.2 — Watch the Service come up

Stack status moves to `UPDATE_IN_PROGRESS`. The new `Service` resource is
created and ECS starts the first task. Total time: 2-3 minutes.

Stack reaches `UPDATE_COMPLETE` once:
1. The task transitions from `PENDING` → `RUNNING`.
2. The ALB target group health check passes twice (the
   `HealthyThresholdCount`).

### Step 3.3 — Verify the task is healthy

URL: <https://us-east-1.console.aws.amazon.com/ecs/v2/clusters/wistia-prod-dashboard/services?region=us-east-1>

- Click into the **`wistia-prod-dashboard`** service.
- **Tasks** tab should show 1 task with status `Running`.
- **Health and metrics** tab → **Target group health** → status `Healthy`.

(If unhealthy, jump to the **Troubleshooting** section.)

### Step 3.4 — Open the dashboard

Two ways to get the URL:

- **Stack Outputs**: CloudFormation → `wistia-dashboard` → **Outputs** tab
  → `DashboardUrl` (e.g. `http://wistia-prod-dashboard-1234567890.us-east-1.elb.amazonaws.com`).
- **EC2 Load Balancers**: <https://us-east-1.console.aws.amazon.com/ec2/home?region=us-east-1#LoadBalancers:>
  → `wistia-prod-dashboard` → copy **DNS name**, prefix with `http://`.

Paste into a browser. The Streamlit dashboard should render with:
- Four KPI cards at top.
- Last-7-days, last-30-days, engagement-by-media tables.
- A daily-trends line chart.
- Monthly engagement + top visitors tables.

The footer caption should read `Reading Gold from
s3://wistia-datalake-<account>-us-east-1/gold` — confirms the env var is
plumbed through.

---

## Operating the dashboard in the console

### Push a new image and roll out

```powershell
./infra/scripts/build-dashboard-image.ps1

# Force ECS to pull :latest again (the tag moved):
aws ecs update-service `
  --cluster wistia-prod-dashboard `
  --service wistia-prod-dashboard `
  --force-new-deployment `
  --region us-east-1
```

ECS does a rolling deploy with `MinimumHealthyPercent: 100` /
`MaximumPercent: 200` — it starts a new task, waits for it to register
healthy, then stops the old one. **Zero downtime.** Watch progress under
the service's **Events** tab.

### Read container logs

URL: <https://us-east-1.console.aws.amazon.com/cloudwatch/home?region=us-east-1#logsV2:log-groups>

- Log group: `/ecs/wistia-prod-dashboard`.
- Each task launch creates a new log stream
  (`dashboard/dashboard/<task-id>`).
- Streamlit's startup banner appears within a few seconds of task launch;
  request logs follow as you hit the ALB.

### Inspect target health

URL: <https://us-east-1.console.aws.amazon.com/ec2/home?region=us-east-1#TargetGroups:>

- Click `wistia-prod-dashboard` → **Targets** tab.
- Each registered task IP appears as a row. Status should be `healthy`.
- During a rolling deploy you see 2 rows briefly (old + new).

### Rollback to a previous image

The build script pushes a `:<git-sha>` tag for exactly this. To roll back:

- **CloudFormation → wistia-dashboard → Update** → set `ImageTag` to the
  prior SHA (e.g. `a3f1b2c`) → submit.
- ECS generates a new task definition revision pointing at the old image,
  then rolls the service onto it.

(For a panic-rollback that bypasses CFN, use **ECS → service → Update
service → Task definition family → pick previous revision** in the
console. This causes drift; reconcile by updating the template afterward.)

---

## Troubleshooting

### Dashboard renders but KPI cards show 0 / NaN%, tables show "empty"

The container is reading from S3 successfully (no errors in CloudWatch),
but every Gold table comes back empty.

**Investigate, don't assume.** The symptom is identical for three very
different root causes; treat the empty render as a signal to look at the
read stack, not as a diagnosis.

1. **Empty source data.** PR 2's Lambda pre-seeds the watermark forward to
   skip the long initial backfill (see `known_issues.md` #6), and the
   demo Wistia account may have no new play events between the seeded
   watermark and now. Re-running Glue against a landing layer with
   `record_count: 0` files produces a 0-row fact, and the dashboard
   correctly renders an empty UI. Confirm by reading
   `s3://wistia-datalake-.../gold/fact_media_engagement` locally with
   admin creds. **This is what we hit during PR 4 verification.**
2. **Stale Streamlit cache.** Streamlit's `@st.cache_data` holds the
   first `load_gold` result for the lifetime of the container. After
   Glue rewrites Gold, force a new ECS deployment
   (`aws ecs update-service --force-new-deployment ...`) so a fresh task
   reads the new data. The existing task will keep serving the cached
   empty result indefinitely.
3. **Task-role missing permission.** The role's inline policy must allow
   both `s3:GetObject` on `gold/*` AND `s3:ListBucket` on the bucket
   (scoped to the `gold` prefix). Missing ListBucket causes
   `pd.read_parquet` to return an empty DataFrame silently, not raise.
   The relaxed policy in `dashboard.yaml` is the reference shape.

**Diagnostic switch**: set `WISTIA_DASHBOARD_DEBUG=1` on the task (via
CFN parameter override or a temporary `aws ecs update-service`) and
refresh the dashboard. The container will print three lines per render
showing what s3fs sees + the resulting DataFrame shape. Compare those
shapes to a local
`pd.read_parquet("s3://wistia-datalake-.../gold/<table>")` against the
same Gold to pinpoint which of the three causes you're hitting.

### Phase 3 update fails with "task stopped: CannotPullContainerError"

The image isn't actually in ECR for the tag the task def expects. Causes:

- You skipped Phase 2 (no `docker push` happened).
- The build script succeeded but pushed to a different repo (wrong
  account, wrong region).

Fix: re-run `./infra/scripts/build-dashboard-image.ps1`, then re-trigger
the Service update.

### Target group target is `unhealthy: Health checks failed`

The container started but Streamlit isn't responding at
`/_stcore/health`. Check CloudWatch logs for the task — typical causes:

- The container crashed at startup (missing `WISTIA_GOLD_URI`, no S3
  access). Look for Python traceback in the log stream.
- The task role lacks S3 read permissions. Confirm under
  **IAM → Roles → wistia-prod-dashboard-task-role**.
- Streamlit is still warming up. The `HealthCheckGracePeriodSeconds: 60`
  in the template gives it a window; if it's slow, bump the param.

### Stack update stuck at `UPDATE_IN_PROGRESS` for >10 minutes

The Service is waiting for the new task to be `Healthy` before stopping
the old one. If the task keeps failing, ECS rolls back automatically and
the stack lands at `UPDATE_ROLLBACK_COMPLETE`. Read the **Events** tab on
the Service for the specific failure.

### `aws ecs update-service` hangs

That command is synchronous by default and will wait until the deploy
stabilizes. If you don't need to wait, ignore the hang — the deploy
proceeds server-side and you can monitor via the console. If you do
need to wait, prefer `aws ecs wait services-stable` with
`--cli-read-timeout 0` (lesson #7 from `troubleshooting/known_issues.md`).

### "I don't see the dashboard at the ALB DNS name"

- DNS propagation can take ~30 seconds after the ALB transitions to
  `Active`. Hard-refresh after a minute.
- Check the ALB SG allows TCP 80 from `0.0.0.0/0` (it should — set by
  the template).
- Confirm you're using `http://` (not `https://` — no cert in this
  project).

---

## What you should be able to point at after this PR

1. **CloudFormation → wistia-dashboard** — `CREATE_COMPLETE` (or
   `UPDATE_COMPLETE` after Phase 3).
2. **ECR → wistia-prod-dashboard** — at least 2 image tags
   (`latest` + one SHA).
3. **ECS → Clusters → wistia-prod-dashboard → Services →
   wistia-prod-dashboard** — `Active` with `runningCount: 1`.
4. **EC2 → Target Groups → wistia-prod-dashboard** — 1 healthy target.
5. **EC2 → Load Balancers → wistia-prod-dashboard** — `Active`; DNS name
   serves the live dashboard.
6. **CloudWatch → /ecs/wistia-prod-dashboard** — one log stream per task
   launch.
