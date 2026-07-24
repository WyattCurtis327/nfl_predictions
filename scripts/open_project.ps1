# Open nfl_predictions as the IDE workspace root (Cursor or VS Code).
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$workspace = Join-Path $repoRoot "nfl_predictions.code-workspace"

$cursor = @(
    "$env:LOCALAPPDATA\Programs\cursor\Cursor.exe",
    "$env:LOCALAPPDATA\Programs\Cursor\Cursor.exe",
    "$env:ProgramFiles\Cursor\Cursor.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if ($cursor) {
    Start-Process -FilePath $cursor -ArgumentList @($workspace)
    exit 0
}

$code = Get-Command code -ErrorAction SilentlyContinue
if ($code) {
    & code $workspace
    exit 0
}

Write-Host "Open this file in Cursor/VS Code: $workspace"
Write-Host "Or use File -> Open Folder -> $repoRoot"
