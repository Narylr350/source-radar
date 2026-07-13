param(
    [int]$Port = 8765,
    [string]$BindHost = "127.0.0.1"
)

$ErrorActionPreference = "Stop"
$processPattern = "*source-radar.ps1*mcp*--transport*sse*"

function Test-TcpPort {
    param([string]$HostName, [int]$PortNumber)

    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $connect = $client.ConnectAsync($HostName, $PortNumber)
        return $connect.Wait(500) -and $client.Connected
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

# Check if already running
$existing = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq "powershell.exe" -and
    $_.CommandLine -like $processPattern -and
    $_.ProcessId -ne $PID
}
if ($existing) {
    Write-Host "SSE MCP server already running (PID $($existing.ProcessId))" -ForegroundColor Green
    exit 0
}
if (Test-TcpPort -HostName $BindHost -PortNumber $Port) {
    Write-Host "Port ${BindHost}:$Port is already in use." -ForegroundColor Red
    exit 1
}

# Find project root
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$wrapper = Join-Path $scriptDir "source-radar.ps1"
if (-not $env:SOURCE_RADAR_CONFIG_DIR) {
    $env:SOURCE_RADAR_CONFIG_DIR = Join-Path $scriptDir ".source-radar"
}

Write-Host "Starting SSE MCP server on ${BindHost}:$Port..." -ForegroundColor Cyan
Start-Process -FilePath "powershell.exe" `
    -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$wrapper`"", "mcp", "--transport", "sse", "--host", $BindHost, "--port", $Port `
    -WorkingDirectory $scriptDir `
    -WindowStyle Hidden `
    -RedirectStandardError "$env:TEMP\source-radar-mcp-sse.err" `
    -RedirectStandardOutput "$env:TEMP\source-radar-mcp-sse.out"

Start-Sleep -Seconds 2

# Verify it started
$check = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq "powershell.exe" -and
    $_.CommandLine -like $processPattern -and
    $_.ProcessId -ne $PID
}
if ($check -and (Test-TcpPort -HostName $BindHost -PortNumber $Port)) {
    Write-Host "SSE MCP server started (PID $($check.ProcessId))" -ForegroundColor Green
    Write-Host "URL: http://${BindHost}:$Port/sse" -ForegroundColor Cyan
} else {
    Write-Host "Failed to start. Check logs:" -ForegroundColor Red
    Get-Content "$env:TEMP\source-radar-mcp-sse.err" -ErrorAction SilentlyContinue | Select-Object -First 5
    exit 1
}
