# Narration Script — Wistia Video Analytics video walkthrough

**Total target: ~10:00**

---

## §1 — Hook & problem · 0:00–0:45 · [Slide: Title → Problem]

> "Hi — I'm Vitor, and this is my Wistia Video Analytics project: Wistia exposes video engagement data through its Stats API — but it comes back as raw, paginated JSON, one request at a time."

---

## §2 — What I built · 0:45–1:45 · [Slide: Architecture diagram]

> "Here's the architecture at a glance. 
>
> A scheduled **Lambda** calls the Wistia API and drops raw JSON into an **S3** landing zone. (a quick note: I used **Lambda** for ingestion, not Glue because HTTP calls don't need Spark, and Lambda is cheaper and faster.)
> **AWS Glue** then runs PySpark transforms in three stages —
> Bronze, Silver, Gold — writing each layer back to S3 as Parquet. (I used **Glue with PySpark** for transforms because the assignment required PySpark-native — no dbt.) A
> **Streamlit dashboard** reads the Gold layer and serves it over an
> **Application Load Balancer**, running as a container on **ECS Fargate**.
>
> The whole pipeline is chained by a **Glue Workflow** and triggered daily by
> **EventBridge**, and it's watched by **CloudWatch and SNS**."
>

---

## §3 — Live demo (the centerpiece) · 1:45–4:15 · [Screen recording]

> "[Open the live dashboard URL.] This is the dashboard, live on AWS right now.
> At the top: **29,283 plays**, **27,972 unique visitors**, an average of
> **31.3% of each video watched**, and over **1,100 watch-hours** in total.
> [Apply a filter or pick a media; let a chart react.] Everything's interactive
> and it's reading straight from the Gold layer in S3.
>
> [Switch to the AWS console → Glue
> → Workflows → run history.] Here's the Glue workflow's run history. You can see one successful run every day since **June 2nd through June
> 8th**, each one green, each one completing all three jobs. [Switch to
> CloudWatch → Alarms.] And here's the error alarm: it stayed **OK** the entire
> window.
>
> So: **seven consecutive days, fully automated, zero failures and zero alerts.**"


---

## §4 — The pipeline up close · 4:15–6:15 · [Slide: medallion + Gold; glance at a Gold table]

> "Let me open up what's actually happening inside that pipeline. I used a
> **medallion architecture** — Bronze, Silver, Gold.
>
> **Landing** is the raw API response, written as immutable per-run files — I
> never mutate raw data, so I can always replay. **Bronze** types and flattens
> it; one detail to note — the by-date records don't carry a media ID, so I
> deliberately carry it down from the ingestion metadata to preserve the join
> key. **Silver** cleans the data and drops zero-activity rows that would
> otherwise inflate the counts. **Gold** is the dimensional model.
>
> [Show a Gold table — `fact_media_engagement` or `dim_visitor`.] Gold is three
> tables: `dim_media` with the channel derived from the URL, `dim_visitor` at a
> most-recent-event-wins grain, and the fact table — `fact_media_engagement` —
> at visitor-by-media-by-date. That's **28,406 fact rows** over nearly **28,000
> visitors**.
>
> Two requirements worth calling out here: the ingestion handles **pagination**
> to pull every page, and it's **incremental** — it tracks a watermark in S3 so
> each daily run only fetches what's new."

---

## §5 — Why I built it this way · 6:15–8:00 · [Slides: Why 1/2, Why 2/2]


> "I already mentioned Lambda over Glue for ingestion. For **orchestration**, I
> chose the Glue Workflow plus EventBridge over Step Functions or Airflow —
> native integration, no extra infrastructure to manage.
>
> Everything is **CloudFormation** — infrastructure as code — so the entire
> stack is reproducible and reviewable."

---

## §6 — CI/CD & hardening · 8:00–9:00 · [GitHub Actions run; glance at monitoring.yaml]


---

## §7 — What I learned · 9:00–9:35 · [Slide: What I learned]

---

## §8 — Cost, lifecycle & close · 9:35–10:00 · [Slides: Cost, Requirements, Next, Thank you]

> "So, to wrap up: seven-day-production run ran successfully
> all on AWS — hitting every requirement from architecture 
> 
> Thanks for watching — the code, the architecture decisions, and the AWS
> console guides are all in the repo."

---

## Recording checklist

- [ ] Dashboard is live (record demo **before** teardown)
- [ ] Glue run-history shows the full 06-02 → 06-08 green column
- [ ] CloudWatch alarm reads `OK`
- [ ] A green GitHub Actions run is open in a tab
- [ ] Architecture diagram exported to PNG if your tool won't render `.drawio`
- [ ] API token nowhere on screen (`.env`, Lambda env, commit diffs)
- [ ] Audio: one clean take per section; stitch in edit
