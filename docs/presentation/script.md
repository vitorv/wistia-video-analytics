# Narration Script — Wistia Video Analytics video walkthrough

> Word-for-word narration, timed to ~10 minutes. Each section maps to a slide in
> `slides.md` and notes what to show on screen. Brackets `[ ]` are stage
> directions, not spoken. Tip: record demo segments (§3, parts of §4/§6)
> **separately** from narration so a misclick doesn't cost a whole take.
>
> **Keep the API token off-screen the entire time** — don't show `.env`, the
> Lambda env vars, or commit diffs that contain it.

**Total target: ~10:00**

---

## §1 — Hook & problem · 0:00–0:45 · [Slide: Title → Problem]

> "Hi — I'm Vitor, and this is my Wistia Video Analytics project: an automated,
> production-grade data pipeline running end-to-end on AWS.
>
> Here's the problem. Wistia exposes video engagement data through its Stats
> API — but it comes back as raw, paginated JSON, one request at a time. That's
> fine for a quick look, but useless as analytics.
>
> My goal was to turn that into a proper warehouse: a pipeline that refreshes
> itself every day without me touching it, runs in production for seven straight
> days, and lives entirely on AWS with CI/CD. I designed the whole thing around
> one analytical grain — engagement at the level of **visitor, by media, by
> date**. Everything downstream serves that."

---

## §2 — What I built · 0:45–1:45 · [Slide: Architecture diagram]

> "Here's the architecture at a glance. [Trace the path with your cursor.]
>
> A scheduled **Lambda** calls the Wistia API and drops raw JSON into an **S3**
> landing zone. **AWS Glue** then runs PySpark transforms in three stages —
> Bronze, Silver, Gold — writing each layer back to S3 as Parquet. A
> **Streamlit dashboard** reads the Gold layer and serves it over an
> **Application Load Balancer**, running as a container on **ECS Fargate**.
>
> The whole pipeline is chained by a **Glue Workflow** and triggered daily by
> **EventBridge**, and it's watched by **CloudWatch and SNS**.
>
> A quick note on two of those choices, because they matter: I used **Lambda**
> for ingestion, not Glue — HTTP calls don't need Spark, so Lambda is cheaper and
> faster. And I used **Glue with PySpark** for transforms because the assignment
> required PySpark-native — no dbt. I'll come back to the rest of the decisions
> later."

---

## §3 — Live demo (the centerpiece) · 1:45–4:15 · [Screen recording]

> "But the best way to show it works is to just show it.
>
> [Open the live dashboard URL.] This is the dashboard, live on AWS right now.
> At the top: **29,283 plays**, **27,972 unique visitors**, an average of
> **31.3% of each video watched**, and over **1,100 watch-hours** in total.
> [Apply a filter or pick a media; let a chart react.] Everything's interactive
> and it's reading straight from the Gold layer in S3.
>
> Now — is it actually *running in production*? [Switch to the AWS console → Glue
> → Workflows → run history.] Here's the Glue workflow's run history. Look at
> this column — one successful run every single day, **June 2nd through June
> 8th**, each one green, each one completing all three jobs. [Switch to
> CloudWatch → Alarms.] And here's the error alarm: it stayed **OK** the entire
> window.
>
> So: **seven consecutive days, fully automated, zero failures and zero alerts.**
> That's the production requirement — FR8 — satisfied with evidence."

---

## §4 — The pipeline up close · 4:15–6:15 · [Slide: medallion + Gold; glance at a Gold table]

> "Let me open up what's actually happening inside that pipeline. I used a
> **medallion architecture** — Bronze, Silver, Gold.
>
> **Landing** is the raw API response, written as immutable per-run files — I
> never mutate raw data, so I can always replay. **Bronze** types and flattens
> it; one detail I'm proud of — the by-date records don't carry a media ID, so I
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

> "I want to spend a minute on the decisions, because good data engineering is
> mostly about tradeoffs, and I documented every one of these as an ADR in the
> repo.
>
> I already mentioned Lambda over Glue for ingestion. For **orchestration**, I
> chose the Glue Workflow plus EventBridge over Step Functions or Airflow —
> native integration, no extra infrastructure to manage.
>
> For the **dashboard**, this one's a real lesson: I chose ECS Fargate behind an
> ALB instead of App Runner. App Runner looks simpler, but it blocks the
> WebSocket connection Streamlit needs — so it was a non-starter. The ALB makes
> WebSockets work.
>
> Everything is **CloudFormation** — infrastructure as code — so the entire
> stack is reproducible and reviewable, not a pile of console clicks. And I
> pinned **Python 3.11** specifically to match AWS Glue 5.0 exactly, which saved
> me from a class of version-mismatch bugs."

---

## §6 — CI/CD & hardening · 8:00–9:00 · [GitHub Actions run; glance at monitoring.yaml]

> "On the engineering-practice side: [show a green GitHub Actions run] every pull
> request runs the full test suite through GitHub Actions — **98 tests at 100%
> coverage**, plus linting and type checks. Work happens on short-lived feature
> branches that merge to master through PRs.
>
> And it's not just tested — it's monitored. [Glance at monitoring.] There's a
> CloudWatch alarm on Lambda errors and an EventBridge rule watching all three
> Glue jobs for failures or timeouts. Either one emails me through SNS. So the
> pipeline doesn't just run unattended — it tells me the moment something
> breaks."

---

## §7 — What I learned · 9:00–9:35 · [Slide: What I learned]

> "A few honest lessons from the build — I logged sixteen of these in the repo.
> My favorite: when you pipe a password into `docker login` from PowerShell, it
> sneaks in a carriage return and ECR rejects the login with a cryptic 400. The
> fix was to route it through the old `cmd` shell. The other one that cost me
> time — Glue's conditional triggers only fire *inside* a workflow run, not when
> you run a job standalone. Small things, but exactly the kind of thing that
> only shows up in production."

---

## §8 — Cost, lifecycle & close · 9:35–10:00 · [Slides: Cost, Requirements, Next, Thank you]

> "Finally — cost. The whole seven-day run cost about **twelve dollars**, and
> almost all of that is the always-on dashboard. The actual ingestion and
> transformation compute? Forty-two cents. It's serverless and pay-per-run, and
> a single teardown command returns the account to essentially zero.
>
> So, to wrap up: an automated, monitored, seven-day-proven Wistia analytics
> warehouse on AWS — hitting every requirement from architecture through CI/CD
> and the production run. Next steps would be Athena or QuickSight over the Gold
> layer and rotating the shared API token.
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
