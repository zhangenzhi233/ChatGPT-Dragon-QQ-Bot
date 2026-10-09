[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
# QQ 可执行文件路径与 QQ 进程门禁都取自共享 helper，避免两个启动脚本各写一份判定。
. (Join-Path $PSScriptRoot 'qq-process-guard.ps1')
$utf8NoBom = [Text.UTF8Encoding]::new($false)
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$napCatRoot = Get-QqGuardNapCatRoot
$localRoot = Join-Path $projectRoot 'work\qq-ai-local'
$setupPath = Join-Path $localRoot 'setup.json'
$webUiKeyPath = Join-Path $localRoot 'napcat-webui-key.txt'
$oneBotTokenPath = Join-Path $localRoot 'napcat-token.txt'
$webUiConfigPath = Join-Path $napCatRoot 'config\webui.json'
$pidPath = Join-Path $localRoot 'napcat.pid'
$stdoutPath = Join-Path $localRoot 'napcat.stdout.log'
$stderrPath = Join-Path $localRoot 'napcat.stderr.log'
$qqExe = Get-QqGuardExePath
$launcher = Join-Path $napCatRoot 'NapCatWinBootMain.exe'
$hook = Join-Path $napCatRoot 'NapCatWinBootHook.dll'

foreach ($path in @($napCatRoot, $localRoot, $qqExe, $launcher, $hook, $setupPath)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "NapCat 启动所需文件不存在。" }
}
$setup = Get-Content -LiteralPath $setupPath -Raw | ConvertFrom-Json
$botQQ = [string]$setup.botQQ
if ($botQQ -notmatch '^\d{5,15}$') { throw '本机机器人 QQ 号尚未正确保存。' }

if (Test-Path -LiteralPath $pidPath) {
    $existingPid = (Get-Content -LiteralPath $pidPath -Raw).Trim()
    if ($existingPid -match '^\d+$') {
        $existingProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$existingPid" -ErrorAction SilentlyContinue
        # Windows may reuse a saved PID after reboot. Only the exact launcher
        # belonging to this deployment is evidence of an existing instance.
        if ($existingProcess -and $existingProcess.ExecutablePath -eq $launcher) {
            throw '受控 NapCat 已在运行，拒绝重复启动。'
        }
    }
}
$managedNapCat = @(Get-CimInstance Win32_Process -Filter "Name='NapCatWinBootMain.exe'" -ErrorAction SilentlyContinue | Where-Object {
    $_.ExecutablePath -eq $launcher
})
if ($managedNapCat.Count -gt 0) { throw '受控 NapCat 已在运行，拒绝重复启动。' }
# 只拦截本机器人将要启动的同一绝对路径 QQ；其它目录安装的 QQ 允许共存。
# 路径读不出来的同名进程按“无法核验”拒绝，不假定安全。
$null = Assert-QqGuardProcessGate -TargetExePath $qqExe

