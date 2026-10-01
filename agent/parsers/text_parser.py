# -*- coding: utf-8 -*-
"""文本规则解析器：解析最常见的中文题库纯文本格式。

支持的两大类排版：

1) 多行式::

    1. 毛泽东思想形成和发展的时代背景是()
    A.中国沦为半殖民地半封建社会
    B.帝国主义战争和无产阶级革命
    答案：B

2) 单行式::

    1、毛泽东思想活的灵魂是（） A.实事求是 B.群众路线 C.独立自主 答案：ABC
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

from .base import BaseParser, ParsedDocument, RawQuestion

# 题号开头
_QUESTION_START = re.compile(
    r"^\s*(?:"
    r"第\s*[0-9一二三四五六七八九十]+\s*题"
    r"|[（(【\[]\s*\d+\s*[)）】\]]"
    r"|\d+\s*[.．、,，::)）]"
    r"|[一二三四五六七八九十]{1,3}\s*[、.．]"
    r")"
)

# 章节标题，如 "第一章 毛泽东思想及其历史地位"
_CHAPTER_LINE = re.compile(r"^\s*第\s*([0-9一二三四五六七八九十]+)\s*[章节篇]\s*(.*)$")

# 答案标记
_ANSWER_LINE = re.compile(
    r"[（(\[【]?\s*(?:正确答案|参考答案|答案|answer|Answer|ANS|KEY)\s*[)）\]】]?\s*[:：]?\s*([^\n]*)"
)

# 选项行（多行式）：(A) xxx / A. xxx / A、xxx / A）xxx
_OPTION_LINE = re.compile(
    r"^\s*[（(\[【]?\s*([A-Za-z])\s*[)）\]】]?\s*[.．、,，:：)）]\s*(.*)$"
)

# 选项内联（单行式）
_OPTION_INLINE = re.compile(
    r"(?:^|\s|[。；;，,])\s*[（(\[【]?\s*([A-Ha-h])\s*[)）\]】]?\s*[.．、,，:：)）]\s*",
    re.M,
)

_JUDGE_HINT = re.compile(r"判断|对错|是否正确|正确与否")
_TRUE_WORDS = {"正确", "对", "√", "V", "T", "TRUE", "是", "Y", "YES"}
_FALSE_WORDS = {"错误", "错", "×", "X", "F", "FALSE", "否", "N", "NO"}


class TextParser(BaseParser):
    """纯文本题库解析器。"""

    name = "text"

    @staticmethod
    def supports(path: Path) -> bool:
        return Path(path).suffix.lower() in (".txt", ".text")

    def parse(self, text: str, source: Optional[Path] = None) -> ParsedDocument:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = text.replace("\u3000", " ")
        blocks, chapters = _split_blocks(text)
        doc = ParsedDocument(parser=self.name)
        for block_text, chapter in blocks:
            rq = _parse_block(block_text, chapter)
            if rq is None:
                doc.warnings.append(f"跳过无法解析的片段：{block_text[:40]!r}")
                continue
            doc.questions.append(rq)
        if not doc.questions and text.strip():
            doc.warnings.append("未从文本中解析出任何题目，请检查题库格式。")
        return doc


def _split_blocks(text: str):
    """按题号切分为 (block_text, chapter) 列表，并跟踪章节标题。"""
    lines = text.split("\n")
    blocks: List[tuple] = []
    current: List[str] = []
    chapter = 1
    chapter_at_flush = chapter
    numbered = False

    for line in lines:
        cm = _CHAPTER_LINE.match(line)
        # 章节标题行：只有形如 "第一章 xxx" 且不含选项/答案时，视为章节分隔
        if cm and "答案" not in line and not _OPTION_LINE.match(line) and len(line.strip()) <= 40:
            if current:
                blocks.append(("\n".join(current), chapter_at_flush))
                current = []
            chapter = _cn_to_int(cm.group(1)) or chapter
            chapter_at_flush = chapter
            continue

        if _QUESTION_START.match(line):
            numbered = True
            if current:
                blocks.append(("\n".join(current), chapter_at_flush))
            current = [line]
            chapter_at_flush = chapter
        else:
            if current:
                current.append(line)
            else:
                # 题目之前的零散文本，忽略
                continue
    if current:
        blocks.append(("\n".join(current), chapter_at_flush))

    if not numbered:
        # 没有题号：退化为按空行分块
        parts = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
        return [(p, chapter) for p in parts], None
    return blocks, None


def _parse_block(block: str, chapter: int) -> Optional[RawQuestion]:
    answer_raw = None
    m = None
    for m in _ANSWER_LINE.finditer(block):
        pass  # 取最后一个答案标记
    body = block
    if m:
        answer_raw = m.group(1).strip()
        body = block[: m.start()] + block[m.end():]

    stem, options = _split_stem_options(body)

    if not stem and not options:
        return None
    if not stem:
        return None

    is_judge = bool(_JUDGE_HINT.search(stem)) or (
        not options and _is_judge_answer(answer_raw)
    )
    if answer_raw is None and not options:
        # 既无答案也无选项：视为章节标题等噪声
        return None
    if answer_raw is None and is_judge and not options:
        return None

    qtype = "judge" if is_judge else None
    if not answer_raw and options:
        return None

    return RawQuestion(
        stem=stem,
        options=options,
        answer=answer_raw,
        chapter=chapter,
        qtype=qtype,
    )


def _split_stem_options(body: str):
    """把题干与选项拆开，兼容多行式与单行式。"""
    lines = [l for l in body.split("\n")]
    # 去掉尾部空行
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        return "", []

    # 多行式：至少两行以选项标记开头且字母连续
    opt_lines = []
    for idx, line in enumerate(lines):
        m = _OPTION_LINE.match(line)
        if m:
            opt_lines.append((idx, m.group(1).upper(), line))
    if len(opt_lines) >= 2:
        letters = [l for _, l, _ in opt_lines]
        if _is_consecutive(letters):
            first_idx = opt_lines[0][0]
            stem = "\n".join(lines[:first_idx]).strip()
            options: List[str] = []
            expected = 0
            idx_set = {i: (l, raw) for i, l, raw in opt_lines}
            for i in range(first_idx, len(lines)):
                if i in idx_set:
                    options.append(lines[i].strip())
                    expected += 1
                elif options:
                    # 换行的续行，拼接进上一个选项
                    if lines[i].strip():
                        options[-1] = options[-1] + lines[i].strip()
            return _clean_stem(stem), options

    # 单行式
    text = "\n".join(lines).strip()
    matches = list(_OPTION_INLINE.finditer(text))
    if len(matches) >= 2:
        letters = [m.group(1).upper() for m in matches]
        if _is_consecutive(letters):
            stem = text[: matches[0].start()].strip()
            options = []
            for i, m in enumerate(matches):
                end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
                options.append(text[m.start():end].strip())
            options = [o.rstrip() for o in options]
            return _clean_stem(stem), options

    # 无选项
    return _clean_stem(text), []


def _is_consecutive(letters: List[str]) -> bool:
    if len(letters) < 2:
        return False
    from ..schema import LETTERS

    expected = LETTERS[: len(letters)]
    return list(letters) == list(expected)


def _clean_stem(stem: str) -> str:
    s = re.sub(r"[ \t]+", " ", stem)
    s = re.sub(r"\n+", " ", s)
    return s.strip()


def _is_judge_answer(value) -> bool:
    if value is None:
        return False
    text = str(value).strip().upper()
    return text in _TRUE_WORDS or text in _FALSE_WORDS


_CN_DIGITS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
              "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def _cn_to_int(text: str):
    text = text.strip()
    if text.isdigit():
        return int(text)
    if text in _CN_DIGITS:
        return _CN_DIGITS[text]
    m = re.match(r"^十([一二三四五六七八九])$", text)
    if m:
        return 10 + _CN_DIGITS[m.group(1)]
    return None
