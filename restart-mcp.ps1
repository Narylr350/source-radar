param(
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$selfPid = $PID

Write-Host "Killing source-radar MCP processes..." -ForegroundColor Yellow

$targets = @(
    Get-CimInstance Win32_Process |
        Where-Object {
            $cmd = $_.CommandLine
            $cmd -and
            $_.ProcessId -ne $selfPid -and
            ($cmd -like "*source-radar*mcp*" -or $cmd -like "*source_radar*mcp*") -and
            $cmd -notlike "*restart-mcp.ps1*"
        }
)

if ($targets.Count -eq 0) {
    Write-Host "No MCP processes found." -ForegroundColor Cyan
} else {
    $killed = 0
    foreach ($process in $targets) {
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
        Write-Host "Dry run complete. $($targets.Count) process(es) would be killed." -ForegroundColor Cyan
    } else {
        Write-Host "Killed $killed process(es). AI tool will auto-restart MCP on next call." -ForegroundColor Green
    }
}
