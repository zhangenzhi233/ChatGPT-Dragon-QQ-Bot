"""``format_qq_text`` 纯函数测试：真实截图、复合 / 嵌套分数、粗体、代码保护与误伤场景。

测试不依赖全局配置、网络或文件系统，只校验纯函数的输入输出。
"""

from src.chat.utils.qq_text_format import format_qq_text

# 真实截图里的题目文本（含 ** 粗体与三个 \n\[ ... \] 公式行）。
SCREENSHOT_TEXT = (
    "答案填 **0.5 A**。\n"
    "\\[ V_B-V_A=4,\\quad V_E=V_A-8 \\]\n"
    "\\[\\frac{V_E}{2}+\\frac{V_B-V_C}{2}=0\\]\n"
    "\\[I=\\frac{V_C}{4}=\\boxed{0.5A}\\]"
)


def test_real_screenshot_is_converted_readably() -> None:
    """截图场景：粗体标记去掉，三个公式转可读文本且保留次序与语义。"""
    result = format_qq_text(SCREENSHOT_TEXT)

    assert result.startswith("答案填 0.5 A。")
    assert "**" not in result
    assert "\\[" not in result and "\\]" not in result
    assert "V_B-V_A=4, V_E=V_A-8" in result
    assert "V_E/2+(V_B-V_C)/2=0" in result
    assert "I=V_C/4=[0.5A]" in result
    # 次序不能被打乱。
    assert result.index("V_B-V_A=4") < result.index("V_E/2") < result.index("I=V_C/4")


def test_frac_single_atom_denominator_has_no_extra_parens() -> None:
    """单原子分子 / 分母可省括号：\\frac{a}{b} -> a/b。"""
    assert format_qq_text(r"$x=\frac{a}{b}$") == "x=a/b"


def test_frac_compound_numerator_gets_parentheses() -> None:
    """复合分子要补括号，保住优先级：\\frac{V_B-V_C}{2} -> (V_B-V_C)/2。"""
    assert format_qq_text(r"$\frac{V_B-V_C}{2}$") == "(V_B-V_C)/2"


def test_frac_paren_group_is_atomic_and_not_double_wrapped() -> None:
    """已带圆括号分组的分子不再重复加括号，避免 ((a+b))/(c+d)。"""
    assert format_qq_text(r"$\frac{(a+b)}{c+d}$") == "(a+b)/(c+d)"


def test_nested_frac_is_converted_inner_first() -> None:
    """嵌套分数：内层先转换，外层按优先级补括号。"""
    assert format_qq_text(r"$\frac{\frac{a}{b}}{c}$") == "(a/b)/c"
    assert format_qq_text(r"$\frac{1}{\frac{a}{b}}$") == "1/(a/b)"


def test_sqrt_keeps_grouping() -> None:
    """根号用普通括号保留被开方内容：\\sqrt{x+1} -> √(x+1)。"""
    assert format_qq_text(r"$\sqrt{x+1}$") == "√(x+1)"
    assert format_qq_text(r"$\sqrt{2}$") == "√(2)"
    assert format_qq_text(r"$\sqrt[3]{x}$") == "3次根号(x)"


def test_sqrt_of_frac_keeps_precedence() -> None:
    """根号内含分数：先转换分数，再整体作为根号内内容。"""
    assert format_qq_text(r"$\sqrt{\frac{a}{b}}$") == "√(a/b)"


def test_text_mathbf_mathrm_and_operatorname_keep_content() -> None:
    """\\text / \\mathrm / \\mathbf / \\operatorname 保留内容，不丢字符。"""
    assert format_qq_text(r"$\text{速度}=\frac{s}{t}$") == "速度=s/t"
    assert format_qq_text(r"$\mathrm{d}x$") == "dx"
    assert format_qq_text(r"$\mathbf{v}$") == "v"
    assert format_qq_text(r"$\operatorname{argmax}$") == "argmax"


def test_boxed_keeps_content_as_group() -> None:
    """\\boxed{...} 保留内容并用括号表示方框分组，不丢 0.5A。"""
    assert format_qq_text(r"$\boxed{0.5A}$") == "[0.5A]"


