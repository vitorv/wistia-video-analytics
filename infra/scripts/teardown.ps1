# Wistia Phase 3 — Tear down all CloudFormation stacks in reverse order.
#
# Usage:
#   ./infra/scripts/teardown.ps1 -WhatIf      # preview, no changes
#   ./infra/scripts/teardown.ps1              # interactive confirmation, then delete
#   ./infra/scripts/teardown.ps1 -Force       # skip the prompt (use sparingly)
#
# Why this script exists:
#   `aws cloudformation delete-stack` won't delete a stack whose resources
#   still contain user data — specifically, non-empty S3 buckets and ECR
#   repositories. This script empties those first, then deletes the stacks
#   in reverse dependency order:
#
#     wistia-monitoring   (no exports; safe to drop first)
#     wistia-dashboard    (uses ECR repo from itself; empty ECR first)
#     wistia-transforms   (no S3; depends on foundation exports)
#     wistia-ingest       (no S3; depends on foundation exports)
#     wistia-foundation   (S3 buckets — empty datalake + artifacts first)
#
# Side effects (all destructive):
#   - Deletes every object in s3://wistia-datalake-<acct>-us-east-1/
#   - Deletes every object in s3://wistia-artifacts-<acct>-us-east-1/
#   - Deletes every image in ECR repo wistia-prod-dashboard
#   - Deletes 5 CloudFormation stacks
#
# Cost impact after a clean tear-down: ~$0/day.

param(
    [switch]$WhatIf,
    [switch]$Force,
    [string]$Env = "prod",
    [string]$Region = "us-east-1"
)

$ErrorActionPreference = 'Stop'

$AccountId   = aws sts get-caller-identity --query Account --output text
if ($LASTEXITCODE -ne 0) { exit 1 }

$DataLake    = "wistia-datalake-$AccountId-$Region"
$Artifacts   = "wistia-artifacts-$AccountId-$Region"
$EcrRepo     = "wistia-$Env-dashboard"

# Stacks in reverse dependency order.
$Stacks = @(
    "wistia-monitoring",
    "wistia-dashboard",
    "wistia-transforms",
    "wistia-ingest",
    "wistia-foundation"
)

function Test-StackExists($name) {
    aws cloudformation describe-stacks --stack-name $name --region $Region --query 'Stacks[0].StackName' --output text 2>$null | Out-Null
    return ($LASTEXITCODE -eq 0)
}

function Write-Action($verb, $detail) {
    if ($WhatIf) {
        Write-Host "[WhatIf] would $verb $detail" -ForegroundColor Yellow
    } else {
        Write-Host "==> $verb $detail" -ForegroundColor Cyan
    }
}

Write-Host ""
Write-Host "Wistia Phase 3 tear-down" -ForegroundColor Green
Write-Host "  Account : $AccountId"
Write-Host "  Region  : $Region"
Write-Host "  Env     : $Env"
if ($WhatIf) {
    Write-Host "  Mode    : DRY RUN (no resources will be modified)" -ForegroundColor Yellow
} else {
    Write-Host "  Mode    : LIVE  (irreversible)" -ForegroundColor Red
}
Write-Host ""

if (-not $WhatIf -and -not $Force) {
    $answer = Read-Host "Type 'teardown' to confirm. Anything else aborts"
    if ($answer -ne 'teardown') {
        Write-Host "Aborted." -ForegroundColor Yellow
        exit 0
    }
}

# -------------------------------------------------------------------------
# Phase A — Empty stateful resources that block stack delete.
# -------------------------------------------------------------------------

Write-Action "empty" "ECR repo $EcrRepo (deletes all images)"
if (-not $WhatIf) {
    aws ecr describe-repositories --repository-names $EcrRepo --region $Region 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
        $imageIds = aws ecr list-images --repository-name $EcrRepo --region $Region --query 'imageIds' --output json
        if ($imageIds -and $imageIds -ne "[]") {
            aws ecr batch-delete-image --repository-name $EcrRepo --region $Region --image-ids "$imageIds" | Out-Null
            if ($LASTEXITCODE -ne 0) { exit 1 }
        }
    } else {
        Write-Host "    (repo not present; skipping)" -ForegroundColor DarkGray
    }
}

Write-Action "empty" "s3://$DataLake (recursive)"
if (-not $WhatIf) {
    aws s3 ls "s3://$DataLake" --region $Region 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
        aws s3 rm "s3://$DataLake" --recursive --region $Region | Out-Null
        if ($LASTEXITCODE -ne 0) { exit 1 }
    } else {
        Write-Host "    (bucket not present; skipping)" -ForegroundColor DarkGray
    }
}

Write-Action "empty" "s3://$Artifacts (recursive)"
if (-not $WhatIf) {
    aws s3 ls "s3://$Artifacts" --region $Region 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
        aws s3 rm "s3://$Artifacts" --recursive --region $Region | Out-Null
        if ($LASTEXITCODE -ne 0) { exit 1 }
    } else {
        Write-Host "    (bucket not present; skipping)" -ForegroundColor DarkGray
    }
}

# -------------------------------------------------------------------------
# Phase B — Delete stacks in reverse order. Each delete is fire-and-wait
# so we don't try to delete the next stack while CFN is still removing
# resources the next one imports from.
# -------------------------------------------------------------------------

foreach ($stack in $Stacks) {
    if (-not (Test-StackExists $stack)) {
        Write-Host "==> skip $stack (not present)" -ForegroundColor DarkGray
        continue
    }

    Write-Action "delete-stack" $stack
    if (-not $WhatIf) {
        aws cloudformation delete-stack --stack-name $stack --region $Region
        if ($LASTEXITCODE -ne 0) { exit 1 }

        Write-Host "    waiting for $stack to disappear..." -ForegroundColor DarkGray
        aws cloudformation wait stack-delete-complete --stack-name $stack --region $Region
        if ($LASTEXITCODE -ne 0) {
            Write-Host "    delete failed for $stack — inspect via the console" -ForegroundColor Red
            exit 1
        }
        Write-Host "    $stack deleted" -ForegroundColor Green
    }
}

Write-Host ""
if ($WhatIf) {
    Write-Host "Dry run complete. Re-run without -WhatIf to actually tear down." -ForegroundColor Yellow
} else {
    Write-Host "All Wistia Phase 3 stacks deleted. Daily run rate: ~`$0/day." -ForegroundColor Green
}
