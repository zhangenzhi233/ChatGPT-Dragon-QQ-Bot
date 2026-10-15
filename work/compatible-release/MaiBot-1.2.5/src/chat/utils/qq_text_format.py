"""把 QQ 回复中的常见数学标记转成可读文本；代码和不支持的公式原样保留。"""

from __future__ import annotations

import re

_MATH_TOKENS: dict[str, str] = {
    # 空格
    "\\quad": " ",
    "\\qquad": " ",
    "\\,": " ",
    "\\;": " ",
    "\\:": " ",
    "\\ ": " ",
    # 运算与关系
    "\\times": "×",
    "\\cdot": "·",
    "\\div": "÷",
    "\\leq": "≤",
    "\\le": "≤",
    "\\geq": "≥",
    "\\ge": "≥",
    "\\neq": "≠",
    "\\ne": "≠",
    "\\approx": "≈",
    "\\equiv": "≡",
    "\\pm": "±",
    "\\mp": "∓",
    "\\infty": "∞",
    "\\sum": "∑",
    "\\prod": "∏",
    "\\int": "∫",
    "\\to": "→",
    "\\rightarrow": "→",
    "\\Rightarrow": "⇒",
    "\\leftarrow": "←",
    "\\in": "∈",
    "\\notin": "∉",
    "\\subset": "⊂",
    "\\cup": "∪",
    "\\cap": "∩",
    "\\angle": "∠",
    "\\perp": "⊥",
    "\\parallel": "∥",
    "\\degree": "°",
    "\\circ": "°",
    "\\ldots": "…",
    "\\cdots": "…",
    "\\dots": "…",
    "\\%": "%",
    "\\#": "#",
    "\\&": "&",
    "\\_": "_",
    "\\{": "{",
    "\\}": "}",
    # 希腊字母（大写）
    "\\Alpha": "Α",
    "\\Beta": "Β",
    "\\Gamma": "Γ",
    "\\Delta": "Δ",
    "\\Epsilon": "Ε",
    "\\Zeta": "Ζ",
    "\\Eta": "Η",
    "\\Theta": "Θ",
    "\\Iota": "Ι",
    "\\Kappa": "Κ",
    "\\Lambda": "Λ",
    "\\Mu": "Μ",
    "\\Nu": "Ν",
    "\\Xi": "Ξ",
    "\\Omicron": "Ο",
    "\\Pi": "Π",
    "\\Rho": "Ρ",
    "\\Sigma": "Σ",
    "\\Tau": "Τ",
    "\\Upsilon": "Υ",
    "\\Phi": "Φ",
    "\\Chi": "Χ",
    "\\Psi": "Ψ",
    "\\Omega": "Ω",
    # 希腊字母（小写）
    "\\alpha": "α",
    "\\beta": "β",
    "\\gamma": "γ",
    "\\delta": "δ",
    "\\epsilon": "ε",
    "\\varepsilon": "ε",
    "\\zeta": "ζ",
    "\\eta": "η",
    "\\theta": "θ",
    "\\vartheta": "ϑ",
    "\\iota": "ι",
    "\\kappa": "κ",
    "\\lambda": "λ",
    "\\mu": "μ",
    "\\nu": "ν",
    "\\xi": "ξ",
    "\\omicron": "ο",
    "\\pi": "π",
    "\\varpi": "ϖ",
    "\\rho": "ρ",
    "\\sigma": "σ",
    "\\varsigma": "ς",
    "\\tau": "τ",
    "\\upsilon": "υ",
    "\\phi": "φ",
    "\\varphi": "φ",
    "\\chi": "χ",
    "\\psi": "ψ",
    "\\omega": "ω",
}


_WRAPPERS = frozenset(("text", "mathrm", "mathbf", "operatorname", "boxed"))
_FRACTIONS = frozenset(("frac", "tfrac", "dfrac"))
_COMMAND = re.compile(r"\\([A-Za-z]+|[^\n])")
_FENCE = re.compile(r"^[ \t]*(`{3,}|~{3,})[^\n]*", re.MULTILINE)
_ATOM = re.compile(r"(?:[^\W\d_](?:_\w+)*|\d+(?:\.\d+)?)\Z")


