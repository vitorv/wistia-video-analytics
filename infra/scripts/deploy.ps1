# Wistia Phase 3 — CloudFormation deploy wrapper.
#
# Usage:
#   ./infra/scripts/deploy.ps1 -Stack foundation
#   ./infra/scripts/deploy.ps1 -Stack foundation -Env prod
#
# Stack names map to templates in `infra/cloudformation/<stack>.yaml`.
# Each PR in Phase 3 adds one stack (foundation -> ingest -> transforms ->
# dashboard -> monitoring), so this script grows valid -Stack values over time.

param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('foundation', 'ingest', 'transforms', 'dashboard', 'monitoring')]
    [string]$Stack,

    [string]$Env = 'prod'
)

$ErrorActionPreference = 'Stop'

$Template  = Join-Path $PSScriptRoot "..\cloudformation\$Stack.yaml"
$StackName = "wistia-$Stack"

if (-not (Test-Path $Template)) {
    Write-Error "Template not found: $Template"
    exit 1
}

Write-Host "==> Validating $Template"
aws cloudformation validate-template --template-body file://$Template | Out-Null
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host "==> Deploying $StackName (Env=$Env)"
aws cloudformation deploy `
    --stack-name $StackName `
    --template-file $Template `
    --parameter-overrides Env=$Env `
    --capabilities CAPABILITY_NAMED_IAM

if ($LASTEXITCODE -ne 0) {
    Write-Error "Deploy failed for $StackName"
    exit 1
}

Write-Host ""
Write-Host "==> Stack $StackName deployed. Outputs:"
aws cloudformation describe-stacks `
    --stack-name $StackName `
    --query 'Stacks[0].Outputs[].[OutputKey,OutputValue]' `
    --output table