def test_left_right_and_sizing_commands_keep_delimiters() -> None:
    """\\left \\right 与 \\big 尺寸控制只丢尺寸，保留定界符本身。"""
    assert format_qq_text(r"$\left(\frac{a}{b}\right)$") == "(a/b)"
    assert format_qq_text(r"$\big[f(x)\big]$") == "[f(x)]"


def test_spacing_and_greek_and_operators() -> None:
    """\\quad / \\, 转空格，希腊字母与常用运算符转可读符号。"""
    assert format_qq_text(r"$a\quad b$") == "a b"
    assert format_qq_text(r"$a\,b$") == "a b"
    assert format_qq_text(r"$\Omega \times \alpha \cdot \beta$") == "Ω × α · β"
    assert format_qq_text(r"$a \leq b \geq c \neq d \pm e$") == "a ≤ b ≥ c ≠ d ± e"
    assert format_qq_text(r"$\infty \sum \int$") == "∞ ∑ ∫"


def test_subscript_and_superscript_keep_grouping() -> None:
    """下标可保留 V_C；复合下标 / 指数用括号保留分组，平方可保留 ^2。"""
    assert format_qq_text(r"$V_C$") == "V_C"
    assert format_qq_text(r"$V_{AB}$") == "V_(AB)"
    assert format_qq_text(r"$x^2$") == "x^2"
    assert format_qq_text(r"$x^{n-1}$") == "x^(n-1)"


def test_math_zones_in_all_delimiter_forms() -> None:
    """四种明确成对的定界符都转换：$$…$$、\\[…\\]、\\(…\\)、$…$。"""
    assert format_qq_text("$$a+b$$") == "a+b"
    assert format_qq_text(r"\[a+b\]") == "a+b"
    assert format_qq_text(r"\(a+b\)") == "a+b"
    assert format_qq_text("$a+b$") == "a+b"


def test_bold_markers_removed_but_single_asterisk_and_variables_kept() -> None:
    """成对 ** 与 __ 去掉；单个 *、乘法与变量里的 __ 不动。"""
    assert format_qq_text("**粗体**") == "粗体"
    assert format_qq_text("__粗体__") == "粗体"
    assert format_qq_text("答案是 **0.5 A** 哦") == "答案是 0.5 A 哦"
    assert format_qq_text("a*b=ab") == "a*b=ab"
    assert format_qq_text("2*3*4") == "2*3*4"
    assert format_qq_text("变量 __init__ 是构造方法") == "变量 __init__ 是构造方法"
    assert format_qq_text("未成对 **粗体") == "未成对 **粗体"


def test_fenced_code_block_is_byte_identical() -> None:
    """围栏代码块（``` 与 ~~~）原字节保留，公式与粗体都不动。"""
    text = '看这段：\n```python\ns = "$x$"\npath = r"C:\\tmp\\a"\ny = a*b\n```\n就这样'
    result = format_qq_text(text)
    assert "```python\ns = \"$x$\"\npath = r\"C:\\tmp\\a\"\ny = a*b\n```" in result

    tilde = "说明\n~~~\n**bold** $\\frac{a}{b}$\n~~~\n结束"
    assert format_qq_text(tilde) == tilde


def test_unclosed_fence_protects_rest_of_message() -> None:
    """未闭合围栏块保护到文本结尾，不猜公式。"""
    text = "示例：\n```\n**加粗** $\\frac{a}{b}$\n"
    assert format_qq_text(text) == text


def test_inline_code_is_byte_identical() -> None:
    """行内代码原样：反引号内的公式 / 反斜杠 / 星号都不改。"""
    text = "写成 `$\\frac{a}{b}$` 和 `C:\\Users\\me\\file.txt` 这样"
    result = format_qq_text(text)
    assert "`$\\frac{a}{b}$`" in result
    assert "`C:\\Users\\me\\file.txt`" in result


def test_unpaired_backtick_is_treated_as_plain_text() -> None:
    """未成对反引号按普通文本处理，后面的公式仍可转换。"""
    assert format_qq_text("反引号 ` 然后 $x+1$") == "反引号 ` 然后 x+1"


def test_plain_money_is_not_a_formula() -> None:
    """普通金额 $5 / $10 / $100 不得被当成公式。"""
    assert format_qq_text("价格是 $5，另一个 $10") == "价格是 $5，另一个 $10"
    assert format_qq_text("总共 $100 元") == "总共 $100 元"
    assert format_qq_text("$5 到 $10 之间") == "$5 到 $10 之间"


