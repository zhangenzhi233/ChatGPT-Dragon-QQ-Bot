[CmdletBinding()]
param(
    [switch]$NoOpenBrowser,
    [switch]$NoWaitOnExit,
    [switch]$CheckOnly,
    [ValidateRange(30, 900)][int]$LoginTimeoutSec = 300
)

$ErrorActionPreference = 'Stop'

# A double click starts Windows PowerShell; the existing NapCat boot script
# requires PowerShell 7 for its child environment and modern crypto APIs.
if ($PSVersionTable.PSVersion.Major -lt 7) {
    $taskPwsh = Get-Command pwsh -ErrorAction SilentlyContinue
    $taskCandidates = @(
        $(if ($taskPwsh) { $taskPwsh.Source }),
        (Join-Path $env:ProgramFiles 'PowerShell\7\pwsh.exe'),
        ''
    )
    $taskShell = $taskCandidates | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } | Select-Object -First 1
    if (-not $taskShell) { Write-Host '缺少 PowerShell 7，请安装 PowerShell 7.4 或更高版本，并将 pwsh 加入 PATH。'; exit 1 }
    $taskArguments = @('-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $PSCommandPath, '-LoginTimeoutSec', $LoginTimeoutSec)
    foreach ($taskSwitch in @('NoOpenBrowser', 'NoWaitOnExit', 'CheckOnly')) {
        if ($PSBoundParameters[$taskSwitch]) { $taskArguments += "-$taskSwitch" }
    }
    & $taskShell @taskArguments
    exit $LASTEXITCODE
}

# QQ 可执行文件路径与 QQ 进程门禁都取自共享 helper，避免两个启动脚本各写一份判定。
. (Join-Path $PSScriptRoot 'qq-process-guard.ps1')

$taskRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$taskLocal = Join-Path $taskRoot 'work\qq-ai-local'
$taskMai = Join-Path $taskRoot 'work\compatible-release\MaiBot-1.2.5'
$taskPython = Join-Path $taskMai '.venv\Scripts\python.exe'
$taskNapLauncher = Join-Path (Get-QqGuardNapCatRoot) 'NapCatWinBootMain.exe'
$taskQqExe = Get-QqGuardExePath
$taskUrl = 'http://127.0.0.1:8711/#qq-login'
$taskStatePath = Join-Path $taskLocal 'launcher-state.json'
$taskUtf8 = [Text.UTF8Encoding]::new($false)
$taskNode = (Get-Command node -ErrorAction Stop).Source
$taskMutex = $null
$taskLocked = $false

function Get-LauncherControl([string]$Action) {
    $taskOutput = & $taskNode (Join-Path $PSScriptRoot 'launcher-control.mjs') $Action 2>$null
    if (-not $taskOutput) { return [pscustomobject]@{ ready = $false; errorCode = 'local_control_failed' } }
    try { return ($taskOutput -join "`n") | ConvertFrom-Json }
    catch { return [pscustomobject]@{ ready = $false; errorCode = 'local_control_failed' } }
}

function Get-ManagedMaiProcesses {
    $taskAllProcesses = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
    $taskOwnedProcesses = @($taskAllProcesses | Where-Object {
        $_.ExecutablePath -eq $taskPython -and $_.CommandLine -match '(^|[\\/"\s])bot\.py(["\s]|$)'
    })
    # The Windows venv redirector and MaiBot adapter workers run in descendants
    # of the verified bot.py process; their ports belong to those child PIDs.
    do {
        $taskOwnedIds = @($taskOwnedProcesses | ForEach-Object { $_.ProcessId })
        $taskChildren = @($taskAllProcesses | Where-Object { $_.ParentProcessId -in $taskOwnedIds -and $_.ProcessId -notin $taskOwnedIds })
        $taskOwnedProcesses += $taskChildren
    } while ($taskChildren.Count -gt 0)
    return $taskOwnedProcesses
}

function Get-LauncherHealth {
    $taskProcesses = @(Get-ManagedMaiProcesses)
    $taskProcessIds = @($taskProcesses | ForEach-Object { $_.ProcessId })
    $taskWeb = @(Get-NetTCPConnection -State Listen -LocalAddress '127.0.0.1' -LocalPort 8011 -ErrorAction SilentlyContinue | Where-Object { $_.OwningProcess -in $taskProcessIds })
    $taskConnections = @(Get-NetTCPConnection -State Established -RemoteAddress '127.0.0.1' -RemotePort 3011 -ErrorAction SilentlyContinue | Where-Object { $_.OwningProcess -in $taskProcessIds })
    return [pscustomobject]@{ maibotRunning = ($taskProcesses.Count -gt 0); webReady = ($taskWeb.Count -gt 0); wsConnected = ($taskConnections.Count -gt 0) }
}

