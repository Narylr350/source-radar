param(
    [Parameter(Position = 0)]
    [string] $Command = "--help",

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
        Invoke-SourceRadarPython @("-m", "source_radar", "install")
    }
    "ask" {
        $PythonArgs = @("-m", "source_radar", "ask") + $Rest + @("--local-services")
        if ($Rest -notcontains "--progress") {
            $PythonArgs += "--progress"
        }
        Invoke-SourceRadarPython $PythonArgs
    }
    "verify" {
        $PythonArgs = @("-m", "source_radar", "verify") + $Rest + @("--local-services")
        if ($Rest -notcontains "--format") {
            $PythonArgs += @("--format", "markdown")
        }
        if ($Rest -notcontains "--progress") {
            $PythonArgs += "--progress"
        }
        Invoke-SourceRadarPython $PythonArgs
    }
    "mcp-sse" {
        & (Join-Path $Root "start-mcp-sse.ps1") @Rest
        exit $LASTEXITCODE
    }
    default {
        $PythonArgs = @("-m", "source_radar", $Command) + $Rest
        Invoke-SourceRadarPython $PythonArgs
    }
}
