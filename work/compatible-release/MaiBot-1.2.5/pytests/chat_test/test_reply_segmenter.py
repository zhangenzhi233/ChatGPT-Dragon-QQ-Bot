"""回复正文确定性分段纯函数测试（不依赖全局配置）。"""

from src.chat.utils.reply_segmenter import contains_fenced_code, split_reply_text


def test_split_is_lossless_on_long_chinese() -> None:
    text = "".join(f"这是第{i}个自然段，包含一些说明性文字。\n" for i in range(1, 80))
    segments = split_reply_text(text)
    assert len(segments) > 1
    assert "".join(segments) == text


def test_split_preserves_brackets_and_newlines() -> None:
    text = "第一行\n\n第二行（带括号）\n第三行（另一个括号）\n"
    segments = split_reply_text(text)
    assert "".join(segments) == text


def test_split_keeps_code_block_intact_with_indentation() -> None:
    text = "代码如下：\n```python\nif x:\n    print(\"输入数字错误\")\n    y = 1\n```\n以上是说明。"
    segments = split_reply_text(text)
    assert "".join(segments) == text
    # 代码块应整体保留（含缩进），不被从任意字符处破坏。
    assert any('print("输入数字错误")' in segment for segment in segments)
    assert any("    y = 1" in segment for segment in segments)


def test_split_does_not_break_english_words() -> None:
    text = "word " * 200
    segments = split_reply_text(text)
    assert "".join(segments) == text
    for segment in segments:
        # 每个分段都不能以半个英文单词结尾或开头。
        assert all(word == "word" for word in segment.split())


def test_short_text_stays_single_segment() -> None:
    text = "第一句。第二句。第三句。"
    segments = split_reply_text(text)
    assert segments == [text]


def test_no_punctuation_long_line_splits_at_safe_boundary() -> None:
    text = "这是一个没有任何标点的超长句子" * 30
    segments = split_reply_text(text)
    assert "".join(segments) == text
    assert len(segments) > 1


def test_contains_fenced_code_detects_triple_backticks() -> None:
    assert contains_fenced_code("```python\nprint(1)\n```")
    assert contains_fenced_code("~~~\ncode\n~~~")
    assert not contains_fenced_code("普通文本")


def test_long_clauses_stay_bounded_even_with_a_comma() -> None:
    text = "甲" * 300 + "，" + "乙" * 500
    parts = split_reply_text(text)
    assert "".join(parts) == text
    assert max(map(len, parts)) <= 240


def test_unclosed_fence_keeps_complete_code_lines() -> None:
    text = "```python\n" + '    print("输入数字错误")\n' * 40
    assert split_reply_text(text) == [text]


def test_host_preserves_indentation_at_long_code_segment_boundaries() -> None:
    from src.maisaka.builtin_tool.context import BuiltinToolRuntimeContext

    text = "```python\n" + '    print("输入数字错误")\n' * 150 + "```"
    parts = BuiltinToolRuntimeContext.post_process_reply_segments(text, enable_chinese_typo=False)
    assert len(parts) > 1
    assert "".join(p.text for p in parts) == text
    assert all(p.text.startswith(("```", "    ")) for p in parts)
