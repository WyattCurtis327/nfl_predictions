# Install official Databricks AI dev skills for Grok Build in this project.
#
# Usage (from repo root):
#   powershell -File scripts/install_databricks_grok_skills.ps1
#   powershell -File scripts/install_databricks_grok_skills.ps1 -Profile DEFAULT

param(
    [string]$Profile = $env:DATABRICKS_CONFIG_PROFILE
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$SkillsRoot = Join-Path $RepoRoot ".grok\skills"
$CanonicalRoot = Join-Path $env:USERPROFILE ".databricks\aitools\skills"
$AiDevKitVenvPython = Join-Path $env:USERPROFILE ".ai-dev-kit\.venv\Scripts\python.exe"
$McpEntry = Join-Path $env:USERPROFILE ".ai-dev-kit\repo\databricks-mcp-server\run_server.py"
$GrokConfig = Join-Path $RepoRoot ".grok\config.toml"

if (-not (Get-Command databricks -ErrorAction SilentlyContinue)) {
    throw "Databricks CLI not found. Install it first: https://docs.databricks.com/dev-tools/cli/"
}

Write-Host "Installing/updating official Databricks skills (global canonical store)..."
& databricks aitools install --scope=global | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "databricks aitools install failed with exit code $LASTEXITCODE"
}

if (-not (Test-Path $CanonicalRoot)) {
    throw "Canonical skills directory not found: $CanonicalRoot"
}

New-Item -ItemType Directory -Force -Path $SkillsRoot | Out-Null

$linked = 0
Get-ChildItem -Path $CanonicalRoot -Directory | ForEach-Object {
    $skillName = $_.Name
    if ($skillName.StartsWith(".")) {
        return
    }
    if (-not (Test-Path (Join-Path $_.FullName "SKILL.md"))) {
        return
    }

    $target = Join-Path $SkillsRoot $skillName
    if (Test-Path $target) {
        $item = Get-Item $target -Force
        if ($item.LinkType -in @("Junction", "SymbolicLink")) {
            Remove-Item $target -Force
        }
        else {
            throw "Refusing to overwrite non-link path: $target"
        }
    }

    New-Item -ItemType Junction -Path $target -Target $_.FullName | Out-Null
    $linked++
}

Write-Host "Linked $linked Databricks skills into $SkillsRoot"

if ((Test-Path $AiDevKitVenvPython) -and (Test-Path $McpEntry)) {
    $profileValue = $Profile
    if ([string]::IsNullOrWhiteSpace($profileValue)) {
        $profileValue = [Environment]::GetEnvironmentVariable("databricks_profile")
    }
    if ([string]::IsNullOrWhiteSpace($profileValue)) {
        $profileValue = [Environment]::GetEnvironmentVariable("DATABRICKS_CONFIG_PROFILE")
    }
    if ([string]::IsNullOrWhiteSpace($profileValue)) {
        throw "Set -Profile or DATABRICKS_CONFIG_PROFILE / databricks_profile before configuring MCP."
    }
    $pythonPath = $AiDevKitVenvPython.Replace("\", "/")
    $mcpPath = $McpEntry.Replace("\", "/")

    $mcpBlock = @"

[mcp_servers.databricks]
command = "$pythonPath"
args = ["$mcpPath"]
env = { DATABRICKS_CONFIG_PROFILE = "$profileValue" }
"@

    if (Test-Path $GrokConfig) {
        $existing = Get-Content $GrokConfig -Raw
        if ($existing -notmatch "\[mcp_servers\.databricks\]") {
            Add-Content -Path $GrokConfig -Value $mcpBlock
            Write-Host "Appended Databricks MCP server to $GrokConfig"
        }
        else {
            Write-Host "Databricks MCP server already configured in $GrokConfig"
        }
    }
    else {
        New-Item -ItemType Directory -Force -Path (Split-Path $GrokConfig) | Out-Null
        Set-Content -Path $GrokConfig -Value $mcpBlock.TrimStart()
        Write-Host "Created $GrokConfig with Databricks MCP server"
    }
}
else {
    Write-Warning "Databricks AI Dev Kit MCP server not found at ~/.ai-dev-kit. Skills are installed; run the AI Dev Kit installer to enable MCP tools."
}

Write-Host "Done. Restart or reload Grok to pick up project skills."