function Get-OrCreateSecret([string]$Path) {
    if (Test-Path -LiteralPath $Path) {
        $existing = (Get-Content -LiteralPath $Path -Raw).Trim()
        if ($existing.Length -ge 24) { return $existing }
    }
    $bytes = New-Object byte[] 32
    [Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    $value = [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+','-').Replace('/','_')
    [IO.File]::WriteAllText($Path, $value, [Text.Encoding]::ASCII)
    return $value
}
$webUiKey = Get-OrCreateSecret $webUiKeyPath
$null = Get-OrCreateSecret $oneBotTokenPath

function Set-ConfigValue($Object, [string]$Name, $Value) {
    if ($Object.PSObject.Properties.Name -contains $Name) { $Object.$Name = $Value }
    else { $Object | Add-Member -NotePropertyName $Name -NotePropertyValue $Value }
}

# Reapply the local-only WebUI boundary on every fresh boot. The random local key
# remains stable so the companion manager can authenticate without printing it.
$webUiConfig = if (Test-Path -LiteralPath $webUiConfigPath) {
    Get-Content -LiteralPath $webUiConfigPath -Raw | ConvertFrom-Json
} else { [PSCustomObject]@{} }
Set-ConfigValue $webUiConfig 'host' '127.0.0.1'
Set-ConfigValue $webUiConfig 'port' 6109
Set-ConfigValue $webUiConfig 'disableWebUI' $false
Set-ConfigValue $webUiConfig 'token' $webUiKey
Set-ConfigValue $webUiConfig 'autoLoginAccount' $botQQ
[IO.File]::WriteAllText($webUiConfigPath, ($webUiConfig | ConvertTo-Json -Depth 32), $utf8NoBom)

# Do not retain any network listener/client across a restart. enableVerifiedWs()
# is the only path that may add the checked local WebSocket after QQ login.
Get-ChildItem -LiteralPath (Join-Path $napCatRoot 'config') -Filter 'onebot11*.json' -File | ForEach-Object {
    $oneBotConfig = Get-Content -LiteralPath $_.FullName -Raw | ConvertFrom-Json
    if (-not ($oneBotConfig.PSObject.Properties.Name -contains 'network')) {
        $oneBotConfig | Add-Member -NotePropertyName 'network' -NotePropertyValue ([PSCustomObject]@{})
    }
    foreach ($networkName in @('httpServers', 'httpSseServers', 'httpClients', 'websocketServers', 'websocketClients', 'plugins')) {
        Set-ConfigValue $oneBotConfig.network $networkName @()
    }
    [IO.File]::WriteAllText($_.FullName, ($oneBotConfig | ConvertTo-Json -Depth 32), $utf8NoBom)
}

$childEnv = @{}
Get-ChildItem Env: | ForEach-Object { $childEnv[$_.Name] = $_.Value }
# Confine account/cache directories to this QQ child process only.
$qqProfileRoot = Join-Path (Split-Path $napCatRoot -Parent) 'QQ-profile'
$qqRoaming = Join-Path $qqProfileRoot 'AppData\Roaming'
$qqLocal = Join-Path $qqProfileRoot 'AppData\Local'
New-Item -ItemType Directory -Path $qqRoaming, $qqLocal -Force | Out-Null
$childEnv['APPDATA'] = $qqRoaming
$childEnv['LOCALAPPDATA'] = $qqLocal
$childEnv['NAPCAT_PATCH_PACKAGE'] = Join-Path $napCatRoot 'qqnt.json'
$childEnv['NAPCAT_LOAD_PATH'] = Join-Path $napCatRoot 'loadNapCat.js'
$childEnv['NAPCAT_INJECT_PATH'] = $hook
$childEnv['NAPCAT_MAIN_PATH'] = Join-Path $napCatRoot 'napcat.mjs'
$childEnv['NAPCAT_WORKDIR'] = $napCatRoot
$childEnv['NAPCAT_WEBUI_PREFERRED_PORT'] = '6109'
$childEnv['NAPCAT_WEBUI_SECRET_KEY'] = $webUiKey
$childEnv['NAPCAT_QUICK_ACCOUNT'] = $botQQ
$loadUrl = 'file:///' + ($childEnv['NAPCAT_MAIN_PATH'] -replace '\\','/')
[IO.File]::WriteAllText($childEnv['NAPCAT_LOAD_PATH'], "(async () => {await import('$loadUrl')})()", $utf8NoBom)
# The bootstrap adds -q itself and consumes one account/QQ-options argument.
# Keep the QQ options together; disable GPU as in the working local QQ instance.
$qqProfile = Join-Path (Split-Path $napCatRoot -Parent) 'QQ-profile'
New-Item -ItemType Directory -Path $qqProfile -Force | Out-Null
$qqOptionText = $botQQ + ' --disable-gpu --in-process-gpu --user-data-dir="' + $qqProfile + '"'
$bootQqOptions = '"' + $qqOptionText.Replace('"', '\"') + '"'
$process = Start-Process -FilePath $launcher -ArgumentList @(('"' + $qqExe + '"'), ('"' + $hook + '"'), $bootQqOptions) -WorkingDirectory $napCatRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath -Environment $childEnv
[IO.File]::WriteAllText($pidPath, [string]$process.Id, [Text.Encoding]::ASCII)
Write-Output 'NapCat 已在后台启动，等待小号二维码；日志仅保存在 work\qq-ai-local。'