def test_money_inside_sentence_with_math_still_safe() -> None:
    """同一句里既有金额又有真公式时，金额不动、公式照转。"""
    result = format_qq_text(r"花了 $5，精度 $0 < \frac{a}{b}$ 更高")
    assert "$5" in result
    assert "a/b" in result


def test_windows_paths_are_untouched() -> None:
    """Windows 路径里的反斜杠不做全局删除。"""
    text = r"路径 D:\qq-ai-companion\work\a_b\file.txt 和 \\server\share\dir"
    assert format_qq_text(text) == text


def test_unknown_command_is_preserved_whole() -> None:
    """未知命令整体保留，绝不吞掉它的内容。"""
    assert format_qq_text(r"$\foobar{x+1}$") == r"$\foobar{x+1}$"
    assert r"\foobar" in format_qq_text(r"$\foobar{x+1}$")
    assert "x+1" in format_qq_text(r"$\foobar{x+1}$")


def test_corrupted_or_unsupported_syntax_keeps_original() -> None:
    """语法损坏（未闭合花括号 / 未闭合数学区）时整体保留原公式。"""
    assert format_qq_text(r"$\frac{a}{b$") == r"$\frac{a}{b$"
    assert format_qq_text(r"$a+b") == r"$a+b"
    assert format_qq_text(r"\[a+b") == r"\[a+b"
    assert format_qq_text(r"\(a+b") == r"\(a+b"


def test_frac_inside_code_and_chinese_text_outside_math_only() -> None:
    """中文字符串里的 \\frac 只在数学区转换，代码 / 示例里的保持原样。"""
    assert format_qq_text("命令 \\frac{a}{b} 的写法") == "命令 \\frac{a}{b} 的写法"
    assert format_qq_text(r"源码示例 `\frac{a}{b}`") == r"源码示例 `\frac{a}{b}`"
    assert format_qq_text(r"$c=\frac{a}{b}$ 是公式") == "c=a/b 是公式"


def test_idempotent_on_repeated_calls() -> None:
    """幂等性：对结果再调用一次不产生变化。"""
    samples = [
        SCREENSHOT_TEXT,
        r"$a=\frac{b}{c}$ 和 **粗体** 与 $5",
        "```\n$x$ **b**\n```\n$\\sqrt{x}$",
        r"$\foobar{x}$",
        "普通文本，没有公式。",
    ]
    for sample in samples:
        once = format_qq_text(sample)
        assert format_qq_text(once) == once, sample


def test_empty_and_whitespace_input() -> None:
    """空字符串原样返回，空白文本不被破坏。"""
    assert format_qq_text("") == ""
    assert format_qq_text("   ") == "   "
    assert format_qq_text("\n\n") == "\n\n"


def test_no_global_backslash_or_brace_deletion() -> None:
    """不做无边界全局删反斜杠 / 花括号：文本外的反斜杠与花括号保留。"""
    text = r"转义 \{ 和 \} 以及单独的反斜杠 \ 都保留"
    assert format_qq_text(text) == text


def test_fraction_power_and_operator_precedence() -> None:
    assert format_qq_text(r"\[\frac{a+b}{c+d}\]") == "(a+b)/(c+d)"
    assert format_qq_text(r"\(\frac{a}{b}^2\)") == "(a/b)^2"
    assert format_qq_text(r"\(\frac{a}{b}c\)") == "(a/b)c"
    assert format_qq_text(r"\(\frac{2V}{4\Omega}\)") == "(2V)/(4Ω)"
    assert format_qq_text(r"\(\frac{a}{bc}\)") == "a/(bc)"


def test_unknown_nested_command_preserves_complete_formula() -> None:
    original = r"\[\frac{\unknown{a}}{b}\]"
    assert format_qq_text(original) == original
    assert format_qq_text(r"$a**b**c$") == "a**b**c"


def test_fence_is_not_closed_by_backticks_inside_a_code_line() -> None:
    original = '```python\ns = "```"\nx = "$x$"\n# **bold**\n```'
    assert format_qq_text(original) == original
