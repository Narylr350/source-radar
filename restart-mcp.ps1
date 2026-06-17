param(
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$selfPid = $PID
$maxRounds = 5

Write-Host "Killing source-radar MCP processes..." -ForegroundColor Yellow

function Get-SourceRadarMcpProcesses {
    @(
        Get-CimInstance Win32_Process |
        Where-Object {
            $cmd = $_.CommandLine
            $cmd -and
            $_.ProcessId -ne $selfPid -and
            ($cmd -like "*source-radar*mcp*" -or $cmd -like "*source_radar*mcp*") -and
            $cmd -notlike "*restart-mcp.ps1*"
        }
    )
}

$killed = 0
$seen = @{}

for ($round = 1; $round -le $maxRounds; $round++) {
    $targets = @(Get-SourceRadarMcpProcesses)
    if ($targets.Count -eq 0) {
        if ($round -eq 1) {
            Write-Host "No MCP processes found." -ForegroundColor Cyan
        }
        break
    }

    Write-Host "Round ${round}: found $($targets.Count) MCP process(es)." -ForegroundColor Yellow
    foreach ($process in $targets) {
        if ($seen.ContainsKey([string]$process.ProcessId)) {
            continue
        }
        $seen[[string]$process.ProcessId] = $true
        $short = if ($process.CommandLine.Length -gt 100) {
            $process.CommandLine.Substring(0, 100) + "..."
        } else {
            $process.CommandLine
        }
        if ($DryRun) {
            Write-Host "  Would kill PID $($process.ProcessId): $short" -ForegroundColor Cyan
        } else {
            Write-Host "  Killing PID $($process.ProcessId): $short"
            try {
                Stop-Process -Id $process.ProcessId -Force -ErrorAction Stop
                $killed++
            } catch {
                Write-Host "  PID $($process.ProcessId) already exited; skipping." -ForegroundColor DarkGray
            }
        }
    }

    if ($DryRun) {
        break
    }

    Start-Sleep -Milliseconds 300
}

$remaining = @(Get-SourceRadarMcpProcesses)
if ($DryRun) {
    Write-Host "Dry run complete. $($seen.Count) process(es) would be killed." -ForegroundColor Cyan
} elseif ($remaining.Count -gt 0) {
    Write-Host "Remaining MCP processes after cleanup:" -ForegroundColor Red
    foreach ($process in $remaining) {
        Write-Host "  PID $($process.ProcessId): $($process.CommandLine)" -ForegroundColor Red
    }
    exit 1
} else {
    Write-Host "Killed $killed process(es). No source-radar MCP processes remain." -ForegroundColor Green
    Write-Host "Claude Code must reconnect or make a new MCP tool call to start a fresh stdio MCP process." -ForegroundColor Cyan
}
