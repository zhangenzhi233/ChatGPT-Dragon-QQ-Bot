# Group Chat Stream Benchmark

这套基准数据专门用于 A_memorix 当前“群聊聊天流”设计的量化评估。

设计对齐点：

- 只把 Bot 参与过的话题段落纳入长期记忆总结。
- 群聊内容先按话题批次收束，再写入 `chat_summary`。
- 回复前通过 `search_long_term_memory` 做长期记忆检索增强。
- 回复后只把“关于人物的稳定事实”写回 `person_fact`。
- 检索需要覆盖 `search / time / episode / aggregate` 四种模式。
- 需要有明确的负样本，验证“无 Bot 参与”的纯群友闲聊不会被误写入。
- 当前 summarizer 的原生触发条件需要被显式覆盖：
  `80` 条消息直接触发，或 `8` 小时后累计至少 `20` 条消息触发。

数据文件：

- `group_chat_stream_memory_benchmark.json`
- `group_chat_stream_memory_benchmark_hard.json`
  第二套更长、更刁钻的压力数据，刻意加入跨话题重叠词、自然句 episode query、
  以及更容易淹没人物事实的长聊天流，用于验证修复是否具有泛化效果。

推荐量化指标：

- `search.accuracy_at_1`
- `search.recall_at_5`
- `search.keyword_recall_at_5`
- `knowledge_fetcher.success_rate`
- `profile.success_rate`
- `writeback.success_rate`
- `episode_generation.success_rate`
- `negative_control.zero_hit_rate`

当前 fixture 结构：

- `simulated_stream_batches`
  用于模拟话题级聊天窗口，适合检索、episode、画像、写回等离线量化评估。
- `runtime_trigger_streams`
  用于模拟真正能触发当前 summarizer 阈值的原生聊天流。
  这部分数据满足 `20 条 + 8 小时` 的时间触发条件，可直接用于验证
  “是否进入话题检查”与“无 Bot 发言是否被丢弃”。
- `chat_history_records`
  用于模拟宿主将群聊话题总结后写入长期记忆的主路径。
- `person_writebacks`
  用于模拟发送回复后的稳定人物事实写回。
- `search_cases / time_cases / episode_cases / knowledge_fetcher_cases / profile_cases`
  用于直接驱动量化检索评估。
- `negative_control_cases`
  用于验证“无 Bot 发言的群聊片段应被忽略”。

覆盖主题：

- 值班柜第二层的备用物资与物资报备
- 停电夜投影仪抢救与应急灯 / 橙色延长线盘
- 风铃观测前的温湿度计校准与无糖姜茶
- 东侧窗边狸花猫、绿色硬壳笔记本与黄铜回形针
- 无 Bot 参与的零食闲聊负样本

使用建议：

- 如果要验证“当前 summarizer 是否真的会被触发”，优先喂 `runtime_trigger_streams`。
- 如果要验证“当前实现是否真正符合总结后写入和检索设计”，优先喂 `simulated_stream_batches` 与 `chat_history_records`。
- 如果要快速跑检索、画像、episode、写回指标，直接使用 `chat_history_records + person_writebacks + cases`。
- 如果要切换到第二套压力数据，可在运行 benchmark 前设置
  `A_MEMORIX_BENCHMARK_DATA_FILE=pytests/A_memorix_test/data/benchmarks/group_chat_stream_memory_benchmark_hard.json`。
