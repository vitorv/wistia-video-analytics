# PR 1 — Foundation: AWS Console Walkthrough

> A pure web-UI version of what `infra/cloudformation/foundation.yaml` deploys.
> Use this if you need to reproduce PR 1's outcome without the AWS CLI, or as a
> reference for what the CloudFormation template actually creates.
>
> **Outcome:** two S3 buckets in `us-east-1` — `wistia-datalake-<account>-us-east-1`
> and `wistia-artifacts-<account>-us-east-1`, both with SSE-S3 encryption,
> versioning suspended, and full public-access-block.
>
> **Two paths** are documented below:
> - **Path A** (recommended): upload `foundation.yaml` to the CloudFormation
>   console and click "Create stack." Same outcome as the CLI; preserves the
>   Infrastructure-as-Code benefits.
> - **Path B**: create the two S3 buckets manually from scratch, no CFN.
>   Educational — shows what the CFN template translates to under the hood.
>   Use only if you're explicitly skipping IaC.

---

## Prerequisites

1. AWS account with admin (or equivalent) permissions on S3 + CloudFormation.
2. **Region locked to N. Virginia (us-east-1).** Top-right of every console
   page → region dropdown → "US East (N. Virginia) us-east-1." This must be
   set *before* you start, on *every* page you open.
3. You know your **AWS account ID** (12-digit number). Find it: top-right of
   the console → click your username → "Account ID" copies to clipboard with
   the small icon. Or via CLI: `aws sts get-caller-identity --query Account --output text`.

For the bucket names below, substitute your account ID for `<account>`. The
PR 1 template uses CFN's `!Sub ${AWS::AccountId}` to generate this
automatically; in the console you type it.

---

## Path A — Upload `foundation.yaml` to CloudFormation

This is the closest equivalent to what the `aws cloudformation deploy` CLI
command does. AWS lets you upload any template file (or paste YAML/JSON) and
it handles the create-resources-in-order part for you.

### Step A1 — Open the CloudFormation console

URL: <https://us-east-1.console.aws.amazon.com/cloudformation/home?region=us-east-1>

Or: Console search bar (top) → type "CloudFormation" → click the service.

Verify the region dropdown (top-right) reads **N. Virginia**.

You should land on the **Stacks** list. If you have no stacks yet, you'll see
an empty state with a big "Create stack" button. If you already have other
stacks (e.g., from earlier exploration), they appear in a table.

### Step A2 — Start a new stack

Click the orange **Create stack** button → **With new resources (standard)**.

(The other option, "From existing resources (import resources)," is for
adopting resources that already exist outside CFN. Not what we want.)

### Step A3 — Specify the template

You're on the "Specify template" page.

- **Prerequisite — Prepare template**: select **Choose an existing template**.
- **Specify template**: select **Upload a template file**.
- Click **Choose file** → navigate to `infra/cloudformation/foundation.yaml`
  in your local repo → select it.

The file uploads to a CFN-managed staging S3 bucket (AWS shows this as
`cf-templates-<hash>-us-east-1`). That's normal and free; CFN creates the
bucket once per region the first time you use the console.

Click **Next**.

### Step A4 — Specify stack details

- **Stack name**: `wistia-foundation`
  (This is the name shown in the Stacks list and in CLI commands. Lowercase,
  no spaces. The PR 1 plan uses this exact name.)

- **Parameters** → `Env`:
  Dropdown shows `dev` and `prod`. Choose **`prod`**.
  This sets the suffix on the Export names so future stacks (PR 2+) can find
  these buckets via `!ImportValue wistia-prod-datalake-bucket`.

Click **Next**.

### Step A5 — Configure stack options

This page is long and most defaults are fine. Things worth noting:

- **Tags** (optional, but recommended):
  Click **Add new tag**, add:
  - Key: `project`, Value: `wistia`
  - Key: `env`, Value: `prod`

  These tags flow down to every resource the stack creates (the buckets pick
  them up too). They make Cost Explorer breakdowns by-project much cleaner.

- **Permissions** → **IAM role**: leave blank. CFN uses your console session's
  permissions, which for the Wistia project means admin.

