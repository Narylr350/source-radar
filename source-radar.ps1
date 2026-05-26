param(
    [Parameter(Position = 0)]
    [string] $Command = "help",

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $Rest
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not $env:SOURCE_RADAR_CONFIG_DIR) {
    $env:SOURCE_RADAR_CONFIG_DIR = Join-Path $Root ".source-radar"
}
$env:PYTHONIOENCODING = "utf-8"
$OutputEncoding = [System.Text.UTF8Encoding]::new()
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

function Invoke-SourceRadarPython {
    param([string[]] $PythonArgs)
    if (-not (Test-Path $Python)) {
        Write-Host "Local environment missing. Running setup first..."
        Push-Location $Root
        try {
            uv sync --extra dynamic
        }
        finally {
            Pop-Location
        }
    }
    & $Python @PythonArgs
    exit $LASTEXITCODE
}

switch ($Command) {
    "setup" {
        Push-Location $Root
        try {
            uv sync --extra dynamic
            uv run crawl4ai-setup
            & $Python -m source_radar setup
            exit $LASTEXITCODE
        }
        finally {
            Pop-Location
        }
    }
    "ask" {
        $PythonArgs = @("-m", "source_radar", "ask") + $Rest + @("--local-services")
        Invoke-SourceRadarPython $PythonArgs
    }
    "verify" {
        $PythonArgs = @("-m", "source_radar", "verify") + $Rest
        Invoke-SourceRadarPython $PythonArgs
    }
    "health" {
        $PythonArgs = @("-m", "source_radar", "health") + $Rest
        Invoke-SourceRadarPython $PythonArgs
    }
    "probe" {
        $PythonArgs = @("-m", "source_radar", "probe") + $Rest
        Invoke-SourceRadarPython $PythonArgs
    }
    default {
        Write-Host "Usage:"
        Write-Host "  .\source-radar.ps1 setup"
        Write-Host "  .\source-radar.ps1 ask `"your question`""
        Write-Host "  .\source-radar.ps1 verify `"claim to verify`""
        exit 0
    }
}
