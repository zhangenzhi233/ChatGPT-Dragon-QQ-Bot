import pytest

from plugins.SilverDragonVoice.voice_intent import VOICE_REQUEST_CANDIDATE_PATTERN, is_voice_request


@pytest.mark.parametrize(
    "text",
    [
        "我给你添加了语言的功能，看看你说话效果怎么样",
        "我给你添加了语音的功能，看看你说话效果怎么样",
        "我可以听听你说话的声音吗",
        "用语音回复我",
        "请用语音回复我？",
        "发条语音给我。",
        "让我听听你的声音！",
        "能用语音回复吗",
        "你能不能给我发一条语音？",
        "可以让我听听你的声音吗",
        "我想听听你的声音",
        "试试新声音吧",
        "现在能发语音了吗",
        "让我听下你的声音",
        "我不知道你的声音，想听听",
        "我想听你的声音",
        "想听一下你的声音",
        "不用担心，我想听听你的声音",
        "可以发送语音吗",
        "可以发送语言吗",
        "我修复了原来的问题，现在试试语音效果",
        "我修复了原来的语音识别问题，现在试试语音效果吧",
        "我想知道你今天过得怎么样，用语音告诉我吧",
        "你今天过得怎么样？用语音告诉我。",
        "用语音回答这个问题",
    ],
)
def test_natural_current_user_requests_match_candidate_and_are_accepted(text):
    assert VOICE_REQUEST_CANDIDATE_PATTERN.fullmatch(text) is not None
    assert is_voice_request(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "/语音 你好",
        "不要用语音回复我",
        "我不想听你的声音",
        "如果可以的话，他会发语音吗",
        "他说想听听你的声音",
        "她引用了‘让我听听你的声音’这句话",
        "你的声音好可爱",
        "我觉得你声音好听",
        "播放这个语音",
        "怎么更换声音",
        "语音发送失败了",
        "我给你添加了语音功能",
        "请用中文说话",
        "请用温柔的语气说话",
        "我想看你语言水平",
        "不要\n用语音回复我",
        "我想听她发语音，要怎么做",
        "我想让她发语音",
        "我想听他发语音",
        "我想看看可以发送语言的格式",
    ],
)
def test_non_requests_are_rejected(text):
    assert is_voice_request(text) is False
    # 分类器只看当前消息的请求意图，讨论和转述继续普通文字聊天。
    assert VOICE_REQUEST_CANDIDATE_PATTERN.search(text) is None


@pytest.mark.parametrize("text", ["我觉得你声音好听", "播放这个语音", "语音发送失败了", "我给你添加了语音功能"])
def test_voice_discussion_without_a_request_does_not_enter_candidate_path(text):
    assert VOICE_REQUEST_CANDIDATE_PATTERN.fullmatch(text) is None
