[CmdletBinding()]
param(
    [switch]$CheckOnly,
    [switch]$DryRun,
    [switch]$SkipNapCat,
    [switch]$SkipPython,
    [switch]$SkipSdk,
    [string]$PythonPath = '3.12',
    [string]$QqInstallDirectory
)
$ErrorActionPreference = 'Stop'
$packageRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$botRoot = Join-Path $packageRoot 'work\compatible-release\MaiBot-1.2.5'
$sdkRoot = Join-Path $packageRoot 'work\official-sdk\sign-in-with-chatgpt-devkit-main'
$runtimeRoot = Join-Path $packageRoot 'runtime'
$issues = @()
if ($PSVersionTable.PSVersion -lt [version]'7.4') { $issues += '需要 PowerShell 7.4 或更高版本。' }
foreach ($command in @('node','npm','uv')) {
    if (-not (Get-Command $command -ErrorAction SilentlyContinue)) { $issues += "未找到 $command，请先安装并加入 PATH。" }
}
if (Get-Command node -ErrorAction SilentlyContinue) {
    $nodeVersion = (& node -p 'process.versions.node').Trim()
    if ([version]$nodeVersion -lt [version]'24.5.0') { $issues += '本启动器需要 Node.js 24.5 或更高版本。' }
}
foreach ($source in @('bot.py','pyproject.toml','uv.lock')) {
    if (-not (Test-Path -LiteralPath (Join-Path $botRoot $source))) { $issues += "缺少源码 $source。" }
}
foreach ($source in @('package-lock.json','packages\local\src\index.ts','LICENSE')) {
    if (-not (Test-Path -LiteralPath (Join-Path $sdkRoot $source))) { $issues += "缺少 SDK 源码 $source。" }
}
# The reviewed QQ/NapCat setup requires an English deployment path.
if ($packageRoot -match '[^\x00-\x7F]') { $issues += '请把项目移到英文目录，例如 D:\ChatGPT-Dragon-QQ-Bot。' }
if ($CheckOnly -or $DryRun) {
    [ordered]@{ ok=($issues.Count -eq 0); readOnly=$true; issues=@($issues); napcatVersion='v4.18.33'; actions=@('uv sync --frozen --no-dev','安装可选插件依赖','npm ci + SDK build','下载并校验 NapCat','可选：从指定 QQ 安装目录复制程序文件，排除账号缓存') } | ConvertTo-Json -Depth 4
    if ($issues.Count) { exit 1 }; exit 0
}
if ($issues.Count) { throw ($issues -join "`n") }
if (-not $SkipPython) {
    Push-Location $botRoot
    try {
        & uv sync --frozen --no-dev --python $PythonPath
        if ($LASTEXITCODE -ne 0) { throw 'MaiBot 依赖安装失败，请保留上面的错误信息。' }
        $python = Join-Path $botRoot '.venv\Scripts\python.exe'
        & uv pip install --python $python 'edge-tts==7.2.8' -r (Join-Path $botRoot 'plugins\Maizone\requirements.txt')
        if ($LASTEXITCODE -ne 0) { throw '插件依赖安装失败。' }
    } finally { Pop-Location }
}
if (-not $SkipSdk) {
    Push-Location $sdkRoot
    try {
        & npm ci --workspace '@siwc/local' --include-workspace-root
        if ($LASTEXITCODE -ne 0) { throw 'SDK 依赖安装失败。' }
        & npm run build --workspace '@siwc/local'
        if ($LASTEXITCODE -ne 0) { throw 'SDK 构建失败。' }
    } finally { Pop-Location }
}
if (-not $SkipNapCat) {
    $napcatRoot = Join-Path $runtimeRoot 'NapCat'
    New-Item -ItemType Directory -Path $napcatRoot -Force | Out-Null
    $archive = Join-Path $napcatRoot 'NapCat.Shell.zip'
    $expectedHash = '4b8e20e6d22288586d99eb0b34fff6c7ee1d88b00353039326f8c459a86df667'
    Invoke-WebRequest -Uri 'https://github.com/NapNeko/NapCatQQ/releases/download/v4.18.33/NapCat.Shell.zip' -OutFile $archive
    if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedHash) { throw 'NapCat SHA256 不一致，已停止安装。' }
    Expand-Archive -LiteralPath $archive -DestinationPath $napcatRoot -Force
}
if ($QqInstallDirectory) {
    $source = (Resolve-Path -LiteralPath $QqInstallDirectory).Path
    $destination = Join-Path $runtimeRoot 'QQ'
    if (-not (Test-Path -LiteralPath (Join-Path $source 'QQ.exe'))) { throw '指定目录中没有 QQ.exe，请提供 QQ 官方程序安装目录。' }
    if ($source.Equals($destination,[StringComparison]::OrdinalIgnoreCase) -or $source.StartsWith($runtimeRoot+'\',[StringComparison]::OrdinalIgnoreCase)) { throw '来源必须是项目以外的 QQ 官方安装目录。' }
    # Copy only program content; exclude any profiles/data/logins and do not follow reparse points.
    New-Item -ItemType Directory -Path $destination -Force | Out-Null
    & robocopy $source $destination /E /XJ /XD QQ-profile profile profiles UserData 'User Data' data logs cache config /XF *.db *.sqlite *.sqlite3 *.log *.jsonl /R:0 /W:0 /NFL /NDL /NJH /NJS
    if ($LASTEXITCODE -ge 8) { throw 'QQ 程序文件复制失败。' }
}
Write-Host '依赖安装完成。双击 Setup.cmd，登录 ChatGPT、选择模型、填写主号与机器人小号，并阅读确认 MaiBot 协议。'
Write-Host '然后双击 Start.cmd。QQ 的登录与验证必须由你自己完成。'

