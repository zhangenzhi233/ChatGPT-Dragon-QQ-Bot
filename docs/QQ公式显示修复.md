# QQ 公式显示修复

QQ 的普通文字消息直接显示 LaTeX 和 Markdown 源码，旧分段还会把数学定界符拆在两条消息中。

现在 QQ 的普通回复在分段前使用 `src/chat/utils/qq_text_format.py` 做保守转换，支持常见分数、根号、上下标、符号和粗体。代码块、行内代码、金额、路径保持原样。未知或损坏公式整体保留；不引入第三方依赖。复合分子/分母加括号，避免改变运算顺序。

接入点为 `BuiltinToolRuntimeContext.post_process_reply_message_items`，仅影响 QQ；显式跳过后处理的语音等插件保持原文，保留其授权匹配。发生格式转换的回复不随机注入错字。回复生成器按 QQ 普通文字显示能力增加中英日一致的格式说明，要求自然语言讲解时以文字说明为主。

独立验证：63 项测试通过，Ruff 通过；包括截图公式、复合与嵌套分数、幂次、代码与路径保护、未知公式保留、平台及插件跳过隔离。原长回复分段回归通过。

运行：在 MaiBot 根目录执行 `.venv\Scripts\python.exe -m pytest pytests/chat_test/test_qq_text_format.py pytests/chat_test/test_reply_segmenter.py pytests/chat_test/test_response_post_process.py pytests/maisaka/test_reply_before_post_process.py -q`。

额外扩展检查中的旧 `test_behavior_style_prompt.py::test_planner_context_uses_behavior_style_instead_of_personality` 断言与已有身份一致性实现冲突；Planner 当前本来包含 `identity`，本次没有修改 Planner 相关文件。这项不计入 63 项通过集合，不宣称整仓所有测试通过。