function Set-LauncherPhase([string]$Phase, [string]$Message) {
    New-Item -ItemType Directory -Path $taskLocal -Force | Out-Null
    $taskRecord = @{ updatedAt = [DateTimeOffset]::UtcNow.ToString('o'); phase = $Phase; message = $Message }
    [IO.File]::WriteAllText($taskStatePath, ($taskRecord | ConvertTo-Json -Depth 4), $taskUtf8)
    Write-Host $Message
}

try {
    if ($CheckOnly) {
        @{ bridge = (Get-LauncherControl 'bridge'); qq = (Get-LauncherControl 'status'); bot = (Get-LauncherHealth) } | ConvertTo-Json -Depth 4 -Compress
        exit 0
    }
    $taskHash = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($taskRoot))).Substring(0, 16)
    $taskMutex = [Threading.Mutex]::new($false, "Local\QQAiLauncher-$taskHash")
    try { $taskLocked = $taskMutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $taskLocked = $true }
    if (-not $taskLocked) { Write-Host '启动程序已经在运行，请完成那个窗口中的步骤。'; exit 0 }

    try { $Host.UI.RawUI.WindowTitle = 'ChatGPT_bot' } catch { }
    Write-Host 'ChatGPT_bot 启动程序' -ForegroundColor Cyan
    Set-LauncherPhase 'starting' '1/3 正在启动模型桥接……'
    $null = & (Join-Path $PSScriptRoot 'start-setup.ps1') -NoOpenBrowser
    $taskSettings = Get-LauncherControl 'settings'
    $taskBridge = Get-LauncherControl 'bridge'
    if (-not $taskSettings.saved -or -not $taskBridge.ready) {
        if (-not $NoOpenBrowser) { Start-Process -FilePath 'http://127.0.0.1:8711/' }
        throw '请在本机设置页完成 ChatGPT 授权和已保存的小号设置，然后再次双击启动。'
    }

    Set-LauncherPhase 'starting_qq' '2/3 正在检查 QQ 小号……'
    $taskQq = Get-LauncherControl 'status'
    if (-not $taskQq.ready) {
        $taskManagedNap = @(Get-CimInstance Win32_Process -Filter "Name='NapCatWinBootMain.exe'" -ErrorAction SilentlyContinue | Where-Object { $_.ExecutablePath -eq $taskNapLauncher })
        if ($taskManagedNap.Count -eq 0) {
            # 本机器人还没有受控 NapCat 时才开始新启动；已有受控 NapCat 维持原复用路径。
            # 门禁只拒绝同一绝对路径 QQ（详情见 qq-process-guard.ps1），
            # 其它目录安装的 QQ 可以与机器人共存，不再要求退出全部 QQ。
            $null = Assert-QqGuardProcessGate -TargetExePath $taskQqExe
            $null = & (Join-Path $PSScriptRoot 'start-napcat.ps1')
        }
    }

    $taskDeadline = [DateTimeOffset]::UtcNow.AddSeconds($LoginTimeoutSec)
    $taskOpenedLogin = $false
    $taskShownWaiting = $false
    $taskAutoLoginTried = $false
    $taskAutoLoginGrace = [DateTimeOffset]::MinValue
    while ([DateTimeOffset]::UtcNow -lt $taskDeadline) {
        $taskQq = Get-LauncherControl 'status'
        if ($taskQq.loggedIn -and -not $taskQq.accountMatches) { throw '当前 QQ 与保存的小号不一致。请在 QQ 中切换到专用小号后再次启动。' }
        if ($taskQq.loggedIn -and $taskQq.accountMatches -and $taskQq.coreReady -and -not $taskQq.isOffline) { break }
        if ($taskQq.ready -and -not $taskQq.loggedIn -and -not $taskAutoLoginTried) {
            $taskAutoLoginTried = $true
            if ($taskQq.loginPhase -notin @('initializing', 'qrcode_scanned', 'reconnecting')) {
                Set-LauncherPhase 'auto_login' '正在尝试已保存的小号登录记录……'
                $taskRestore = Get-LauncherControl 'restore-login'
                if ($taskRestore.accepted) { $taskAutoLoginGrace = [DateTimeOffset]::UtcNow.AddSeconds(30) }
            } else { $taskAutoLoginGrace = [DateTimeOffset]::UtcNow.AddSeconds(30) }
        }
        if ([DateTimeOffset]::UtcNow -lt $taskAutoLoginGrace) { Start-Sleep -Seconds 2; continue }
        if ($taskQq.ready -and -not $taskQq.loggedIn -and -not $taskOpenedLogin) {
            Set-LauncherPhase 'waiting_login' '请用手机 QQ 小号扫码并确认。确认后本程序会自动继续，请保留启动窗口。'
            if (-not $NoOpenBrowser) { Start-Process -FilePath $taskUrl }
            $taskOpenedLogin = $true
        } elseif (-not $taskQq.ready -and -not $taskShownWaiting) {
            Write-Host 'QQ 登录组件正在准备……'
            $taskShownWaiting = $true
        }
        Start-Sleep -Seconds 3
    }
    if (-not ($taskQq.loggedIn -and $taskQq.accountMatches -and $taskQq.coreReady -and -not $taskQq.isOffline)) {
        throw '等待 QQ 登录超时。完成小号扫码后，再双击启动即可继续。'
    }
    if (-not $taskQq.wsEnabled) { $taskQq = Get-LauncherControl 'enable' }
    if (-not $taskQq.wsEnabled) { throw 'QQ 消息通道尚未接通，请检查小号登录状态后再次启动。' }

    Set-LauncherPhase 'starting_bot' '3/3 正在启动聊天机器人……'
    $taskProcesses = @(Get-ManagedMaiProcesses)
    if ($taskProcesses.Count -eq 0) { $null = & (Join-Path $PSScriptRoot 'start-maibot.ps1') }
    $taskDeadline = [DateTimeOffset]::UtcNow.AddSeconds(90)
    do {
        $taskHealth = Get-LauncherHealth
        if ($taskHealth.maibotRunning -and $taskHealth.webReady -and $taskHealth.wsConnected) { break }
        Start-Sleep -Seconds 2
    } while ([DateTimeOffset]::UtcNow -lt $taskDeadline)
    if (-not ($taskHealth.maibotRunning -and $taskHealth.webReady -and $taskHealth.wsConnected)) {
        throw '机器人连接未完成。保留启动记录，在这条聊天里让我检查即可。'
    }
    $taskQq = Get-LauncherControl 'status'
    if (-not ($taskQq.loggedIn -and $taskQq.accountMatches -and $taskQq.coreReady -and -not $taskQq.isOffline -and $taskQq.wsEnabled)) {
        throw 'QQ 在启动期间离线，请恢复专用小号登录后再次启动。'
    }
    # 每次真实一键启动成功后，请独立插件自行考虑是否主动私聊。
    # CheckOnly 在此前已经返回，热加载插件也不会产生这个信号。
    $taskCompanionDir = Join-Path $taskMai 'temp\plugins\local.silver-dragon-companion'
    $taskCompanionSignal = Join-Path $taskCompanionDir 'startup-request.json'
    try {
        [IO.Directory]::CreateDirectory($taskCompanionDir) | Out-Null
        $taskCompanionRequest = @{request_id=[Guid]::NewGuid().ToString('N');requested_at=[DateTimeOffset]::UtcNow.ToString('o')}
        $taskCompanionTemp = $taskCompanionSignal + '.' + $taskCompanionRequest.request_id + '.tmp'
        [IO.File]::WriteAllText($taskCompanionTemp, ($taskCompanionRequest | ConvertTo-Json -Compress), $taskUtf8)
        Move-Item -LiteralPath $taskCompanionTemp -Destination $taskCompanionSignal -Force
    } catch {
        Write-Host '机器人已接通；主动聊天启动信号未记录，可稍后再次启动。'
    }
    Set-LauncherPhase 'ready' '启动完成：QQ 小号在线，机器人已接通。现在可以用主 QQ 与她聊天。'
    if ($taskBridge.planPaused) { Write-Host '当前记录显示模型共享额度受限，文字回复需等待额度恢复。' }
    if (-not $NoWaitOnExit) { $null = Read-Host '按回车关闭这个启动窗口，机器人将继续在后台运行' }
    exit 0
} catch {
    # Script errors are kept locally; do not display raw command lines or logs.
    $taskMessage = '启动未完成，请检查安装目录与本机启动日志。'
    $taskKnownMessages = @(
        '请在本机设置页完成 ChatGPT 授权和已保存的小号设置，然后再次双击启动。',
        # 门禁提示与 qq-process-guard.ps1 用同一函数生成，避免两处文本漂移。
        (Get-QqGuardSameExeMessage -TargetExePath $taskQqExe),
        (Get-QqGuardUnverifiableMessage),
        (Get-QqGuardUnknownTargetMessage),
        '当前 QQ 与保存的小号不一致。请在 QQ 中切换到专用小号后再次启动。',
        '等待 QQ 登录超时。完成小号扫码后，再双击启动即可继续。',
        'QQ 消息通道尚未接通，请检查小号登录状态后再次启动。',
        '机器人连接未完成。保留启动记录，在这条聊天里让我检查即可。',
        'QQ 在启动期间离线，请恢复专用小号登录后再次启动。'
    )
    if ($_.Exception.Message -in $taskKnownMessages) { $taskMessage = $_.Exception.Message }
    Set-LauncherPhase 'blocked' $taskMessage
    exit 1
} finally {
    if ($taskLocked -and $taskMutex) { $taskMutex.ReleaseMutex() }
    if ($taskMutex) { $taskMutex.Dispose() }
}