class _UnsupportedMath(ValueError):
    """公式含不支持或损坏的结构，调用方保留整个原式。"""


def _group(text: str) -> str:
    """给复合分子/分母补括号，保持运算优先级。"""
    if _ATOM.fullmatch(text):
        return text
    if text.startswith("(") and text.endswith(")"):
        depth = 0
        for index, char in enumerate(text):
            depth += (char == "(") - (char == ")")
            if depth < 0 or (depth == 0 and index != len(text) - 1):
                break
        else:
            if depth == 0:
                return text
    return f"({text})"


class _MathReader:
    """扫描明确的数学区；递归花括号保持结构，未知命令拒绝转换。"""

    def __init__(self, text: str, depth: int = 0) -> None:
        self.text = text
        self.pos = 0
        self.depth = depth
        if depth > 40:
            raise _UnsupportedMath("公式嵌套过深")

    def skip_space(self) -> None:
        while self.pos < len(self.text) and self.text[self.pos].isspace():
            self.pos += 1

    def argument(self) -> str:
        self.skip_space()
        if self.pos >= len(self.text) or self.text[self.pos] != "{":
            raise _UnsupportedMath("缺少花括号参数")
        start = self.pos + 1
        self.pos = start
        depth = 1
        while self.pos < len(self.text):
            char = self.text[self.pos]
            if char == "\\":
                match = _COMMAND.match(self.text, self.pos)
                if match:
                    self.pos = match.end()
                    continue
            depth += (char == "{") - (char == "}")
            if depth == 0:
                inner = self.text[start:self.pos]
                self.pos += 1
                return _MathReader(inner, self.depth + 1).read()
            self.pos += 1
        raise _UnsupportedMath("花括号未闭合")

    def read(self) -> str:
        pieces: list[str] = []
        while self.pos < len(self.text):
            char = self.text[self.pos]
            if char == "}":
                raise _UnsupportedMath("多余的右花括号")
            if char == "{":
                pieces.append(f"({self.argument()})")
                continue
            if char in "_^" and self.pos + 1 < len(self.text) and self.text[self.pos + 1] == "{":
                self.pos += 1
                content = self.argument()
                pieces.append(char + (content if len(content) == 1 or content.isdecimal() else f"({content})"))
                continue
            if char != "\\":
                # 需要布局环境的结构由完整公式保留，避免误解释成文本。
                if char in "&$":
                    raise _UnsupportedMath("不支持的布局或定界符")
                pieces.append(char)
                self.pos += 1
                continue
            match = _COMMAND.match(self.text, self.pos)
            if match is None:
                raise _UnsupportedMath("反斜杠缺少命令")
            name = match.group(1)
            self.pos = match.end()
            if name in _FRACTIONS:
                numerator, denominator = self.argument(), self.argument()
                if not numerator or not denominator:
                    raise _UnsupportedMath("空分数")
                value = f"{_group(numerator)}/{_group(denominator)}"
                # 分数整体的幂或相邻乘法也需要保留原来的分组。
                following = self.text[self.pos:].lstrip()
                if following and (following[0].isalnum() or following[0] in "(^_"):
                    value = f"({value})"
                pieces.append(value)
            elif name == "sqrt":
                self.skip_space()
                order = None
                if self.pos < len(self.text) and self.text[self.pos] == "[":
                    end = self.text.find("]", self.pos + 1)
                    if end < 0:
                        raise _UnsupportedMath("根指数未闭合")
                    order = _MathReader(self.text[self.pos + 1:end], self.depth + 1).read()
                    if not order:
                        raise _UnsupportedMath("空根指数")
                    self.pos = end + 1
                radicand = self.argument()
                pieces.append(f"√({radicand})" if order in (None, "2") else f"{_group(order)}次根号({radicand})")
            elif name in _WRAPPERS:
                if name == "operatorname" and self.pos < len(self.text) and self.text[self.pos] == "*":
                    self.pos += 1
                content = self.argument()
                pieces.append(f"[{content}]" if name == "boxed" else content)
            elif name in ("left", "right", "big", "Big", "bigg", "Bigg"):
                self.skip_space()
                if self.pos >= len(self.text) or self.text[self.pos] not in "()[]|.":
                    raise _UnsupportedMath("不支持的定界符")
                delimiter = self.text[self.pos]
                self.pos += 1
                pieces.append("" if delimiter == "." else delimiter)
            elif match.group(0) in _MATH_TOKENS:
                pieces.append(_MATH_TOKENS[match.group(0)])
            else:
                raise _UnsupportedMath(f"未知命令 {name}")
        return re.sub(r"\s+", " ", "".join(pieces)).strip()


