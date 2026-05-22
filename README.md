# Wistia Video Analytics Pipeline

An end-to-end data engineering pipeline that ingests video engagement analytics
from the **Wistia Stats API**, processes them with **PySpark**, and stores them
in a structured warehouse on **AWS**.

This repository currently contains **Phase 1 — the ingestion layer**: a tested,
locally-runnable module that pulls raw data from the Wistia API into a
partitioned landing zone. Phase 2 (PySpark transforms, AWS deployment) follows.

## Architecture (Phase 1)

The ingestion module (`src/ingestion/`) pulls three endpoints per media:

| Endpoint | Extractor | Output |
| --- | --- | --- |
| Events | `extract_events` | per-visitor engagement events |
| by_date | `extract_by_date` | media-level daily aggregates |
| Media metadata | `extract_media_metadata` | media title, created date |

Raw responses are written to a partitioned landing zone that mirrors the future
`s3://<bucket>/landing/` layout:

```
landing/<endpoint>/media_id=<id>/ingest_date=<YYYY-MM-DD>/data_<timestamp>.json
```

Each run writes its own immutable file, and a watermark store bounds incremental
runs so only new data is fetched.

## Prerequisites

- Python 3.12
- A Wistia API token with the **Read detailed stats** permission

## Setup

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements-dev.txt
```

Create a `.env` file in the project root:

```
WISTIA_API_TOKEN=your_token_here
```

`.env` is gitignored — never commit a token.

## Running the pipeline

```bash
python -m src.ingestion
```

This pulls all endpoints for the configured media IDs and writes to `landing/`.
Re-runs are incremental — only data newer than the stored watermark is fetched.

## Quality gates

All four run in CI on every push and pull request:

```bash
ruff check src tests       # lint
black --check src tests    # format
mypy src tests             # type-check
pytest                     # tests + coverage (100% enforced)
```

The test suite mocks all HTTP — no live API calls.

## Project structure

```
src/ingestion/      ingestion module: client, extractors, landing, watermark, pipeline
tests/              test suite + sanitized fixtures
scripts/            one-off API exploration scripts
.github/workflows/  CI pipeline
```
