# -*- coding: utf-8 -*-
"""归一化：把各解析器产出的松散结果统一为标准题目结构。"""

from __future__ import annotations

import re
from typing import Any, Iterable, List, Optional, Sequence, Tuple, Union

from .schema import (
    DEFAULT_JUDGE_ANSWERS,
    DEFAULT_JUDGE_OPTIONS,
    LETTERS,
    Question,
    ValidationError,
)

# 选项前缀：(A) 内容 / 【A】内容 / A. 内容 / A、内容 / A）内容 / A：内容
_BRACKET_PREFIX = re.compile(r"^\s*[（(【\[]\s*([A-Za-z])\s*[)）】\]]\s*[、.．,，:：]?\s*(.*)$")
_PLAIN_PREFIX = re.compile(r"^\s*([A-Za-z])\s*[.．、,，:：)）]\s*(.*)$")

# 题干开头的题号：1. 1、 (1) 【1】 第1题 一、
_STEM_NUMBER = re.compile(
    r"^\s*(?:第\s*\d+\s*题|[（(【\[]\s*\d+\s*[)）】\]]|\d+\s*[.．、,，:：)）]\s*|[一二三四五六七八九十]+\s*[、.．]\s*)"
)

# 题干中残留的答案标记
_ANSWER_IN_STEM = re.compile(
    r"[（(\[【]?\s*(?:正确答案|参考答案|答案|answer|Answer|ANS|KEY)\s*[:：]?\s*[A-Za-z正确错误对错√×,，、\s]*[)）\]】]?\s*$"
)

# 需要清理的噪声字符（参考项目 v1.2 公告中提到的 "极：" 等异常字样）
_NOISE_PATTERNS = [re.compile(r"极\s*[:：]")]

# 判断题为真的/假的答案写法
_TRUE_WORDS = {"正确", "对", "√", "V", "T", "TRUE", "是", "1", "Y", "YES"}
_FALSE_WORDS = {"错误", "错", "×", "X", "F", "FALSE", "否", "0", "N", "NO"}

_MULTI_HINT = re.compile(r"[（(【\[]?\s*多\s*选\s*[)）】\]]?|多选题")
_JUDGE_HINT = re.compile(r"判断|对错|正确与否")


def clean_text(text: Any) -> str:
    """清理题干/选项中的异常字符与多余空白。"""
    if text is None:
        return ""
    s = str(text)
    s = s.replace("\u3000", " ").replace("\xa0", " ")
    for pat in _NOISE_PATTERNS:
        s = pat.sub("", s)
    s = re.sub(r"[ \t]+", " ", s)
    return s.strip()


def strip_question_number(stem: str) -> str:
    """去掉题干开头的题号，如 "1." "第3题" "(4)"。"""
    s = clean_text(stem)
    s = _STEM_NUMBER.sub("", s, count=1)
    return s.strip()


def strip_answer_in_stem(stem: str) -> str:
    """去掉题干末尾残留的 "（答案：A）" 之类内容。"""
    s = clean_text(stem)
    for _ in range(3):
        new = _ANSWER_IN_STEM.sub("", s)
        if new == s:
            break
        s = new
    return s.strip()


def normalize_options(options: Sequence[Any]) -> List[str]:
    """把选项统一为 "A.内容" 形式，并按位置补齐字母前缀。

    若源数据已提供连续的 A、B、C… 字母则沿用，否则按位置重新编号，
    保证 option[0] 恒等于选项字母（参考项目依赖该约定判分）。
    """
    contents: List[str] = []
    letters: List[str] = []
    for raw in options:
        if raw is None:
            continue
        text = clean_text(raw)
        if not text:
            continue
        m = _BRACKET_PREFIX.match(text) or _PLAIN_PREFIX.match(text)
        if m:
            letters.append(m.group(1).upper())
            contents.append(clean_text(m.group(2)))
        else:
            letters.append("")
            contents.append(text)

    expected = list(LETTERS[: len(contents)])
    detected = [l for l in letters]
    if detected != expected:
        # 源数据字母缺失或不连续，按位置重新编号
        letters = expected
    return [f"{letters[i]}.{contents[i]}" for i in range(len(contents))]


