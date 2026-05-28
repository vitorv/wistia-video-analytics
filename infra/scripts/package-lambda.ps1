# Wistia Phase 3 — Build the Lambda deployment zip for the ingest function.
#
# Usage:
#   ./infra/scripts/package-lambda.ps1
#   ./infra/scripts/package-lambda.ps1 -Upload    # also push to the artifacts bucket
#
# Builds build/lambda.zip containing:
#   - src/common/ and src/ingestion/ (no transforms/dashboard/tests)
#   - Runtime deps from requirements.txt installed at the zip root
#
# Lambda expects the handler module to be importable from the zip root, so the
# zip layout is:  src/__init__.py, src/common/..., src/ingestion/..., boto3/...
# Handler entry point: src.ingestion.pipeline.handler

param(
    [switch]$Upload
)

$ErrorActionPreference = 'Stop'

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$BuildDir = Join-Path $RepoRoot "build"
$StageDir = Join-Path $BuildDir "lambda"
$ZipPath  = Join-Path $BuildDir "lambda.zip"

Write-Host "==> Cleaning $BuildDir"
if (Test-Path $BuildDir) {
    Remove-Item -Recurse -Force $BuildDir
}
New-Item -ItemType Directory -Path $StageDir | Out-Null

Write-Host "==> Installing runtime dependencies into staging dir"
& "$RepoRoot\.venv\Scripts\pip.exe" install `
    --quiet `
    --target $StageDir `
    -r (Join-Path $RepoRoot "requirements.txt")
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host "==> Copying src/common and src/ingestion"
$SrcDir = Join-Path $StageDir "src"
New-Item -ItemType Directory -Path $SrcDir | Out-Null
Copy-Item (Join-Path $RepoRoot "src\__init__.py") $SrcDir
Copy-Item -Recurse (Join-Path $RepoRoot "src\common")    $SrcDir
Copy-Item -Recurse (Join-Path $RepoRoot "src\ingestion") $SrcDir

Write-Host "==> Pruning __pycache__ and dist-info metadata"
Get-ChildItem -Path $StageDir -Recurse -Filter __pycache__ -Directory `
    | Remove-Item -Recurse -Force
# Trim the lambda-irrelevant *.dist-info directories pip leaves behind
Get-ChildItem -Path $StageDir -Directory -Filter *.dist-info `
    | Remove-Item -Recurse -Force

Write-Host "==> Creating zip"
if (Test-Path $ZipPath) {
    Remove-Item $ZipPath
}
Compress-Archive -Path (Join-Path $StageDir "*") -DestinationPath $ZipPath
$SizeMb = [math]::Round((Get-Item $ZipPath).Length / 1MB, 2)
Write-Host "    $ZipPath ($SizeMb MB)"

if ($Upload) {
    $AccountId = aws sts get-caller-identity --query Account --output text
    $Bucket    = "wistia-artifacts-$AccountId-us-east-1"
    $Key       = "lambda/ingest.zip"
    Write-Host "==> Uploading to s3://$Bucket/$Key"
    aws s3 cp $ZipPath "s3://$Bucket/$Key"
    if ($LASTEXITCODE -ne 0) { exit 1 }
}

Write-Host ""
Write-Host "Done. Lambda zip at: $ZipPath"
