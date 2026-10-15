"""回复正文确定性分段。

把一条过长的普通文本回复拆成多条发送，遵循以下约束：

- 目标每条 120~240 字符，优先在段落、句号/问号/感叹号等自然边界处切分；
- 保留原文的空格、括号、缩进与换行，不删除任何字符；
- 围栏代码块（``` 或 ~~~）整体保留，超过硬上限时才按完整行切分；
- 不在英文单词或标识符中间切分；无标点长句最终按合理字符边界分割；
- 按顺序拼接所有分段必须与原文完全一致（无损）。

本模块是纯函数实现，不依赖全局配置或 I/O，便于单独测试。
"""

from __future__ import annotations

import re

# 默认分段目标区间（字符数）。
DEFAULT_TARGET_MIN = 120
DEFAULT_TARGET_MAX = 240
# 围栏代码块超过该长度才允许按完整行切分，否则整体作为一条（长度例外）。
CODE_BLOCK_HARD_LIMIT = 2000

# 围栏代码块：``` 或 ~~~ 开头，其后可选语言标识，正文到闭合围栏为止。
_FENCE_PATTERN = re.compile(r"`{3,}|~{3,}")
# 句末标点：优先在这些位置之后切分。
_SENTENCE_END_CHARS = frozenset("。！？!?；;")


def _is_ascii_alnum(char: str) -> bool:
    """判断字符是否为 ASCII 字母或数字（用于避免拆英文单词/标识符）。"""
    return char.isascii() and char.isalnum()


def _iter_sentence_chunks(text: str):
    """按句末标点或换行边界产出文本块，每个块保留其结尾的标点/换行。

    切分点只落在句末标点（。！？!?；;）之后或换行符处，因此逗号、空格、
    括号与缩进都不会被当作强边界，原文逐字符拼接后仍与输入一致。
    """
    buf: list[str] = []
    for char in text:
        buf.append(char)
        if char == "\n" or char in _SENTENCE_END_CHARS:
            yield "".join(buf)
            buf = []
    if buf:
        yield "".join(buf)


def _split_after_secondary_boundary(text: str) -> list[str]:
    """在逗号、分号、冒号或空白等次级边界之后切分，分隔符跟随前一段。"""
    pieces: list[str] = []
    buf: list[str] = []
    for char in text:
        buf.append(char)
        if char in "，,、；;：:" or char.isspace():
            pieces.append("".join(buf))
            buf = []
    if buf:
        pieces.append("".join(buf))
    return pieces


def _is_safe_boundary(prev: str, cur: str) -> bool:
    """判断在 prev 与 cur 之间切分是否安全（不拆英文单词/标识符）。"""
    if _is_ascii_alnum(prev) and _is_ascii_alnum(cur):
        return False
    return True


def _hard_split_word_safe(text: str, target_max: int) -> list[str]:
    """对无任何标点边界的超长块做字符级硬切，尽量不拆英文词。"""
    if len(text) <= target_max:
        return [text]

    segments: list[str] = []
    start = 0
    length = len(text)
    while start < length:
        end = min(start + target_max, length)
        if end < length:
            cut = end
            while cut > start:
                prev = text[cut - 1]
                cur = text[cut]
                if _is_safe_boundary(prev, cur):
                    break
                cut -= 1
            if cut == start:
                # 找不到安全边界（整段都是连续 ASCII 词），退回目标长度硬切。
                cut = end
            end = cut
        segments.append(text[start:end])
        start = end
    return segments


def _pack_chunks(chunks: list[str], target_max: int) -> list[str]:
    """按顺序把小块贪心打包，尽量不超 target_max，单块超长则原样保留。"""
    segments: list[str] = []
    buf = ""
    for chunk in chunks:
        if not chunk:
            continue
        if len(chunk) >= target_max:
            if buf:
                segments.append(buf)
                buf = ""
            segments.append(chunk)
            continue
        if buf and len(buf) + len(chunk) > target_max:
            segments.append(buf)
            buf = chunk
        else:
            buf += chunk
    if buf:
        segments.append(buf)
    return segments