def normalize_answer(raw: Any, option_count: int) -> Union[str, List[str]]:
    """把各种答案写法统一为字母（单选/判断为字符串，多选为数组）。"""
    letters: List[str] = []
    judge_flag = False

    if isinstance(raw, (list, tuple, set)):
        for item in raw:
            letters.extend(_extract_letters(item))
    else:
        text = clean_text(raw)
        if text.upper().strip(".,;，；、 ") in _TRUE_WORDS or text in _TRUE_WORDS:
            return "A"
        if text.upper().strip(".,;，；、 ") in _FALSE_WORDS or text in _FALSE_WORDS:
            return "B"
        letters = _extract_letters(text)

    valid = [l for l in letters if LETTERS.index(l) < option_count]
    seen: List[str] = []
    for l in valid:
        if l not in seen:
            seen.append(l)
    if not seen:
        raise ValidationError(f"无法从答案 {raw!r} 中解析出有效选项字母")
    if len(seen) == 1 and not judge_flag:
        return seen[0]
    return sorted(seen)


def _extract_letters(value: Any) -> List[str]:
    """从文本中抽取 A-Z 字母（忽略大小写）。"""
    if value is None:
        return []
    text = clean_text(value)
    if not text:
        return []
    return [ch.upper() for ch in text if ch.isascii() and ch.isalpha()]


def detect_type(stem: str, options: Sequence[str], answer: Union[str, List[str]],
                hint: Optional[str] = None) -> str:
    """推断题型：single / multi / judge。"""
    if hint:
        h = str(hint).lower()
        if h in ("single", "multi", "judge"):
            return h
        if "多" in str(hint):
            return "multi"
        if "判断" in str(hint):
            return "judge"
        if "单选" in str(hint):
            return "single"

    if _MULTI_HINT.search(stem or ""):
        return "multi"
    if isinstance(answer, list) and len(answer) > 1:
        return "multi"
    if _JUDGE_HINT.search(stem or ""):
        return "judge"
    if _looks_like_judge(options):
        return "judge"
    return "single"


def _looks_like_judge(options: Sequence[str]) -> bool:
    if len(options) != 2:
        return False
    bodies = []
    for opt in options:
        m = _BRACKET_PREFIX.match(opt) or _PLAIN_PREFIX.match(opt)
        bodies.append(clean_text(m.group(2)) if m else clean_text(opt))
    joined = "".join(bodies)
    return all(b in _TRUE_WORDS or b in _FALSE_WORDS for b in bodies) and len(joined) >= 2


def build_question(stem: str, options: Sequence[Any], answer: Any,
                   chapter: Any = 1, qtype: Optional[str] = None) -> Question:
    """把松散字段组装成校验通过的 Question 对象。"""
    stem_clean = strip_answer_in_stem(strip_question_number(stem))
    if not stem_clean:
        raise ValidationError("题干为空")

    opts = normalize_options(options) if options else []
    if not opts:
        opts = list(DEFAULT_JUDGE_OPTIONS)

    ans = normalize_answer(answer, len(opts)) if answer not in (None, "", []) else None
    if ans is None:
        raise ValidationError("缺少答案")

    final_type = detect_type(stem_clean, opts, ans, qtype)
    if final_type == "judge" and len(opts) < 2:
        opts = list(DEFAULT_JUDGE_OPTIONS)

    if final_type == "multi" and isinstance(ans, str):
        ans = [ans]

    return Question(
        question=stem_clean,
        options=opts,
        answer=ans,
        type=final_type,
        chapter=_coerce_chapter(chapter),
    )


def _coerce_chapter(value: Any) -> int:
    """章节统一为整数；非数字章节按出现顺序由上层回退为 1。"""
    if value is None or value == "":
        return 1
    if isinstance(value, bool):
        return 1
    if isinstance(value, int):
        return value
    text = clean_text(value)
    m = re.search(r"\d+", text)
    if m:
        return int(m.group())
    chinese = _chinese_to_int(text)
    return chinese if chinese else 1


_CN_DIGITS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
              "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def _chinese_to_int(text: str) -> Optional[int]:
    if not text:
        return None
    if text in _CN_DIGITS:
        return _CN_DIGITS[text]
    m = re.match(r"^十([一二三四五六七八九])$", text)
    if m:
        return 10 + _CN_DIGITS[m.group(1)]
    return None


def is_answer_word(value: Any) -> bool:
    """判断给定文本是否是判断题语义的答案词。"""
    text = clean_text(value).upper()
    return text in _TRUE_WORDS or text in _FALSE_WORDS


def judge_answer_to_letter(value: Any) -> Optional[str]:
    text = clean_text(value).upper()
    if text in _TRUE_WORDS:
        return "A"
    if text in _FALSE_WORDS:
        return "B"
    return None
