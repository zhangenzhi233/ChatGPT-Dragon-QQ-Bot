[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$maiBotRoot = Join-Path $projectRoot 'work\compatible-release\MaiBot-1.2.5'
$localRoot = Join-Path $projectRoot 'work\qq-ai-local'
$pythonExe = Join-Path $maiBotRoot '.venv\Scripts\python.exe'
$setupPath = Join-Path $localRoot 'setup.json'
$bridgeKeyPath = Join-Path $localRoot 'bridge-key.txt'
$logPath = Join-Path $localRoot 'maibot.log'
$pidPath = Join-Path $localRoot 'maibot.pid'
$agreementPath = Join-Path $localRoot 'maibot-1.2.5-agreement-confirmed.json'

if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'MaiBot 虚拟环境不存在。请先完成本机部署。' }
if (-not (Test-Path -LiteralPath $setupPath)) { throw '尚未保存本机设置。请先在 127.0.0.1:8711 完成设置。' }
if (-not (Test-Path -LiteralPath $bridgeKeyPath)) { throw '本机模型桥接密钥不存在。请先运行 configure-maibot.py。' }

$setup = Get-Content -LiteralPath $setupPath -Raw | ConvertFrom-Json
if ($setup.agreementsAccepted -ne $true -or [string]::IsNullOrWhiteSpace($setup.selectedModel)) { throw '本机设置未完成协议确认或模型选择。' }

try {
    $bridgeKey = (Get-Content -LiteralPath $bridgeKeyPath -Raw).Trim()
    $bridge = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8711/v1/models' -Headers @{ Authorization = "Bearer $bridgeKey" } -TimeoutSec 30
    if ($bridge.StatusCode -ne 200) { throw '模型桥接未就绪。' }
} catch { throw '模型桥接未就绪；请保持 QQ AI 本机设置服务运行。' }

$napcatReady = Get-NetTCPConnection -State Listen -LocalAddress '127.0.0.1' -LocalPort 3011 -ErrorAction SilentlyContinue
if (-not $napcatReady) { throw 'NapCat 正向 WebSocket 尚未在 127.0.0.1:3011 监听。请先完成专用 QQ 小号扫码。' }

if (Test-Path -LiteralPath $pidPath) {
    $existingPid = (Get-Content -LiteralPath $pidPath -Raw).Trim()
    if ($existingPid -match '^\d+$') {
        $existingProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$existingPid" -ErrorAction SilentlyContinue
        if ($existingProcess -and $existingProcess.Name -in @('powershell.exe', 'pwsh.exe') -and
            $existingProcess.CommandLine.Contains($maiBotRoot, [StringComparison]::OrdinalIgnoreCase) -and
            $existingProcess.CommandLine.Contains($pythonExe, [StringComparison]::OrdinalIgnoreCase) -and
            $existingProcess.CommandLine -match 'bot\.py') {
            throw 'MaiBot 已在运行。'
        }
    }
}

# The setup page recorded the user's acceptance of this exact MaiBot release.
# MaiBot itself expects text-MD5 markers; issue them only after verifying both
# accepted SHA-256 hashes against the files currently on disk.
if (-not (Test-Path -LiteralPath $agreementPath)) { throw '缺少本机许可确认记录。请先在设置页阅读并确认 MaiBot 许可及隐私条款。' }
$agreement = Get-Content -LiteralPath $agreementPath -Raw | ConvertFrom-Json
if ($agreement.maibotVersion -ne '1.2.5' -or $agreement.acceptedVia -ne 'local-setup-page') { throw 'MaiBot 许可确认记录与当前版本不匹配。' }
foreach ($agreementFile in @('EULA.md', 'PRIVACY.md')) {
    $sourcePath = Join-Path $maiBotRoot $agreementFile
    $currentSha = (Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash.ToLowerInvariant()
    $recordSha = [string]$agreement.agreementHashes.PSObject.Properties[$agreementFile].Value
    $setupSha = [string]$setup.agreementHashes.PSObject.Properties[$agreementFile].Value
    if ($currentSha -ne $recordSha -or $currentSha -ne $setupSha) { throw 'MaiBot 协议文件与用户已确认版本不一致。请在设置页重新阅读并确认。' }
    $contents = [IO.File]::ReadAllText($sourcePath, [Text.Encoding]::UTF8)
    $textMd5 = [Convert]::ToHexString([Security.Cryptography.MD5]::HashData([Text.Encoding]::UTF8.GetBytes($contents))).ToLowerInvariant()
    $markerName = if ($agreementFile -eq 'EULA.md') { 'eula.confirmed' } else { 'privacy.confirmed' }
    [IO.File]::WriteAllText((Join-Path $maiBotRoot $markerName), $textMd5, [Text.UTF8Encoding]::new($false))
}

$command = "`$env:PYTHONUTF8='1'; `$env:PYTHONIOENCODING='utf-8'; `$env:MAIBOT_ENABLE_CONSOLE_INPUT='0'; `$loopbackBypass = @(`$env:NO_PROXY, `$env:no_proxy, '127.0.0.1', 'localhost', '::1') | Where-Object { `$_ } | Select-Object -Unique; `$env:NO_PROXY = (`$loopbackBypass -join ','); `$env:no_proxy = `$env:NO_PROXY; Set-Location -LiteralPath '$maiBotRoot'; & '$pythonExe' '.\bot.py' *>> '$logPath'"
$process = Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoProfile', '-NonInteractive', '-WindowStyle', 'Hidden', '-Command', $command) -WindowStyle Hidden -PassThru
$process.Id | Set-Content -LiteralPath $pidPath -Encoding ascii
Write-Output 'MaiBot 已在后台启动；日志位于 work\qq-ai-local\maibot.log。'
