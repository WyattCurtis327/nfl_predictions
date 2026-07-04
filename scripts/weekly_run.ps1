# Weekly operator wrapper: stage odds, sync env, build wheel, deploy bundle, run pipeline.
param(
    [string]$Target = "prod",
    [string]$Profile = "",
    [switch]$SkipStageOdds,
    [switch]$SkipMetricView,
    [switch]$DeployOnly
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Resolve-Profile {
    if ($Profile) { return $Profile }
    if ($env:DATABRICKS_CONFIG_PROFILE) { return $env:DATABRICKS_CONFIG_PROFILE }
    if (Test-Path ".env") {
        foreach ($line in Get-Content ".env") {
            if ($line -match '^\s*DATABRICKS_CONFIG_PROFILE=(.+)$') {
                return $Matches[1].Trim().Trim("'").Trim('"')
            }
        }
    }
    throw "Set -Profile or DATABRICKS_CONFIG_PROFILE in .env"
}

$resolvedProfile = Resolve-Profile
$python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Missing .venv. Run: python -m venv .venv; pip install -e `".[dev]`""
}

Write-Host "Syncing Databricks Connect env..."
& $python (Join-Path $Root "scripts\sync_bundle_env.py")

if (-not $SkipStageOdds) {
    Write-Host "Staging live odds..."
    & $python (Join-Path $Root "scripts\stage_odds.py")
}

Write-Host "Building wheel..."
& $python -m pip install -q build
& $python -m build --wheel -o dist

$deployArgs = @("scripts\deploy_bundle.py", $Target)
if ($SkipMetricView) {
    $deployArgs += "--skip-metric-view"
}
& $python @deployArgs

if ($DeployOnly) {
    Write-Host "Deploy complete (DeployOnly)."
    exit 0
}

Write-Host "Running nfl_weekly_pipeline on target=$Target profile=$resolvedProfile..."
databricks bundle run nfl_weekly_pipeline -t $Target --profile $resolvedProfile