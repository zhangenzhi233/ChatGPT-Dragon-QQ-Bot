# ChatGPT 龙娘 QQ 聊天机器人

**在自己的 Windows 电脑上，让 QQ 小号成为可修改人设的银白龙娘 AI 伙伴。**

基于 MaiBot 1.2.5、NapCat Adapter 1.4.0 和官方 Sign in with ChatGPT DevKit；支持文字与图片理解、龙娘表情、按需语音以及可选的主动聊天。当前版本是供学习和复现的实验版。

![银白龙 Q 版](assets/character/Q版.jpg)

本项目由个人维护，非 OpenAI 或腾讯官方产品。每位使用者自行登录自己的 ChatGPT 与 QQ 账号；本仓库不提供账号、额度或登录缓存。SDK 受非商业许可约束，整个组合不能视为统一的 MIT 项目，详见 [第三方许可](THIRD_PARTY_NOTICES.md)。

## 2026-10-15 更新

- 长回答按自然句段连续发送，保留代码、括号与缩进；修复超长回复被替换成“不知道”的问题。
- QQ 普通文字中的常见公式转换为可直接阅读的符号与算式，代码和未知公式保留原样。
- 主动聊天新增有来源的待跟进事项、话题去重与发送结果记录；新消息到来时让未发送的主动回复让位。
- 改善模型暂时断连后的恢复，以及空间配图选择和发布前的有限准备重试。

相关离线回归 210 项、发布配置测试 6 项通过。主动聊天、语音和空间功能在新安装中仍默认关闭。更新详情、验证边界及已有安装的更新步骤见 [更新记录](CHANGELOG.md)。

## 功能与默认设置

| 功能 | 默认状态 | 说明 |
|---|---|---|
| QQ 私聊文字、图片理解 | 设置完成后可用 | 仅允许设置页指定的主号；模型能力与账号资格以实际授权结果为准 |
| 银白龙人设与 29 张表情 | 人设自动应用，表情手动导入 | 原画、Q 版是同一虚拟角色；可换成你自己的形象 |
| 按需语音 | 关闭 | 开启后可朗读文字或用语音回答当前问题 |
| 主动聊天 | 关闭 | 有来源的事项跟进与话题去重；由模型决定是否开口，允许保持沉默 |
| QQ 空间读写 | 关闭 | 需要另外配置 Maizone；公开发布功能需自行明确开启 |
| 群聊 | 没有默认群授权 | 当前发布包尚未做群聊实测 |

![29 张龙娘表情预览](assets/stickers/preview.png)

## 先准备环境

