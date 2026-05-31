# Wistia Phase 3 — Streamlit dashboard image.
#
# Built locally + pushed to ECR (see infra/scripts/build-dashboard-image.ps1).
# ECS Fargate pulls it and runs the task on port 8501 behind an ALB.
#
# The dashboard reads Gold Parquet straight from s3:// via pandas + s3fs;
# no Spark, no boto3 in app code. WISTIA_GOLD_URI is injected by the task
# definition (e.g. s3://wistia-datalake-<acct>-us-east-1/gold).

FROM python:3.11-slim

# Python hygiene
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install deps first so code changes don't bust the layer cache.
COPY requirements-dashboard.txt .
RUN pip install -r requirements-dashboard.txt

# Copy only what the dashboard imports. The full src/ tree (ingestion +
# transforms + glue scripts + Spark) would balloon the image and pull in
# pyspark; the dashboard only needs:
#   - src/dashboard/        UI + data access
#   - src/transforms/config.py  layer roots + join_layer_path
#   - src/common/           JsonFormatter / configure_logging (imported transitively)
COPY src/__init__.py src/__init__.py
COPY src/common/ src/common/
COPY src/dashboard/ src/dashboard/
COPY src/transforms/__init__.py src/transforms/__init__.py
COPY src/transforms/config.py src/transforms/config.py

EXPOSE 8501

# Streamlit's built-in health endpoint — used by the ALB target group and
# by Docker's HEALTHCHECK below.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request, sys; \
sys.exit(0 if urllib.request.urlopen('http://localhost:8501/_stcore/health', timeout=3).status == 200 else 1)"

USER nobody

CMD ["streamlit", "run", "src/dashboard/app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
