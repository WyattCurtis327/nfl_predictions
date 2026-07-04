# Load environment variables from .env file
param(
    [string]$EnvFilePath = ".env"
)

if (-not (Test-Path $EnvFilePath)) {
    Write-Error ".env file not found at $EnvFilePath"
    exit 1
}

Get-Content $EnvFilePath | ForEach-Object {
    # Skip empty lines and comments
    if ($_ -match '^\s*$' -or $_ -match '^\s*#') {
        return
    }
    
    # Parse KEY=VALUE
    if ($_ -match '^\s*([^=]+)=(.*)$') {
        $key = $matches[1].Trim()
        $value = $matches[2].Trim()
        
        # Remove surrounding quotes if present
        $value = $value -replace '^["'']|["'']$', ''
        
        [Environment]::SetEnvironmentVariable($key, $value)
        Write-Host "✓ Set $key"
    }
}

Write-Host "Environment variables loaded from $EnvFilePath"
