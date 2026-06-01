# Wistia Video Analytics Pipeline

An end-to-end data engineering pipeline that ingests video engagement
analytics from the **Wistia Stats API**, processes them with **PySpark**, and
serves a **Streamlit** dashboard. The production target is AWS (Phase 3).

## Status

| Phase | Scope | Status |
| --- | --- | --- |
| **Phase 1** | Ingestion layer — Wistia API → local `landing/` zone | ✅ Complete |
| **Phase 2** | Bronze → Silver → Gold transforms + Streamlit dashboard, all local | ✅ Complete |
| **Phase 3** | AWS deployment (Lambda + Glue + EventBridge + ECS Fargate) via CloudFormation; 7-day production run | ✅ Complete |

## Local architecture (Phase 2)

```
 Wistia Stats API
        │
        │  src.ingestion  (Python; requests + watermark)
        ▼
   landing/   (raw JSON, immutable per-run files)
        │
        │  src.transforms  (PySpark; pure DataFrame → DataFrame functions)
        ▼
   bronze/ → silver/ → gold/   (Parquet)
        │
        │  src.dashboard   (Streamlit; pandas / pyarrow)
        ▼
    Browser
```

- **Ingestion** (`src/ingestion/`) — pulls Events, by_date, and Media metadata
  per media; writes raw JSON envelopes to `landing/`; tracks per-(endpoint,
  media) watermarks for incremental runs.
- **Transforms** (`src/transforms/`) — Bronze (schema-stamp landing JSON) →
  Silver (clean / type-cast / dedupe / drop zero-activity days) → Gold star
  schema (`dim_media`, `dim_visitor`, `fact_media_engagement`).
- **Dashboard** (`src/dashboard/`) — reads Gold Parquet with pandas/pyarrow
  (no Spark) and renders KPI cards, recent-window summaries, daily and
  monthly trends, and a top-visitors leaderboard.

## Prerequisites

- **Python 3.11** — matches AWS Glue 5.0; PySpark 3.5.x is not fully
  compatible with Python 3.12 (`distutils` removed).
- **JDK 17 or 21** — for local PySpark. Spark 3.5 officially supports through
  Java 17; Java 21 runs in practice. CI uses Temurin 17.
- A **Wistia API token** with the *Read detailed stats* permission.

### Windows extra — Hadoop native binaries

