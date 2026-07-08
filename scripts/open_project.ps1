# Open nfl_predictions as the IDE workspace root (Cursor or VS Code).
$workspace = Join-Path $PSScriptRoot "..\nfl_predictions.code-workspace" | Resolve-Path

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

Write-Host "Open this file in Cursor: $workspace"
Write-Host "Or use File -> Open Folder -> C:\Users\wyatt\nfl_predictions"