- **Stack failure options**: leave on the default ("Roll back all stack
  resources"). If anything fails during create, CFN un-creates everything
  cleanly, leaving no orphaned buckets.

- **Capabilities**: PR 1's template has no IAM resources, so no checkboxes
  appear here. (PR 2+ will need `CAPABILITY_NAMED_IAM` ticked.)

Click **Next**.

### Step A6 — Review and submit

Scroll through the review page. Confirm:

- Stack name: `wistia-foundation`
- Parameters: `Env = prod`
- Tags: `project=wistia`, `env=prod`
- Template URL: a CFN-staging S3 URL (auto-generated)
- "Resources" section lists `DataLakeBucket` and `ArtifactsBucket` (both
  `AWS::S3::Bucket`).

Click **Submit**.

### Step A7 — Wait for CREATE_COMPLETE

You're now on the **stack detail page**. The status starts as `CREATE_IN_PROGRESS`
(yellow). S3 buckets create in seconds — the whole stack reaches
`CREATE_COMPLETE` (green) in about 30 seconds.

Click the **Events** tab to watch progress in real time. You'll see lines
like:
- `CREATE_IN_PROGRESS  AWS::S3::Bucket   DataLakeBucket`
- `CREATE_COMPLETE     AWS::S3::Bucket   DataLakeBucket`

If something errors, the **Status reason** column explains why (e.g., "Bucket
name already exists" if you forgot the account-id suffix — see
[Troubleshooting](#troubleshooting) below).

### Step A8 — Verify outputs

Once the status is `CREATE_COMPLETE`:

- **Outputs** tab: should show four rows:
  - `DataLakeBucketName` → `wistia-datalake-<account>-us-east-1`
  - `DataLakeBucketArn` → `arn:aws:s3:::wistia-datalake-<account>-us-east-1`
  - `ArtifactsBucketName` → `wistia-artifacts-<account>-us-east-1`
  - `ArtifactsBucketArn` → `arn:aws:s3:::wistia-artifacts-<account>-us-east-1`

  Each has an "Export name" — that's what later stacks consume via
  `!ImportValue`.

- **Resources** tab: lists the two `AWS::S3::Bucket` resources, with links to
  open them in the S3 console.

### Step A9 — Verify the buckets in the S3 console

Click either bucket's **Physical ID** (the bucket name) on the Resources tab.
That deep-links to the S3 console for that bucket.

On the bucket page:

- **Properties** tab:
  - **Bucket Versioning**: should show **Suspended**.
  - **Default encryption**: should show **Server-side encryption with Amazon
    S3 managed keys (SSE-S3) AES256**. Bucket Key disabled.
  - **Tags**: should include `project=wistia`, `env=prod`, `stack=foundation`.

- **Permissions** tab:
  - **Block public access (bucket settings)**: all four sub-settings on:
    - Block public access to buckets and objects granted through *new* access control lists (ACLs): **On**
    - Block public access to buckets and objects granted through *any* access control lists (ACLs): **On**
    - Block public access to buckets and objects granted through *new* public bucket or access point policies: **On**
    - Block public access to buckets and objects granted through *any* public bucket or access point policies: **On**

Back up and verify the other bucket the same way.

Path A is complete. The buckets are live and identical to what the CLI
deploy produces.

---

## Path B — Manual S3 (no CloudFormation)

Use this if you're explicitly skipping IaC. The trade-off: changes you make
later in the console will *not* be tracked anywhere — you become responsible
for keeping `foundation.yaml` and the live state in sync (or for not caring
about that).

### Step B1 — Open the S3 console

URL: <https://us-east-1.console.aws.amazon.com/s3/home?region=us-east-1>

Or: Console search bar → "S3" → click.

S3 is technically a global service (bucket names are globally unique across
all accounts), but the console shows buckets per the region they were created
in. Confirm region = **N. Virginia (us-east-1)** before continuing.

### Step B2 — Create the data lake bucket

Click **Create bucket** (orange, top-right).

Fill in:

- **Bucket name**: `wistia-datalake-<account>-us-east-1`
  (Substitute your 12-digit account ID. The exact name pattern doesn't matter
  functionally, but PR 2+ stacks expect this pattern via `!Sub`.)

- **AWS Region**: **US East (N. Virginia) us-east-1**
  Should already be filled in from the page region.

- **Copy settings from existing bucket**: leave blank.

- **Object Ownership**: **ACLs disabled (recommended)**.
  This is the modern default and matches the PR 1 template (which doesn't set
  ACLs anywhere).

- **Block Public Access settings for this bucket**:
  Leave **all four sub-settings checked**. The default "Block all public
  access" checkbox at the top should be checked. This matches the template's
  `PublicAccessBlockConfiguration` with everything `true`.

- **Bucket Versioning**: **Disable**.
  The PR 1 template uses `Status: Suspended`. The console wording is
  "Disable" but the underlying state is the same — versioning is off.

- **Tags** (optional): add the same tags from Path A — `project=wistia`,
  `env=prod`, `stack=foundation`.

- **Default encryption** → **Encryption type**:
  Select **Server-side encryption with Amazon S3 managed keys (SSE-S3)**.
  (This is the default for new buckets as of January 2023, but worth
  confirming.)

  Leave **Bucket Key** disabled.

- **Advanced settings**: leave defaults (Object Lock disabled).

Click **Create bucket** at the bottom. You're returned to the buckets list
with a green confirmation banner.

### Step B3 — Create the artifacts bucket

Same as Step B2, but the bucket name is `wistia-artifacts-<account>-us-east-1`.

### Step B4 — Verify

For each bucket, click the bucket name → **Properties** tab → confirm
encryption is SSE-S3 and versioning is "Disabled." Click **Permissions** tab →
confirm Block Public Access shows "Block *all* public access — On."

Path B is complete.

---

## What the buckets are *for*

This is the same content as the CFN template, restated for the
console-walkthrough reader.

| Bucket | Purpose |
|---|---|
| `wistia-datalake-<account>-us-east-1` | The data lake. All pipeline data lives here under prefixes: `landing/` (raw API JSON, Lambda writes), `bronze/` (schema-stamped Parquet, Glue Bronze writes), `silver/` (cleaned/deduped Parquet, Glue Silver writes), `gold/` (dimensional model Parquet, Glue Gold writes), `state/` (watermark.json). |
| `wistia-artifacts-<account>-us-east-1` | Deployment artifacts: Lambda zips (PR 2 uploads here), Glue PySpark scripts (PR 3 uploads here), CloudFormation staging templates. *Code*, not data. |

Keeping these separate means deleting the data lake never touches your
deployable artifacts, and the IAM policies on each can be tighter (e.g.,
Glue gets read-only on artifacts, read+write on the data lake).

---

## Tear down

If you ever need to remove the buckets:

### If you used Path A (CloudFormation)

1. **Empty both buckets first.** CloudFormation will refuse to delete a
   non-empty S3 bucket. In the S3 console → click the bucket → **Empty**
   button (you'll be asked to type "permanently delete" to confirm). Do this
   for *both* buckets.

2. Open CloudFormation console → Stacks → click `wistia-foundation` →
   **Delete** button (top-right). Confirm.

3. Status moves to `DELETE_IN_PROGRESS` → `DELETE_COMPLETE`. The buckets are
   gone.

### If you used Path B (manual buckets)

1. In the S3 console, click each bucket → **Empty** → confirm.
2. Once empty, click each bucket → **Delete** → type the bucket name to
   confirm.

---

## Troubleshooting

### "Bucket name already exists" on create

S3 bucket names are **globally unique across all AWS accounts** in a partition
(commercial AWS = one partition). If you typed `wistia-datalake-foundation`
without the account ID, you might collide with someone else who used the same
name. The fix is the `wistia-datalake-<account>-us-east-1` pattern — embedding
your account ID guarantees uniqueness.

### Stack rolls back to `CREATE_FAILED` / `ROLLBACK_COMPLETE`

CFN tried to create something and failed. Click the **Events** tab → look for
the first red status (the *original* failure — later red events are usually
just the rollback cleanup). Common causes for this template:

- **Bucket name collision** (see above).
- **Account-level "block public access" override.** If your account has a
  policy that *blocks* you from un-blocking public access on buckets, the
  `PublicAccessBlockConfiguration` resource may fail because CFN tries to
  set it explicitly. Unusual for personal accounts.

After diagnosing, delete the failed stack (CFN won't let you redeploy with
the same name otherwise) and try again.

### "ResourceNotReady" or stale state on stack delete

If a bucket was emptied but the stack delete still hangs, refresh — sometimes
the bucket-empty operation takes a few seconds to propagate. If it's still
hanging after a minute, retry the delete; CFN should pick up on the second
attempt.

### I lost track of which region I created the buckets in

In S3, the bucket list shows the **AWS Region** column for each bucket. If
you accidentally created one in `us-east-2`, delete it (empty first) and
recreate in `us-east-1`. The PR 1 plan and all downstream stacks assume
`us-east-1`.

### I want to see what the buckets cost

S3 Standard storage in `us-east-1` is $0.023/GB-month. With ~900 MB of data
across the four pipeline layers, that's about $0.02/month — basically free.
The bigger cost driver is PUT/GET request charges if a job runs unexpectedly
often; the daily Glue pipeline in PR 3 was the main driver in the Global
Partners account (see Session 8 in the vault for the cleanup story).

---

## Related references

- [`infra/cloudformation/foundation.yaml`](../../infra/cloudformation/foundation.yaml) — the source template this guide reproduces
- [`infra/README.md`](../../infra/README.md) — deploy + teardown via CLI
- ADR-008 (vault) — why CloudFormation was chosen as the IaC tool
