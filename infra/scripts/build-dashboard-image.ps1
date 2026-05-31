# Wistia Phase 3 — Build the dashboard Docker image and push to ECR.
#
# Usage:
#   ./infra/scripts/build-dashboard-image.ps1
#   ./infra/scripts/build-dashboard-image.ps1 -NoCache
#
# Prereqs:
#   - Docker Desktop running (engine reachable via `docker version`).
#   - The dashboard CFN stack deployed once with DeployService=false so the
#     ECR repository exists.
#   - AWS CLI authenticated as a user/role with ECR push permissions.
#
# Pushes two tags so we have a rollback story:
#   - :latest        — what the ECS task definition pulls
#   - :<git-sha>     — immutable pointer to the exact commit built
#
# After a successful push, ECS doesn't auto-deploy. Either:
#   - Re-run `aws cloudformation deploy ... DeployService=true` for the
#     first deploy, or
#   - Run `aws ecs update-service --force-new-deployment` to roll the
#     existing service onto the new :latest.

param(
    [string]$Env = "prod",
    [string]$Region = "us-east-1",
    [switch]$NoCache
)

$ErrorActionPreference = 'Stop'

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path

Write-Host "==> Checking Docker daemon"
docker version --format '{{.Server.Version}}' | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Error "Docker daemon not reachable. Start Docker Desktop and retry."
    exit 1
}

Write-Host "==> Resolving AWS account + ECR repository URI"
$AccountId = aws sts get-caller-identity --query Account --output text
if ($LASTEXITCODE -ne 0) { exit 1 }
$RegistryHost = "$AccountId.dkr.ecr.$Region.amazonaws.com"
$RepoName     = "wistia-$Env-dashboard"
$RepoUri      = "$RegistryHost/$RepoName"

Write-Host "    Registry : $RegistryHost"
Write-Host "    Repo     : $RepoName"

Write-Host "==> Verifying ECR repository exists"
aws ecr describe-repositories --repository-names $RepoName --region $Region | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Error "ECR repo '$RepoName' not found. Deploy the dashboard CFN stack first (DeployService=false is fine)."
    exit 1
}

Write-Host "==> Resolving git short SHA"
$GitSha = (git -C $RepoRoot rev-parse --short HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or -not $GitSha) {
    Write-Error "Failed to read git short SHA. Are you in a git repo?"
    exit 1
}
Write-Host "    SHA: $GitSha"

Write-Host "==> Docker login to ECR"
# Pipe the token through cmd.exe, not PowerShell. Capturing the token in a
# PowerShell variable and piping it appends a trailing newline that ECR
# rejects with HTTP 400 ("login attempt failed"). cmd.exe streams bytes
# without rewriting line endings.
cmd /c "aws ecr get-login-password --region $Region | docker login --username AWS --password-stdin $RegistryHost"
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host "==> Building image (this can take a few minutes on first run)"
$BuildArgs = @("build")
if ($NoCache) { $BuildArgs += "--no-cache" }
$BuildArgs += @("-t", "${RepoUri}:latest", "-t", "${RepoUri}:$GitSha", $RepoRoot)
& docker @BuildArgs
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host "==> Pushing :latest"
docker push "${RepoUri}:latest"
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host "==> Pushing :$GitSha"
docker push "${RepoUri}:$GitSha"
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host ""
Write-Host "Done. Pushed:"
Write-Host "  ${RepoUri}:latest"
Write-Host "  ${RepoUri}:$GitSha"
Write-Host ""
Write-Host "Next:"
Write-Host "  - First deploy: aws cloudformation deploy ... DeployService=true"
Write-Host "  - Subsequent updates: aws ecs update-service --cluster wistia-$Env-dashboard ``"
Write-Host "      --service wistia-$Env-dashboard --force-new-deployment --region $Region"