PySpark on Windows needs `winutils.exe` + `hadoop.dll` for local-filesystem
Parquet I/O. Download them (Hadoop 3.3.6) from
[`cdarlint/winutils`](https://github.com/cdarlint/winutils) into
`vendor/hadoop/bin/`:

```
vendor/hadoop/
└── bin/
    ├── winutils.exe
    └── hadoop.dll
```

`vendor/` is gitignored. `src/transforms/spark.py:build_spark` wires up
`HADOOP_HOME` automatically when those binaries are present. Linux / macOS
need neither.

## Setup

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements-dev.txt
```

Create a `.env` in the project root:

```
WISTIA_API_TOKEN=your_token_here
```

`.env` is gitignored — never commit a token.

## Running the pipeline

```bash
# 1. Pull raw data from the Wistia API into the landing zone.
#    Incremental — only data newer than the stored watermark is fetched.
python -m src.ingestion

# 2. Transform landing JSON → Bronze → Silver → Gold Parquet.
python -m src.transforms

# 3. Open the dashboard (reads gold/ via pandas/pyarrow).
streamlit run src/dashboard/app.py
```

The dashboard renders at `http://localhost:8501` by default.

## Quality gates

All four run in CI on every push and pull request:

```bash
ruff check src tests       # lint
black --check src tests    # format
mypy src tests             # type-check
pytest                     # tests + coverage (100% enforced)
```

The test suite mocks all HTTP and runs a local Spark session — no live API
calls, no AWS dependencies.

## Project structure

```
src/
  common/             shared logging (JSON line formatter for CloudWatch)
  ingestion/          Phase 1 — client, extractors, landing, watermark, pipeline
  transforms/         Phase 2 — PySpark Bronze → Silver → Gold transforms
  transforms/glue/    Phase 3 — Glue 5.0 entry-point scripts (one per layer)
  dashboard/          Phase 2 — Streamlit UI + pandas data layer (S3-aware in Phase 3)
infra/
  cloudformation/     Phase 3 — 5 CFN templates (one per stack)
  scripts/            Phase 3 — packaging + build + teardown PowerShell scripts
docs/aws-console-guides/
                      Phase 3 — web-UI walkthroughs (one per PR)
tests/                test suite + sanitized fixtures
scripts/              one-off API exploration scripts (excluded from gates)
vendor/               (Windows local-dev only; gitignored) Hadoop native binaries
.github/workflows/    CI pipeline
```

## Architecture decisions

Major decisions are recorded as ADRs in `context_vault/decisions/` (vault is
gitignored). Phase 1 + 2 ADRs:

- **ADR-001** — System architecture (Lambda + Glue + ECS Fargate + ALB)
- **ADR-002** — Fact-table grain: visitor × media × date
- **ADR-003** — Landing zone uses immutable per-run files (Bronze dedupes downstream)
- **ADR-004** — Bounded initial backfill (`BACKFILL_FLOOR_DATE = 2024-03-01`)
- **ADR-005** — `dim_visitor` grain: most-recent event wins (resolves D1)
- **ADR-006** — Filter zero-activity `by_date` rows in Silver (resolves D3)
- **ADR-007** — Branching strategy: short-lived feature branches via PR
- **ADR-008** — CloudFormation as Infrastructure-as-Code (Phase 3)

## Phase 3 — AWS deployment

The pipeline runs on AWS via 5 CloudFormation stacks. Deploy order:

```powershell
# 1. Foundation — S3 data lake + artifacts buckets
aws cloudformation deploy --stack-name wistia-foundation `
  --template-file infra/cloudformation/foundation.yaml `
  --parameter-overrides Env=prod --region us-east-1

# 2. Ingest — Lambda + EventBridge (daily 06:00 UTC)
./infra/scripts/package-lambda.ps1 -Upload
aws cloudformation deploy --stack-name wistia-ingest `
  --template-file infra/cloudformation/ingest.yaml `
  --capabilities CAPABILITY_NAMED_IAM `
  --parameter-overrides Env=prod WistiaApiToken=$Token --region us-east-1

# 3. Transforms — 3 Glue jobs + Workflow + SCHEDULED trigger (06:15 UTC)
./infra/scripts/package-transforms.ps1 -Upload
aws cloudformation deploy --stack-name wistia-transforms `
  --template-file infra/cloudformation/transforms.yaml `
  --capabilities CAPABILITY_NAMED_IAM `
  --parameter-overrides Env=prod --region us-east-1

# 4. Dashboard — ECR + ECS Fargate + ALB. Two-phase: deploy without
#    Service, push image, deploy with Service.
aws cloudformation deploy --stack-name wistia-dashboard `
  --template-file infra/cloudformation/dashboard.yaml `
  --capabilities CAPABILITY_NAMED_IAM `
  --parameter-overrides Env=prod DeployService=false `
    DefaultVpcId=$VpcId DefaultPublicSubnetIds=$SubnetCsv --region us-east-1
./infra/scripts/build-dashboard-image.ps1
aws cloudformation deploy --stack-name wistia-dashboard `
  --template-file infra/cloudformation/dashboard.yaml `
  --capabilities CAPABILITY_NAMED_IAM `
  --parameter-overrides Env=prod DeployService=true `
    DefaultVpcId=$VpcId DefaultPublicSubnetIds=$SubnetCsv --region us-east-1

# 5. Monitoring — SNS alerts + Lambda alarm + Glue failure rule
aws cloudformation deploy --stack-name wistia-monitoring `
  --template-file infra/cloudformation/monitoring.yaml `
  --parameter-overrides Env=prod AlertEmail=you@example.com --region us-east-1
# Confirm the SNS subscription email AWS sends to that address.
```

Step-by-step console walkthroughs live in
[`docs/aws-console-guides/`](docs/aws-console-guides/) (one per PR).

### Tear-down

```powershell
./infra/scripts/teardown.ps1 -WhatIf   # preview
./infra/scripts/teardown.ps1           # confirm prompt, then live
```

Empties the ECR repo + both S3 buckets, then deletes all 5 stacks in
reverse dependency order. Run rate after: ~$0/day.
