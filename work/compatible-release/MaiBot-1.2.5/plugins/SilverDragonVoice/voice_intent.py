"""当前用户文本中的语音请求判定。"""

import re


_VOICE_TOPIC_PATTERN = (
    r"(?:语音|声音|试听|听.{0,16}说话|说话.{0,16}听"
    # 真实截图把“语音”打成“语言”；只接受明确“可以发送语言吗”一类问法。
    r"|^\s*你?(?:可以|能不能|可不可以)发送语言(?:吗|么|嘛|吧)?[？?。！!\s]*$"
    r"|(?:看看|看下|看一下|试看|试试).{0,16}说话|说话.{0,8}效果)"
)
_REQUEST_INTENT_PATTERN = (
    r"(?:想(?:要)?|能不能|可不可以|可以|能|请|麻烦).{0,12}(?:听|发|试|看|用)"
    r"|(?:让我|给我).{0,12}(?:听|发|试|看)"
    r"|(?:听听|听下|听一下|发条|发一条|试试|试看|看看|看下|看一下).{0,16}"
    + _VOICE_TOPIC_PATTERN
    + r"|用.{0,8}语音.{0,8}(?:回复|回答|告诉|讲|说)"
)

_NEGATIVE_REQUEST_PATTERN = re.compile(
    r"(?:不要|别|不想|无需|不用|停止|关闭)[^，。；：,]{0,12}(?:语音|声音|说话|听|发)"
)
_HYPOTHETICAL_OR_REPORTED_PATTERN = re.compile(
    r"(?:^|[，。；：])\s*(?:如果|假如|要是|假设|设想)|(?:他说|她说|他们说|朋友说|别人说|有人说|他问|她问|他们问|朋友问|别人问|有人问|转述|引用|提到)"
)
_THIRD_PERSON_TARGET_PATTERN = re.compile(
    r"(?:听(?:听|下|一下)?|看(?:看|下|一下)?|让)\s*(?:他们|她们|他|她)"
    r"|(?:他们|她们|他|她)(?:的)?(?:声音|语音|说话)"
    r"|(?:他们|她们|他|她).{0,4}(?:发|用).{0,4}语音"
)
_QUOTED_TEXT_PATTERN = re.compile(r"[“「『\"].{1,}[”」』\"]")
_MANAGEMENT_PATTERN = re.compile(r"(?:怎么|如何|怎样).{0,12}(?:更换|修改|设置|调整|切换)|(?:更换|修改|设置|调整|切换).{0,12}(?:语音|声音)")
_FAILURE_PATTERN = re.compile(r"(?:语音|声音).{0,8}(?:发送)?失败|(?:发送)?失败.{0,8}(?:语音|声音)")

# 此正则只判断当前用户消息的语音意图，不注册自然语言 Command，
# 让问题保留在普通聊天历史中，并由原有 Replyer 生成上下文回答。
_EXCLUSION_PATTERNS = (
    _NEGATIVE_REQUEST_PATTERN,
    _HYPOTHETICAL_OR_REPORTED_PATTERN,
    _THIRD_PERSON_TARGET_PATTERN,
    _QUOTED_TEXT_PATTERN,
    _MANAGEMENT_PATTERN,
    _FAILURE_PATTERN,
)
_EXCLUSION_LOOKAHEADS = "".join(r"(?!.*?(?:" + pattern.pattern + r"))" for pattern in _EXCLUSION_PATTERNS)
VOICE_REQUEST_CANDIDATE_PATTERN = re.compile(
    r"(?s)^(?!\s*/)" + _EXCLUSION_LOOKAHEADS
    + r"(?=.*?" + _VOICE_TOPIC_PATTERN + r")(?=.*?(?:" + _REQUEST_INTENT_PATTERN + r")).+$"
)


def is_voice_request(text: str) -> bool:
    """判断一整条当前用户消息是否明确请求听到一条语音。

    该函数不处理命令，也不调用模型；它只根据当前消息的中文语义线索判定。
    """

    return VOICE_REQUEST_CANDIDATE_PATTERN.fullmatch(str(text or "")) is not None
