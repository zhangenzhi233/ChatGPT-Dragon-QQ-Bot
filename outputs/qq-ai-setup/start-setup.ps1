param([switch]$NoOpenBrowser)
$ErrorActionPreference = 'Stop'
$TaskRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$TaskUrl = 'http://127.0.0.1:8711/'
$TaskRunning = $false
try {
    $TaskPage = Invoke-WebRequest -Uri $TaskUrl -UseBasicParsing -TimeoutSec 2
    if ($TaskPage.Content -notmatch 'QQ AI') { throw 'Port 8711 is used by another application.' }
    $TaskRunning = $true
} catch {
    if ($_.Exception.Message -eq 'Port 8711 is used by another application.') { throw }
}
if (-not $TaskRunning) {
    $TaskNode = (Get-Command node -ErrorAction Stop).Source
    $TaskServer = Join-Path $PSScriptRoot 'server.mjs'
    $TaskLogDirectory = Join-Path $TaskRoot 'work\qq-ai-local'
    New-Item -ItemType Directory -Path $TaskLogDirectory -Force | Out-Null
    # Reuse the user's existing Windows proxy only in this helper's process.
    # Node fetch does not read Windows Internet Settings on its own.
    $TaskNetwork = Get-ItemProperty -LiteralPath 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' -ErrorAction SilentlyContinue
    if ($TaskNetwork.ProxyEnable -eq 1 -and [string]$TaskNetwork.ProxyServer -match '^(127\.0\.0\.1|localhost):[0-9]+$') {
        if (-not $env:HTTPS_PROXY) { $env:HTTPS_PROXY = 'http://' + [string]$TaskNetwork.ProxyServer }
        if (-not $env:HTTP_PROXY) { $env:HTTP_PROXY = 'http://' + [string]$TaskNetwork.ProxyServer }
    }
    $env:NO_PROXY = (@('127.0.0.1','localhost','::1', $env:NO_PROXY) | Where-Object { $_ }) -join ','
    $TaskProcess = Start-Process -FilePath $TaskNode -ArgumentList @('--use-env-proxy', ('"' + $TaskServer + '"')) -WindowStyle Hidden -WorkingDirectory $TaskRoot -RedirectStandardOutput (Join-Path $TaskLogDirectory 'setup-server.stdout.log') -RedirectStandardError (Join-Path $TaskLogDirectory 'setup-server.stderr.log') -PassThru
    [IO.File]::WriteAllText((Join-Path $TaskLogDirectory 'setup-server.pid'), [string]$TaskProcess.Id)
    $TaskStarted = $false
    for ($TaskAttempt = 0; $TaskAttempt -lt 30; $TaskAttempt++) {
        Start-Sleep -Milliseconds 400
        if ($TaskProcess.HasExited) { throw ('Setup server failed. See ' + (Join-Path $TaskLogDirectory 'setup-server.stderr.log')) }
        try {
            $TaskPage = Invoke-WebRequest -Uri $TaskUrl -UseBasicParsing -TimeoutSec 1
            if ($TaskPage.StatusCode -eq 200 -and $TaskPage.Content -match 'QQ AI') { $TaskStarted = $true; break }
        } catch {}
    }
    if (-not $TaskStarted) { throw 'Setup server did not become ready. Check the log directory.' }
}
if (-not $NoOpenBrowser) { Start-Process -FilePath $TaskUrl }
Write-Output ('Ready: ' + $TaskUrl)