- Windows 10/11，64 位。
- [Node.js](https://nodejs.org/) 24.5 或更高版本。
- [PowerShell](https://github.com/PowerShell/PowerShell/releases) 7.4 或更高版本，安装后能运行 `pwsh`。
- [uv](https://docs.astral.sh/uv/getting-started/installation/)，用于创建独立的 Python 3.12 环境。没有 Python 3.12 时 uv 可在安装阶段下载；不依赖 Codex 内置环境。
- 从 [QQ 官网](https://im.qq.com/) 安装 Windows QQ，准备一个机器人小号与自己的主号。已核验的本机基线为 QQ 9.9.33-52230，其他版本的 NapCat 兼容性需实测。
- 可自行登录的 ChatGPT 账号。官方文档说明，符合资格的 Plus/Pro 用户可以授权本地应用使用方案额度；是否可用、具体模型与额度以登录页面为准。[官方接入说明](https://developers.openai.com/siwc/quickstart)

## 1. 下载并安装依赖

在 GitHub 的 **Code → Download ZIP** 下载并解压，或：

```powershell
git clone https://github.com/zhangenzhi233/ChatGPT-Dragon-QQ-Bot.git
```

把项目放到英文目录，例如 `D:\ChatGPT-Dragon-QQ-Bot`。在项目目录打开 PowerShell 7：

```powershell
# 只读检查：不联网、不启动、不写配置
pwsh -File .\setup\install.ps1 -CheckOnly

# 安装依赖，下载并校验 NapCat 4.18.33。
# 把参数替换为你实际安装 QQ.exe 的目录。
pwsh -File .\setup\install.ps1 -QqInstallDirectory "C:\Program Files\Tencent\QQNT"
```

安装会创建本项目的独立 Python 环境、构建登录 SDK，并从指定官方安装目录复制 QQ 程序到 `runtime/QQ`。账号缓存不随项目提供。安装不会启动 QQ、调用模型或自动接受 MaiBot 协议。

如果 QQ 安装路径不同，找到 `QQ.exe` 后填写它所在的目录。安装失败时保留终端的原始报错；不要直接复制别人整个机器人运行目录。

## 2. 完成本机设置

双击 **Setup.cmd**，浏览器打开本机设置页 `http://127.0.0.1:8711/`：

1. 使用自己的 ChatGPT 账号登录，在官方页面完成授权。
2. 从实际可用列表选择模型。使用方案额度需要相应授权，额度限制不能由本项目解除。
3. 填写机器人 QQ 小号和允许私聊的主 QQ，两个号码必须不同。测试群号可以留空。
4. 阅读 MaiBot 的许可和隐私条款，然后确认并保存。

设置页的单次模型测试是可选项，会使用你的模型额度。不要在限额或网络失败时反复点击。

## 3. 启动与登录 QQ

双击 **Start.cmd**。启动器会检查桥接、启动专用 QQ/NapCat，等待扫码并启动 MaiBot。

- 使用机器人小号扫码；设备验证必须由你自己完成。
- 看到“启动完成”后，从设置中的主 QQ 发一条普通私聊，确认真实往返。
- 重复启动会检查并复用本目录已有服务。其他目录里的 QQ 可以保留；无法核验进程归属时启动器会给出提示。
- 电脑需要保持开机、联网。QQ 会话可能失效，需要重新登录。

本项目使用独立端口：设置/桥接 **8711**、NapCat WebUI **6109**、消息 WebSocket **3011**、MaiBot WebUI **8011**，均限制在本机回环地址。同一套端口当前支持一个实例；被其他服务占用时先检查占用原因。

## 4. 导入龙娘表情

机器人与 MaiBot 已启动后，在项目目录执行：

```powershell
# 只核验本地 29 张 PNG 及清单，不连接机器人
node .\scripts\import-stickers.mjs --check-only

# 使用本项目本机管理凭据导入表情，并登记角色归属；不会主动发 QQ 消息
node .\scripts\import-stickers.mjs
```

首次导入后，若当前内存表情池未刷新，可停止并重新启动本项目，再从主号请求一张表情。文件入库、实际发送和手机显示是不同检查点。

## 5. 修改人设、开启语音或主动聊天

把 `outputs/qq-ai-setup/人设设置.example.toml` 复制为同目录的 `人设设置.toml`，修改昵称、性格、行为和说话风格，然后执行：

```powershell
.\work\compatible-release\MaiBot-1.2.5\.venv\Scripts\python.exe .\outputs\qq-ai-setup\apply-persona.py
```

开启或关闭可选功能：

```powershell
$botPython = ".\work\compatible-release\MaiBot-1.2.5\.venv\Scripts\python.exe"
& $botPython .\scripts\configure-features.py --voice on
& $botPython .\scripts\configure-features.py --companion on
# 暂停主动聊天
& $botPython .\scripts\configure-features.py --companion off
```

配置后，在 MaiBot WebUI 的插件管理中加载或重载相应插件，也可以停止再启动本项目。

- 语音：`/语音 你好呀` 朗读指定内容；`你今天过得怎么样？用语音告诉我。` 请求本轮动态语音回答；`/试听` 才播放固定问候。音色、语速、音高在 `plugins/SilverDragonVoice/config.toml` 的 `[voice]` 修改。
- 主动聊天：默认每天最多 3 次尝试，至少间隔 60 分钟，北京时间 00:00–08:00 静默。模型评估时间不是保证发送时间。需真实主号私聊存在，首次开启后可在下一次启动信号或未来评估时判断是否开口。
- 空间功能：独立的 Maizone 插件默认关闭，自动发布默认关闭。请先阅读 [Maizone 原说明](work/compatible-release/MaiBot-1.2.5/plugins/Maizone/README.md)，再填写自己的权限并启用；不要沿用他人的 cookies。

主动聊天可记录最多 8 条有消息原文依据的待跟进事项，区分完成、取消和过期，减少反复追问。事项及引用片段保存在本机插件状态，并通过原有模型通道参与评估。它依赖模型判断，可能漏记或误判，不提供准点提醒保证。没有增加调度请求次数，单次输出上限由 512 提高到 1200 tokens，实际输出用量可能增加。详见 [连续陪伴说明](docs/连续陪伴升级说明.md)。

## 停止机器人

```powershell
# 查看本目录可确认归属的进程数量，不停止
pwsh -File .\scripts\stop.ps1 -CheckOnly

# 停止本目录的受管服务及其子进程
pwsh -File .\scripts\stop.ps1
```

## 数据与验证状态

自己的配置、授权、QQ 缓存、数据库、日志和虚拟环境均被 `.gitignore` 排除。发布改动前执行：

```powershell
.\work\compatible-release\MaiBot-1.2.5\.venv\Scripts\python.exe .\scripts\verify-release.py
git status --short
```

截至 2026-10-09，本发布树已实际完成独立依赖安装、SDK 构建、插件离线回归、桥接/登录模拟回归、PowerShell 解析、进程归属检查和素材哈希检查。SDK 有一项仅适用于 Unix 的权限测试在 Windows 跳过。详见 [发布核验记录](docs/发布前核验.md)。

2026-10-15 在此基础上完成 210 项相关离线回归和 6 项发布配置测试，并复核公开文件与素材。以上为选定范围的回归结果，不代表全仓测试通过；未调用真实模型或发送测试消息。

**新安装的 QQ 登录、ChatGPT 授权、真实文字/图片/语音往返和空间动作尚未在另一台干净机器上完成验证。** 请把本项目视为实验版；问题反馈请注明版本和报错，并遮住账号、密钥与聊天内容。

## 来源与许可

- MaiBot 与修改：GPL v3；子目录中的 AGPL、MIT 及 MaiBot 特别许可授权均保留。
- NapCat Adapter：GPL v3 或更高版本；Maizone 和两个独立定制插件按各自 MIT 许可。
- OpenAI Sign in with ChatGPT DevKit 及其修改：**Noncommercial License v1.0**，保留原文及修改说明。
- 图片素材独立于代码许可，见 [素材使用说明](assets/README.md)。

欢迎提交问题或改进。提交前只包含源码和示例配置，且说明实际验证结果。

