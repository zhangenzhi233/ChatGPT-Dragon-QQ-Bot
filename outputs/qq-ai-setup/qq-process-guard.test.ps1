# 离线回归：QQ 进程门禁只拦截本机器人将要启动的同一绝对路径 QQ。
# 直接调用 qq-process-guard.ps1 的真实函数，传入手工构造的进程对象；
# 不启动、不停止、不结束任何真实进程，也不读写配置或凭据。
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'qq-process-guard.ps1')

$script:passed = 0
$script:failed = 0

function Assert-Check([bool]$Condition, [string]$Label) {
    if ($Condition) {
        $script:passed++
        Write-Host ("PASS  {0}" -f $Label)
    } else {
        $script:failed++
        Write-Host ("FAIL  {0}" -f $Label)
    }
}

function New-QqGuardFixture([int]$Id, [string]$Path, [string]$Name = 'QQ') {
    return [pscustomobject]@{ Id = $Id; Name = $Name; Path = $Path }
}

$target = Get-QqGuardExePath
Assert-Check ((-not [string]::IsNullOrWhiteSpace($target)) -and $target.EndsWith('QQ.exe')) 'helper 提供唯一的 QQ 可执行文件路径'

# 用独立的模拟目标测试判定，不依赖实际安装目录。
$target = 'D:\QQ\QQ.exe'

# 1. 不同目录安装的 QQ 允许共存（当前实际场景：D:\QQ-Tulpa-DeepSeek\QQ.exe）。
$differentDirectory = @(New-QqGuardFixture 101 'D:\QQ-Tulpa-DeepSeek\QQ.exe')
$result = Test-QqGuardProcessGate -Processes $differentDirectory -TargetExePath $target
Assert-Check ($result.allowed -eq $true) '不同目录的 QQ 允许共存'
Assert-Check ($result.reason -eq 'allowed') '不同目录的判定原因是 allowed'
Assert-Check (@($result.retained).Count -eq 1) '不同目录的 QQ 记入保留列表'
Assert-Check (@($result.blocking).Count -eq 0) '不同目录不产生拦截项'

# 2. 同一绝对路径的 QQ 拒绝。
$sameDirectory = @(New-QqGuardFixture 202 'D:\QQ\QQ.exe')
$result = Test-QqGuardProcessGate -Processes $sameDirectory -TargetExePath $target
Assert-Check ($result.allowed -eq $false) '相同路径的 QQ 被拒绝'
Assert-Check ($result.reason -eq 'same_executable') '相同路径的判定原因是 same_executable'
Assert-Check (@($result.blocking).Count -eq 1) '相同路径记入拦截列表'
Assert-Check (@($result.retained).Count -eq 0) '相同路径不进入保留列表'
Assert-Check ($result.message -eq (Get-QqGuardSameExeMessage -TargetExePath $target)) '拒绝提示与主脚本已知提示同源'
Assert-Check ($result.message.Contains($target)) '拒绝提示指明本机器人使用的 QQ 路径'
Assert-Check ($result.message.Contains('可以继续保留')) '拒绝提示明确其它目录 QQ 可以保留'
Assert-Check (-not $result.message.Contains('退出全部')) '拒绝提示不再要求退出全部 QQ'

# 3. 路径大小写与分隔符不敏感。
$variants = @(
    'd:\qq\qq.exe',
    'D:/QQ/QQ.exe',
    '  "D:\QQ\QQ.EXE"  ',
    '\\?\D:\QQ\QQ.exe',
    'D:\QQ\QQ.exe\'
)
foreach ($variant in $variants) {
    $result = Test-QqGuardProcessGate -Processes @(New-QqGuardFixture 303 $variant) -TargetExePath $target
    Assert-Check (($result.allowed -eq $false) -and ($result.reason -eq 'same_executable')) ("路径变体仍被拒绝：{0}" -f $variant)
}
$result = Test-QqGuardProcessGate -Processes @(New-QqGuardFixture 304 'D:\QQ\QQ.exe') -TargetExePath 'd:/qq/QQ.exe'
Assert-Check (($result.allowed -eq $false) -and ($result.reason -eq 'same_executable')) '目标路径写成小写正斜杠时仍被拒绝'
Assert-Check ((Test-QqGuardSamePath 'D:\QQ\QQ.exe' 'd:\qq\qq.exe') -eq $true) 'Test-QqGuardSamePath 大小写不敏感'
Assert-Check ((Test-QqGuardSamePath 'D:\QQ\QQ.exe' 'D:\QQ-Tulpa-DeepSeek\QQ.exe') -eq $false) 'Test-QqGuardSamePath 区分目录'
Assert-Check ((Test-QqGuardSamePath '' 'D:\QQ\QQ.exe') -eq $false) '空路径不与任何路径相同'

# 4. 路径无法读取的同名进程按无法核验拒绝，不能假定安全。
foreach ($unreadable in @($null, '', '   ')) {
    $result = Test-QqGuardProcessGate -Processes @(New-QqGuardFixture 404 $unreadable) -TargetExePath $target
    Assert-Check (($result.allowed -eq $false) -and ($result.reason -eq 'unverifiable')) '路径读不出的同名进程被拒绝'
}
Assert-Check ((Get-QqGuardUnverifiableMessage) -ne (Get-QqGuardSameExeMessage -TargetExePath $target)) '无法核验与相同路径的可辨别提示不同'
Assert-Check ((Get-QqGuardUnverifiableMessage).Contains('无法读取')) '无法核验提示说明原因'
Assert-Check ((Get-QqGuardUnverifiableMessage).Contains('可以继续保留')) '无法核验提示明确其它目录 QQ 可以保留'

# 5. 空列表允许（电脑上没有同名 QQ 时正常启动）。
$result = Test-QqGuardProcessGate -Processes @() -TargetExePath $target
Assert-Check ($result.allowed -eq $true) '空进程列表允许启动'
$result = Test-QqGuardProcessGate -Processes $null -TargetExePath $target
Assert-Check ($result.allowed -eq $true) 'null 进程列表允许启动'

# 6. 拦截判定同时支持抛错入口，并与主脚本口径一致。
$threwMessage = ''
try {
    $null = Assert-QqGuardProcessGate -Processes $sameDirectory -TargetExePath $target
} catch { $threwMessage = $_.Exception.Message }
Assert-Check ($threwMessage -eq (Get-QqGuardSameExeMessage -TargetExePath $target)) 'Assert 门禁对相同路径抛出统一提示'
$allowedThrough = $true
try {
    $null = Assert-QqGuardProcessGate -Processes $differentDirectory -TargetExePath $target
} catch { $allowedThrough = $false }
Assert-Check ($allowedThrough -eq $true) 'Assert 门禁对不同目录放行'

Write-Host ("PASS={0} FAIL={1}" -f $script:passed, $script:failed)
if ($script:failed -gt 0) { exit 1 }
exit 0