def _escaped(text: str, index: int) -> bool:
    """奇数个反斜杠表示转义，避免把转义美元当公式。"""
    count = 0
    while index > 0 and text[index - 1] == "\\":
        count += 1
        index -= 1
    return count % 2 == 1


def _math_zone(text: str, index: int) -> tuple[str, int] | None:
    """找到明确成对的数学区；数字开头的单美元仅在含运算符时成立。"""
    if _escaped(text, index):
        return None
    for opener, closer in (("$$", "$$"), (r"\[", r"\]"), (r"\(", r"\)"), ("$", "$")):
        if not text.startswith(opener, index):
            continue
        start = index + len(opener)
        if opener == "$" and (start >= len(text) or text[start].isspace() or text[start] == "$"):
            return None
        end = text.find(closer, start)
        while end >= 0 and _escaped(text, end):
            end = text.find(closer, end + len(closer))
        if end < 0:
            return None
        expression = text[start:end]
        if opener == "$":
            if not expression or expression[-1].isspace() or "\n" in expression:
                return None
            if expression[0].isdigit() and not re.search(r"[=<>+*/\\^_]", expression):
                return None
        original = text[index:end + len(closer)]
        try:
            result = _MathReader(expression).read()
        except _UnsupportedMath:
            return original, end + len(closer)
        if not result:
            return original, end + len(closer)
        if opener in ("$$", r"\["):
            if index > 0 and text[index - 1] != "\n":
                result = "\n" + result
            after = end + len(closer)
            if after < len(text) and text[after] != "\n":
                result += "\n"
        return result, end + len(closer)
    return None


def _bold(text: str) -> str:
    """仅去掉边界明确的粗体；保留乘方、变量和 Python 双下划线名字。"""
    text = re.sub(r"(?<![A-Za-z0-9_*])\*\*(?=\S)(.+?)(?<=\S)\*\*(?![A-Za-z0-9_*])", r"\1", text)
    return re.sub(r"(?<![A-Za-z0-9_])__(?=\S)(.+?)(?<=\S)__(?![A-Za-z0-9_])",
                  lambda m: m.group(0) if re.fullmatch(r"[A-Za-z0-9_]+", m.group(1)) else m.group(1), text)


def format_qq_text(text: str) -> str:
    """QQ 可读转换：围栏/行内代码、未知公式透传，其余数学和粗体保守处理。"""
    pieces: list[str] = []
    plain: list[str] = []
    cursor = 0

    def flush() -> None:
        pieces.append(_bold("".join(plain)))
        plain.clear()

    while cursor < len(text):
        fence = _FENCE.match(text, cursor)
        if fence:
            marker = fence.group(1)
            close = re.compile(r"^[ \t]*" + re.escape(marker[0]) + "{" + str(len(marker)) + r",}[ \t]*(?=\r?$)", re.MULTILINE)
            closing = close.search(text, fence.end())
            end = closing.end() if closing else len(text)
            flush()
            pieces.append(text[cursor:end])
            cursor = end
            continue
        if text[cursor] == "`":
            run = re.match(r"`+", text[cursor:]).group(0)
            close = re.search(r"(?<!`)" + re.escape(run) + r"(?!`)", text[cursor + len(run):])
            if close:
                end = cursor + len(run) + close.end()
                flush()
                pieces.append(text[cursor:end])
                cursor = end
                continue
        zone = _math_zone(text, cursor)
        if zone:
            flush()
            value, cursor = zone
            pieces.append(value)
            continue
        plain.append(text[cursor])
        cursor += 1
    flush()
    return "".join(pieces)
