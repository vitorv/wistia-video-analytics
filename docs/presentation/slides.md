---
marp: true
theme: default
paginate: true
title: Wistia Video Analytics — End-to-End Data Pipeline on AWS
---

<!--
Marp-ready deck. Render with the Marp CLI or the VS Code "Marp for VS Code"
extension (Export → PDF/PPTX/HTML). Each `---` starts a new slide.
Speaker notes for each slide live in the companion `script.md` (word-for-word,
timed). Keep the API token off-screen at all times.
-->

# Wistia Video Analytics
### An automated, production-grade data pipeline on AWS

**Vitor Verissimo** · Senior Data Engineering project

<!-- Title card. Hold ~3s while you say the one-liner. -->

---

## The problem

- Wistia exposes video engagement through a **Stats API** — raw, paginated, per-request JSON.
- Goal: turn that into a **queryable analytics warehouse** that…
  - refreshes itself **daily**, unattended
  - runs in **production for 7 consecutive days**
  - lives entirely on **AWS**, with **CI/CD**
- Modeling target — the fact grain: **visitor × media × date**

---

## What I built

![Architecture](../architecture_diagram.drawio)

**Wistia API → Lambda → S3 (landing) → Glue: Bronze→Silver→Gold → S3 → Streamlit (ECS + ALB)**
Orchestration: **Glue Workflow + EventBridge** · Monitoring: **CloudWatch + SNS**

<!-- If the .drawio doesn't render in your tool, export it to PNG first and
swap the path. -->

---

## Proof it works — live

- **Dashboard (live):** 29,283 plays · 27,972 visitors · 31.3% avg watched · 1,117 watch-hours
- **Glue Workflow run history:** 7 green "Completed" runs — **2026-06-02 → 06-08**
- **CloudWatch alarm:** `OK` for the entire window

> 7 consecutive days · fully automated · **0 failures · 0 alerts** → **FR8 ✅**

---

## The data pipeline — medallion layers

| Layer | What happens | Decision |
| --- | --- | --- |
| **Landing** | Immutable raw JSON, one file per run | ADR-003 |
| **Bronze** | Typed + flattened; `media_id` carried from ingest metadata | lineage |
| **Silver** | Cleaned; drop zero-activity `by_date` rows | ADR-006 |
| **Gold** | Dimensional model | ADR-002 |

**Also:** pagination (FR6) · watermark-based incremental ingestion (FR7)

---

## Gold — the dimensional model

- **`dim_media`** — title, url, channel (YouTube/Facebook derivation)
- **`dim_visitor`** — most-recent-event-wins grain (**ADR-005**)
- **`fact_media_engagement`** — visitor × media × date; plays, watched %, watch time

`fact_media_engagement` = **28,406 rows** · `dim_visitor` = **27,972 rows**

---

## Why these choices (1/2)

| Decision | Chose | Rejected | Why |
| --- | --- | --- | --- |
| Ingestion compute | **Lambda** | Glue | HTTP calls don't need Spark; cheaper, faster |
| Transforms | **Glue (PySpark)** | dbt | Required PySpark-native; serverless Spark |
| Orchestration | **Glue Workflow + EventBridge** | Step Functions, Airflow | Native, no extra infra |

---

## Why these choices (2/2)

| Decision | Chose | Rejected | Why |
| --- | --- | --- | --- |
| Dashboard hosting | **ECS Fargate + ALB** | App Runner | App Runner blocks WebSocket (Streamlit) |
| IaC | **CloudFormation** | console clicks | Reproducible, reviewable (ADR-008) |
| Python | **3.11** | 3.12 | Exact AWS Glue 5.0 parity |

---

## CI/CD & production hardening

- **GitHub Actions:** every PR runs the suite — **98 tests · 100% coverage** · ruff/black/mypy *(FR9)*
- **Branching:** short-lived `feat/*` → PR → `master` (ADR-007)
- **Monitoring & alerting:**
  - CloudWatch alarm on Lambda errors → SNS email
  - EventBridge rule on all 3 Glue jobs (FAILED / TIMEOUT / STOPPED) → SNS email

> It doesn't just run — it tells me when it breaks.

---

## What I learned

- **ECR token corruption** — PowerShell appends CRLF when piping to `docker login`; ECR rejects it (HTTP 400). Fix: run through `cmd /c`.
- **Glue triggers are context-sensitive** — CONDITIONAL triggers only fire *inside* a workflow run, not from `start-job-run`.
- **CloudFormation + Glue** — can't swap a workflow's starting trigger in one deploy; delete-then-deploy.

*(16 issues documented in `troubleshooting/known_issues.md`.)*

---

## Cost & lifecycle

- **7-day run cost: ~$12** (Cost Explorer, 06-01 → 06-08)
- Driver = **always-on dashboard** (ECS + ALB + VPC ≈ $10); ingest + transform compute ≈ **$0.42**
- **One-command teardown** (`teardown.ps1`) returns the account to ~$0

> Cost-aware by design: compute is serverless and pay-per-run.

---

## Requirements coverage

| | | | |
| --- | --- | --- | --- |
| FR1 ✅ architecture | FR2 ✅ auth | FR3 ✅ media meta | FR4 ✅ engagement |
| FR5 ✅ visitor | FR6 ✅ pagination | FR7 ✅ incremental | FR8 ✅ 7-day run |
| FR9 ✅ CI/CD | FR10 ✅ DWH model | FR11 ✅ dashboard | FR12 ✅ repo + docs |

---

## What's next

- **Athena / QuickSight** over the Gold layer for ad-hoc SQL
- True **incremental streaming** if Wistia volume grows
- **Rotate + purge** the shared API token (history rewrite)

# Thank you
**Repo:** github · **Docs:** `context_vault/` + `docs/aws-console-guides/`
