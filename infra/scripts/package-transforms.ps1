# Wistia Phase 3 — Package + upload the transforms zip and 3 Glue job scripts.
#
# Usage:
#   ./infra/scripts/package-transforms.ps1
#   ./infra/scripts/package-transforms.ps1 -Upload
#
# Builds build/transforms.zip containing only our pure-Python source:
#   - src/__init__.py
#   - src/common/      (shared JsonFormatter / configure_logging)
#   - src/transforms/  (bronze.py / silver.py / gold.py / config.py / schemas.py / spark.py)
# The src/transforms/glue/ directory is EXCLUDED — its scripts upload
# individually to s3://wistia-artifacts-.../glue/ and are referenced by the
# CFN template's `Command.ScriptLocation` per Glue job.
#
# Glue 5.0 provides PySpark 3.5.4 + Python 3.11 at runtime, so the zip ships
# no third-party dependencies. The zip is referenced via Glue's `--extra-py-files`
# job parameter — Glue adds it to PYTHONPATH inside each worker.

param(
    [switch]$Upload
)

$ErrorActionPreference = 'Stop'

$RepoRoot     = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$BuildDir     = Join-Path $RepoRoot "build"
$StageDir     = Join-Path $BuildDir "transforms"
$ZipPath      = Join-Path $BuildDir "transforms.zip"

Write-Host "==> Cleaning $StageDir"
if (Test-Path $StageDir) {
    Remove-Item -Recurse -Force $StageDir
}
New-Item -ItemType Directory -Path $StageDir | Out-Null

Write-Host "==> Copying src/common and src/transforms (minus glue/)"
$SrcDir = Join-Path $StageDir "src"
New-Item -ItemType Directory -Path $SrcDir | Out-Null
Copy-Item (Join-Path $RepoRoot "src\__init__.py") $SrcDir
Copy-Item -Recurse (Join-Path $RepoRoot "src\common") $SrcDir
# Copy src/transforms but exclude the glue/ subdirectory (those scripts upload separately)
$TransformsDest = Join-Path $SrcDir "transforms"
New-Item -ItemType Directory -Path $TransformsDest | Out-Null
Get-ChildItem -Path (Join-Path $RepoRoot "src\transforms") -File `
    | Copy-Item -Destination $TransformsDest

Write-Host "==> Pruning __pycache__"
Get-ChildItem -Path $StageDir -Recurse -Filter __pycache__ -Directory `
    | Remove-Item -Recurse -Force

Write-Host "==> Creating $ZipPath"
if (Test-Path $ZipPath) {
    Remove-Item $ZipPath
}
# PowerShell's Compress-Archive writes BACKSLASH-separated entry names on
# Windows, which breaks zipimport + extractall on Linux (where Glue runs).
# Use Python's zipfile module instead — it always writes forward slashes.
$pyExe = Join-Path $RepoRoot ".venv\Scripts\python.exe"
& $pyExe -c @"
import os, zipfile
stage = r'$StageDir'
zip_path = r'$ZipPath'
with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
    for root, _, files in os.walk(stage):
        for name in files:
            full = os.path.join(root, name)
            arc = os.path.relpath(full, stage).replace(os.sep, '/')
            zf.write(full, arc)
"@
if ($LASTEXITCODE -ne 0) { exit 1 }
$SizeKb = [math]::Round((Get-Item $ZipPath).Length / 1KB, 2)
Write-Host "    $ZipPath ($SizeKb KB)"

if ($Upload) {
    $AccountId = aws sts get-caller-identity --query Account --output text
    $Bucket    = "wistia-artifacts-$AccountId-us-east-1"

    Write-Host "==> Uploading transforms.zip to s3://$Bucket/glue/transforms.zip"
    aws s3 cp $ZipPath "s3://$Bucket/glue/transforms.zip"
    if ($LASTEXITCODE -ne 0) { exit 1 }

    Write-Host "==> Uploading 3 job scripts to s3://$Bucket/glue/"
    foreach ($job in @("bronze_job.py", "silver_job.py", "gold_job.py")) {
        $local = Join-Path $RepoRoot "src\transforms\glue\$job"
        aws s3 cp $local "s3://$Bucket/glue/$job"
        if ($LASTEXITCODE -ne 0) { exit 1 }
    }
}

Write-Host ""
Write-Host "Done. Transforms zip at: $ZipPath"
