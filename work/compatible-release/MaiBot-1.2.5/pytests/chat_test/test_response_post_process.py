"""回复后处理元数据测试。"""

from src.chat.utils import utils as chat_utils
from src.chat.utils.utils import ProcessedResponseSegment


class _FixedTypoGenerator:
    """返回固定错别字与纠正内容，隔离词频数据和拼音随机性。"""

    def __init__(self, **_kwargs: object) -> None:
        pass

    def create_typo_sentence(self, _sentence: str) -> tuple[str, str]:
        return "今田见", "天"


def test_typo_correction_marks_quote_previous(monkeypatch) -> None:
    monkeypatch.setattr(chat_utils, "ChineseTypoGenerator", _FixedTypoGenerator)
    monkeypatch.setattr(chat_utils.global_config.response_post_process, "enable_response_post_process", True)
    monkeypatch.setattr(chat_utils.global_config.response_splitter, "enable", False)
    monkeypatch.setattr(chat_utils.global_config.chinese_typo, "enable", True)
    monkeypatch.setattr(chat_utils.global_config.chinese_typo, "enable_correction_quote", True)
    monkeypatch.setattr(chat_utils.global_config.chinese_typo, "correction_quote_probability", 1.0)
    monkeypatch.setattr(chat_utils.random, "random", lambda: 0.0)

    segments = chat_utils.process_llm_response_segments("今天见", enable_splitter=False)

    assert segments == [
        ProcessedResponseSegment("今田见"),
        ProcessedResponseSegment("天", quote_previous=True),
    ]
    assert chat_utils.process_llm_response("今天见", enable_splitter=False) == ["今田见", "天"]


def test_typo_correction_quote_can_be_disabled(monkeypatch) -> None:
    monkeypatch.setattr(chat_utils, "ChineseTypoGenerator", _FixedTypoGenerator)
    monkeypatch.setattr(chat_utils.global_config.response_post_process, "enable_response_post_process", True)
    monkeypatch.setattr(chat_utils.global_config.response_splitter, "enable", False)
    monkeypatch.setattr(chat_utils.global_config.chinese_typo, "enable", True)
    monkeypatch.setattr(chat_utils.global_config.chinese_typo, "enable_correction_quote", False)
    monkeypatch.setattr(chat_utils.random, "random", lambda: 0.0)

    segments = chat_utils.process_llm_response_segments("今天见", enable_splitter=False)

    assert segments == [
        ProcessedResponseSegment("今田见"),
        ProcessedResponseSegment("天"),
    ]


def test_typo_correction_quote_respects_probability(monkeypatch) -> None:
    monkeypatch.setattr(chat_utils, "ChineseTypoGenerator", _FixedTypoGenerator)
    monkeypatch.setattr(chat_utils.global_config.response_post_process, "enable_response_post_process", True)
    monkeypatch.setattr(chat_utils.global_config.response_splitter, "enable", False)
    monkeypatch.setattr(chat_utils.global_config.chinese_typo, "enable", True)
    monkeypatch.setattr(chat_utils.global_config.chinese_typo, "enable_correction_quote", True)
    monkeypatch.setattr(chat_utils.global_config.chinese_typo, "correction_quote_probability", 0.0)
    monkeypatch.setattr(chat_utils.random, "random", lambda: 0.0)

    segments = chat_utils.process_llm_response_segments("今天见", enable_splitter=False)

    assert segments == [
        ProcessedResponseSegment("今田见"),
        ProcessedResponseSegment("天"),
    ]


def test_merge_keeps_typo_correction_at_start_of_quoted_message() -> None:
    segments = [
        ProcessedResponseSegment("今田见"),
        ProcessedResponseSegment("天", quote_previous=True),
        ProcessedResponseSegment("晚点聊"),
    ]

    merged_segments = chat_utils._merge_processed_segments_to_max_count(segments, 2)

    assert merged_segments == [
        ProcessedResponseSegment("今田见"),
        ProcessedResponseSegment("天晚点聊", quote_previous=True),
    ]


def _configure_post_process(monkeypatch, *, enable_typo: bool = False, max_length: int = 512) -> None:
    """把后处理相关配置切到可预期的状态，避免依赖默认配置。"""

    monkeypatch.setattr(chat_utils.global_config.response_post_process, "enable_response_post_process", True)
    monkeypatch.setattr(chat_utils.global_config.response_splitter, "enable", True)
    monkeypatch.setattr(chat_utils.global_config.response_splitter, "max_length", max_length)
    monkeypatch.setattr(chat_utils.global_config.response_splitter, "enable_kaomoji_protection", False)
    monkeypatch.setattr(chat_utils.global_config.chinese_typo, "enable", enable_typo)


def test_long_chinese_answer_is_not_replaced_by_default_reply(monkeypatch) -> None:
    _configure_post_process(monkeypatch, enable_typo=False)

    unit = "这是超长回复的正文内容，必须完整保留，不能被替换成默认短句，也不能丢失尾部。"
    long_text = unit * 40
    assert len(long_text) > 1024

    segments = chat_utils.process_llm_response(long_text)

    assert "".join(segments) == long_text
    assert not any("不知道" in segment or "不晓得" in segment for segment in segments)


def test_many_segments_are_not_forced_into_three_chunks_or_default(monkeypatch) -> None:
    _configure_post_process(monkeypatch, enable_typo=False)

    paragraph = "这是一个中等长度的段落，用于验证长文会被按自然边界切成多条，而不是强行合并成三条超大消息。"
    long_text = "\n\n".join(paragraph for _ in range(30))

    segments = chat_utils.process_llm_response(long_text)

    assert "".join(segments) == long_text
    assert len(segments) > 3
    assert not any("不知道" in segment or "不晓得" in segment for segment in segments)


def test_splitter_disabled_keeps_single_segment(monkeypatch) -> None:
    _configure_post_process(monkeypatch, enable_typo=False)

    text = "第一句。第二句。第三句。"

    assert chat_utils.process_llm_response(text, enable_splitter=False) == [text]


def test_brackets_in_code_are_not_stripped(monkeypatch) -> None:
    _configure_post_process(monkeypatch, enable_typo=False)

    text = 'print("输入数字错误")'

    segments = chat_utils.process_llm_response(text)

    assert segments == [text]


def test_medium_long_story_does_not_inject_typos(monkeypatch) -> None:
    _configure_post_process(monkeypatch, enable_typo=True)
    monkeypatch.setattr(chat_utils, "ChineseTypoGenerator", _FixedTypoGenerator)
    text = "月光照在窗台上，她轻轻说了声晚安。" * 24
    parts = chat_utils.process_llm_response_segments(text)
    assert "".join(p.text for p in parts) == text
