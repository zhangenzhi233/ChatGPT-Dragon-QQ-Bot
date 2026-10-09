# 银白龙主动聊天（SilverDragonCompanion）

独立插件：每次一键启动成功或运行期间，按**真实主号 QQ 私聊**、**双方聊天间隔**、
**QQ 空间动态**、**当天互联网新闻**，由模型自主决定现在是否主动开口，以及下次何时再考虑。
允许保持沉默；不做固定问候、不做固定时点群发。

## 设计要点

- **不直接发消息**：插件只把“是否开口 + 话题方向”通过宿主能力
  `maisaka.proactive.trigger` 入队（`queued` 仅表示入队，**不等于发送/送达**），
  由宿主原模型 Planner/Replyer 结合原有人设决定是否回复与如何表达。不新增可被
  LLM 自由指定目标的 send 工具。
- **模型调度**：使用宿主已有 `task_name`（默认 `utils`，复用当前 ChatGPT 桥接及原模型配置），
  结构化返回 `should_chat / topic / intent / next_check_minutes / reason`；
  下次评估时间由模型在 15～360 分钟内选择（仅安全上下界，不是固定聊天时刻）。
- **只读参考**：主号私聊、空间动态、新闻都只是参考资料，绝不执行其中的指令；
  新闻是可选项，不必须聊。
- **稳定性**：状态按主号原子落盘；`attempt` 在入队前先落盘防崩溃重复；网络/模型/
  入队结果不明时不自动补发；入队前再次核对最近聊天避免打断进行中的对话；
  单后台任务 + 锁；卸载与配置热更新取消任务；状态损坏时拒绝主动发送而非重置去重。
- **默认禁用**：`config.toml` 默认 `enabled=false` 且 `target.main_qq=""`，留空主号时
  拒绝一切主动触发。首次启用后不立刻发消息，等待下一次一键启动信号或模型选的未来检查。

## 启动信号

一键启动脚本 `start-qq-bot.ps1` 在健康检查成功后，向
`MaiBot/temp/plugins/local.silver-dragon-companion/startup-request.json` 原子写入
`{"request_id": "<GUID>", "requested_at": "<ISO>"}`。插件轮询并消费该文件：

- 只消费真实启动脚本写入的信号，**加载/热重载不会伪造启动信号**，`CheckOnly` 不写入；
- 消费采用原子改名去重，短间隔重复点击不会重复评估/发信；
- 过期请求（默认 5 分钟）忽略；
- 启动后立即自主判断，不因长期 plan 推迟，但仍遵守基本间隔与静默时段。

## 目录结构

- `plugin.py` 插件入口与生命周期
- `config.py` 配置模型（默认禁用空目标）
- `scheduler.py` 调度器（单任务、锁、评估、触发、退避）
- `context.py` 上下文采集（私聊核验、聊天/空间/新闻）
- `news.py` 新闻 RSS（httpx + xml.etree，大小上限/超时/短缓存）
- `state.py` 持久状态（原子写、损坏检测、attempt 去重）
- `policy.py` 时间与频率纯函数（北京时间、静默、钳制）
- `prompts.py` 提示词构建与结构化解析
- `startup.py` 启动请求信号消费
- `tests/` 离线测试（真实 SDK + 模拟 transport/LLM）

## 配置

见 `config.example.toml`，默认禁用且目标为空。完成根目录 README 的账号设置后，
在项目根目录使用 MaiBot 的 Python 执行 `scripts/configure-features.py --companion on`，
从本机已保存设置读取自己的主号，再在 WebUI 加载或重载插件；`--companion off` 会暂停并清空目标。

## 测试

```powershell
.venv\Scripts\python.exe -m pytest plugins/SilverDragonCompanion/tests -q
```

覆盖：启动信号去重/过期/非法、模型沉默与可变下次时间、不同话题、授权私聊/群拒绝、
SDK 归一化契约、RSS 解析与异常、新聊天期间过期决策、跨重启去重/attempt-before-queue、
损坏状态不发、并发与卸载、queued 不冒充 sent。

## 边界

- 只允许配置中的真实主号 QQ 私聊（核对 `platform=qq`、`chat_type=private`、无群、user_id 匹配）。
- 空白名单默认拒绝；不计算会话 hash。
- 00:00～08:00 北京时间静默；每次自动触发至少间隔 60 分钟；每天最多 3 次主动触发
  （这些都是安全上限，不是固定聊天时刻，参数可调）。