def _split_long_sentence(chunk: str, target_min: int, target_max: int) -> list[str]:
    """拆分单个超过 target_max 的块，先试次级边界，再按字符硬切。"""
    del target_min  # 保留参数以对齐调用签名，长块拆分以不超长为优先。
    if len(chunk) <= target_max:
        return [chunk]

    pieces = _split_after_secondary_boundary(chunk)
    if len(pieces) > 1 and max(len(piece) for piece in pieces) < len(chunk):
        bounded = [part for piece in pieces for part in _hard_split_word_safe(piece, target_max)]
        packed = _pack_chunks(bounded, target_max)
        if packed:
            return packed

    return _hard_split_word_safe(chunk, target_max)


def _segment_plain_text(text: str, target_min: int, target_max: int) -> list[str]:
    """把非代码文本按句子/换行边界切块后，贪心打包成若干段。"""
    chunks = list(_iter_sentence_chunks(text))
    segments: list[str] = []
    buf = ""
    for chunk in chunks:
        if len(chunk) > target_max:
            if buf:
                segments.append(buf)
                buf = ""
            segments.extend(_split_long_sentence(chunk, target_min, target_max))
            continue
        if buf and len(buf) + len(chunk) > target_max:
            segments.append(buf)
            buf = chunk
        else:
            buf += chunk
    if buf:
        segments.append(buf)
    return segments


def _split_code_block(code_text: str, target_max: int) -> list[str]:
    """拆分围栏代码块：短块整体保留，极长块按完整行切分，不重复/遗漏代码。"""
    if len(code_text) <= CODE_BLOCK_HARD_LIMIT:
        return [code_text]

    lines = code_text.splitlines(keepends=True)
    if not lines:
        return [code_text]

    segments: list[str] = []
    buf = ""
    for line in lines:
        if buf and len(buf) + len(line) > target_max:
            segments.append(buf)
            buf = line
        else:
            buf += line
    if buf:
        segments.append(buf)
    return segments


def _extract_atomic_units(text: str) -> list[tuple[str, bool]]:
    """把文本切成原子单元：围栏代码块（is_code=True）与其余文本（is_code=False）。"""
    units: list[tuple[str, bool]] = []
    pos = 0
    while match := _FENCE_PATTERN.search(text, pos):
        if match.start() > pos:
            units.append((text[pos : match.start()], False))
        fence = match.group(0)
        closing = re.search(re.escape(fence[0]) + "{" + str(len(fence)) + ",}", text[match.end():])
        end = match.end() + closing.end() if closing else len(text)
        units.append((text[match.start():end], True))
        pos = end
    if pos < len(text):
        units.append((text[pos:], False))
    return units


def contains_fenced_code(text: str) -> bool:
    """判断文本是否包含围栏代码块标记（``` 或 ~~~）。"""
    return bool(re.search(r"`{3,}|~{3,}", text))


def split_reply_text(
    text: str,
    *,
    target_min: int = DEFAULT_TARGET_MIN,
    target_max: int = DEFAULT_TARGET_MAX,
) -> list[str]:
    """确定性分段：返回若干文本段，按顺序拼接后与原文一致。"""
    if not text:
        return [text]
    if target_max <= 0:
        target_max = DEFAULT_TARGET_MAX
    if target_min < 0:
        target_min = 0

    segments: list[str] = []
    for unit_text, is_code in _extract_atomic_units(text):
        if is_code:
            segments.extend(_split_code_block(unit_text, target_max))
        else:
            segments.extend(_segment_plain_text(unit_text, target_min, target_max))
    # 代码块之间的空行附着到相邻消息，宿主不会发送纯空白消息。
    packed: list[str] = []
    leading = ""
    for segment in segments:
        if not segment.strip():
            if packed:
                packed[-1] += segment
            else:
                leading += segment
        elif segment:
            packed.append(leading + segment)
            leading = ""
    return packed or [text]
