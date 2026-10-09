# QQ 进程门禁（共享判定）：只拦截本机器人将要启动的同一个绝对路径 QQ，
# 允许其它目录安装的 QQ 与机器人共存。
#
# 本文件是 QQ 可执行文件路径与门禁判定的唯一来源：
# start-qq-bot.ps1 与 start-napcat.ps1 都必须 dot-source 本文件，
# 不允许在启动脚本里再写一份 QQ 路径常量或第二套判定。
# 本文件被 dot-source（. 路径）加载，自身不做任何启动/停止/结束进程的操作。

$QqGuardRuntimeRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\runtime'))
$QqGuardExePath = Join-Path $QqGuardRuntimeRoot 'QQ\QQ.exe'

function Get-QqGuardNapCatRoot {
    return (Join-Path $QqGuardRuntimeRoot 'NapCat')
}

function Get-QqGuardExePath {
    return $QqGuardExePath
}

# 把路径规范成可比较形式：去空白与引号、正斜杠转反斜杠、去掉 \\?\ 前缀与结尾反斜杠。
# 路径为空或不可读时返回空字符串，调用方必须按“无法核验”处理，不得当作安全。
function ConvertTo-QqGuardComparablePath {
    [CmdletBinding()]
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) { return '' }
    $value = ([string]$Path).Trim().Trim('"').Trim()
    if (-not $value) { return '' }
    $value = $value -replace '/', '\'
    $value = $value -replace '^\\\\\?\\', ''
    $value = $value.TrimEnd('\')
    if (-not $value) { return '' }
    return $value
}

function Test-QqGuardSamePath {
    [CmdletBinding()]
    param([string]$Left, [string]$Right)
    $leftValue = ConvertTo-QqGuardComparablePath $Left
    $rightValue = ConvertTo-QqGuardComparablePath $Right
    if (-not $leftValue -or -not $rightValue) { return $false }
    # Windows 路径大小写不敏感。
    return [string]::Equals($leftValue, $rightValue, [StringComparison]::OrdinalIgnoreCase)
}

# 以下提示文本是唯一来源：主脚本 catch 里的已知提示必须调用同一函数生成，保证文本一致。
function Get-QqGuardSameExeMessage {
    [CmdletBinding()]
    param([string]$TargetExePath = (Get-QqGuardExePath))
    return ('本机器人要使用的 QQ（{0}）仍在运行，但它不受本启动程序控制。请完全退出该目录下的 QQ（包括托盘图标）后再启动机器人；其它目录安装的 QQ 可以继续保留。' -f $TargetExePath)
}

function Get-QqGuardUnverifiableMessage {
    [CmdletBinding()]
    param()
    return '检测到名为 QQ/QQNT 的进程，但无法读取它的可执行文件路径，不能确认它是否属于本机器人使用的目录。请退出这些无法确认来源的 QQ（包括托盘图标）后再启动机器人；其它目录安装的 QQ 可以继续保留。'
}

function Get-QqGuardUnknownTargetMessage {
    [CmdletBinding()]
    param()
    return '无法确定本机器人要使用的 QQ 程序路径，已按最保守方式停止启动。请检查安装目录与本机启动日志。'
}

# 枚举同名候选进程，并尽力读取可执行文件路径。读不到路径时保留空路径，
# 由 Test-QqGuardProcessGate 判为“无法核验”。不结束任何进程。
function Get-QqGuardCandidateProcesses {
    [CmdletBinding()]
    param([string[]]$Name = @('QQ', 'QQNT'))
    $candidates = New-Object System.Collections.ArrayList
    foreach ($process in @(Get-Process -Name $Name -ErrorAction SilentlyContinue)) {
        $path = ''
        try { $path = [string]$process.Path } catch { $path = '' }
        if (-not $path) {
            try {
                $cimProcess = Get-CimInstance Win32_Process -Filter ('ProcessId={0}' -f $process.Id) -ErrorAction SilentlyContinue
                if ($cimProcess) { $path = [string]$cimProcess.ExecutablePath }
            } catch { $path = '' }
        }
        $null = $candidates.Add([pscustomobject]@{ Id = $process.Id; Name = $process.ProcessName; Path = $path })
    }
    return $candidates.ToArray()
}

# 纯判定，不触碰真实进程：同路径拒绝、无法核验拒绝、其它目录放行、空列表放行。
function Test-QqGuardProcessGate {
    [CmdletBinding()]
    param(
        [object[]]$Processes,
        [string]$TargetExePath = (Get-QqGuardExePath)
    )
    $target = ConvertTo-QqGuardComparablePath $TargetExePath
    $list = @($Processes | Where-Object { $null -ne $_ })
    if (-not $target) {
        if ($list.Count -eq 0) {
            return [pscustomobject]@{ allowed = $true; reason = 'allowed'; message = ''; blocking = @(); retained = @() }
        }
        return [pscustomobject]@{
            allowed = $false; reason = 'target_unknown'
            message = (Get-QqGuardUnknownTargetMessage); blocking = $list; retained = @()
        }
    }
    $sameExe = New-Object System.Collections.ArrayList
    $unverifiable = New-Object System.Collections.ArrayList
    $retained = New-Object System.Collections.ArrayList
    foreach ($process in $list) {
        $candidate = ConvertTo-QqGuardComparablePath ([string]$process.Path)
        if (-not $candidate) { $null = $unverifiable.Add($process); continue }
        if ([string]::Equals($candidate, $target, [StringComparison]::OrdinalIgnoreCase)) { $null = $sameExe.Add($process) }
        else { $null = $retained.Add($process) }
    }
    if ($sameExe.Count -gt 0) {
        return [pscustomobject]@{
            allowed = $false; reason = 'same_executable'
            message = (Get-QqGuardSameExeMessage -TargetExePath $target)
            blocking = $sameExe.ToArray(); retained = $retained.ToArray()
        }
    }
    if ($unverifiable.Count -gt 0) {
        return [pscustomobject]@{
            allowed = $false; reason = 'unverifiable'
            message = (Get-QqGuardUnverifiableMessage)
            blocking = $unverifiable.ToArray(); retained = $retained.ToArray()
        }
    }
    return [pscustomobject]@{ allowed = $true; reason = 'allowed'; message = ''; blocking = @(); retained = $retained.ToArray() }
}

# 启动脚本使用的门禁：枚举真实同名进程后判定，被拦截时抛出统一提示。
function Assert-QqGuardProcessGate {
    [CmdletBinding()]
    param(
        [object[]]$Processes = (Get-QqGuardCandidateProcesses),
        [string]$TargetExePath = (Get-QqGuardExePath)
    )
    $result = Test-QqGuardProcessGate -Processes $Processes -TargetExePath $TargetExePath
    if (-not $result.allowed) { throw $result.message }
    return $result
}
