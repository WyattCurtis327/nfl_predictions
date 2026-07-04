param(
    [string]$Scope = "nfl",
    [string]$Profile = ""
)

# Check if Databricks CLI is installed
if (-not (Get-Command databricks -ErrorAction SilentlyContinue)) {
    Write-Error "Databricks CLI not found."
    exit 1
}

if (-not $Profile) {
    if ($env:DATABRICKS_CONFIG_PROFILE) {
        $Profile = $env:DATABRICKS_CONFIG_PROFILE
    } elseif ($env:databricks_profile) {
        $Profile = $env:databricks_profile
    }
}

$profileArgs = @()
if ($Profile) {
    $profileArgs = @("--profile", $Profile)
}

# Create secret scope (positional scope name in CLI v0.200+)
Write-Host "Creating secret scope: $Scope" -ForegroundColor Cyan
$create = & databricks @profileArgs secrets create-scope $Scope 2>&1
if ($LASTEXITCODE -ne 0 -and $create -notmatch "RESOURCE_ALREADY_EXISTS") {
    Write-Error $create
    exit $LASTEXITCODE
}
Write-Host "Secret scope ready" -ForegroundColor Green

Write-Host "`nEnter secret values (press Enter to skip):" -ForegroundColor Cyan

$secrets = @(
    @{ Name = "odds_api_key"; Prompt = "The Odds API key (live weekly odds only)" }
)

foreach ($secret in $secrets) {
    $value = Read-Host "  $($secret.Prompt)"
    if ($value) {
        & databricks @profileArgs secrets put-secret $Scope $secret.Name --string-value $value
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Failed to store $($secret.Name)"
            exit $LASTEXITCODE
        }
        Write-Host "    Added: $($secret.Name)" -ForegroundColor Green
    }
}

Write-Host "`nDone! Use in notebooks:" -ForegroundColor Green
Write-Host "api_key = dbutils.secrets.get(scope='$Scope', key='odds_api_key')"
Write-Host "`nOr run without prompts:" -ForegroundColor Cyan
Write-Host "python scripts/set_odds_api_secret.py --profile $Profile"