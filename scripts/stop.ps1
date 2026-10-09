[CmdletBinding()]
param([switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
$packageRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$python = Join-Path $packageRoot 'work\compatible-release\MaiBot-1.2.5\.venv\Scripts\python.exe'
$server = Join-Path $packageRoot 'outputs\qq-ai-setup\server.mjs'
$napcat = Join-Path $packageRoot 'runtime\NapCat\NapCatWinBootMain.exe'
$allProcesses = @(Get-CimInstance Win32_Process)
$owned = @($allProcesses | Where-Object {
    ($_.ExecutablePath -eq $python -and $_.CommandLine -match '(^|[\\/"\s])bot\.py(["\s]|$)') -or
    ($_.Name -eq 'node.exe' -and $_.CommandLine -and $_.CommandLine.Contains($server,[StringComparison]::OrdinalIgnoreCase)) -or
    ($_.ExecutablePath -eq $napcat)
})
do {
    $ids = @($owned | ForEach-Object { $_.ProcessId })
    $children = @($allProcesses | Where-Object { $_.ParentProcessId -in $ids -and $_.ProcessId -notin $ids })
    $owned += $children
} while ($children.Count)
if ($CheckOnly) { @{ownedProcesses=$owned.Count;readOnly=$true} | ConvertTo-Json; exit 0 }
foreach ($process in @($owned | Sort-Object CreationDate -Descending)) {
    $current = Get-CimInstance Win32_Process -Filter "ProcessId=$($process.ProcessId)" -ErrorAction SilentlyContinue
    if ($current -and $current.CreationDate -eq $process.CreationDate -and $current.ExecutablePath -eq $process.ExecutablePath) {
        Stop-Process -Id $current.ProcessId -Force -ErrorAction Stop
    }
}
Write-Host ('已停止本目录的受管进程：' + $owned.Count)
