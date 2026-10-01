# -*- coding: utf-8 -*-
"""表格解析器：处理 CSV / TSV / Excel / Markdown 表格。

自动识别表头（题干、选项、答案、章节、题型等），
并兼容「单列合并选项」与「选项A/选项B 分列」两种排版。
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from .base import BaseParser, ParsedDocument, RawQuestion
from .text_parser import _OPTION_INLINE

_STEM_KEYS = {"题干", "题目", "问题", "试题", "题", "题干内容", "题目内容",
              "试题内容", "question", "stem", "content", "title"}
_ANSWER_KEYS = {"答案", "正确答案", "参考答案", "标准答案", "answer", "key", "ans"}
_CHAPTER_KEYS = {"章节", "章", "章节号", "所属章节", "章次", "章节名", "chapter"}
_TYPE_KEYS = {"题型", "类型", "题目类型", "题型名称", "type"}
_OPTION_KEYS = {"选项", "选项内容", "备选答案", "备选项", "options", "option"}

_LETTER_COL = re.compile(r"^\s*(?:选项|option|opt)?\s*[_\-]?\s*([A-Ha-h]|[1-8])\s*$", re.I)
_OPT_SPLIT = re.compile(r"\s*[|｜\n\r]\s*|\s*;\s*|\s*；\s*")


class TableParser(BaseParser):
    """表格题库解析器。"""

    name = "table"

    @staticmethod
    def supports(path: Path) -> bool:
        return Path(path).suffix.lower() in (".csv", ".tsv", ".xlsx", ".xls")

    def parse(self, text: str, source: Optional[Path] = None) -> ParsedDocument:
        rows = parse_delimited(text)
        return self.parse_rows(rows, parser_name=self.name)

    @staticmethod
    def parse_rows(rows: Sequence[Sequence[str]], parser_name: str = "table") -> ParsedDocument:
        doc = ParsedDocument(parser=parser_name)
        rows = [list(r) for r in rows if any((c or "").strip() for c in r)]
        if not rows:
            doc.warnings.append("表格为空。")
            return doc

        mapping = _detect_mapping(rows[0])
        start = 1 if mapping["has_header"] else 0
        if not mapping["has_header"]:
            mapping = _positional_mapping(rows[0])
            doc.warnings.append("未识别到表头，按位置推断列含义（题干, 选项, ..., 答案）。")
        if mapping["stem_col"] is None:
            doc.warnings.append("表格中未找到题干列，解析失败。")
            return doc

        current_chapter = 1
        for row in rows[start:]:
            row = _pad(row, len(rows[0]))
            rq = _row_to_question(row, mapping, current_chapter)
            if rq is None:
                # 可能是章节小标题行
                chapter = _section_chapter(row, mapping)
                if chapter is not None:
                    current_chapter = chapter
                continue
            doc.questions.append(rq)
        return doc


def parse_delimited(text: str) -> List[List[str]]:
    """解析 CSV/TSV 文本为二维列表。"""
    text = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    if not text.strip():
        return []
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    return [row for row in reader]


def _detect_mapping(header: Sequence[str]) -> Dict:
    mapping = {
        "has_header": False,
        "stem_col": None,
        "answer_col": None,
        "chapter_col": None,
        "type_col": None,
        "option_cols": {},
        "options_col": None,
    }
    for idx, raw in enumerate(header):
        cell = (raw or "").strip()
        if not cell:
            continue
        key = cell.lower().replace(" ", "")
        if key in _STEM_KEYS:
            mapping["has_header"] = True
            mapping["stem_col"] = idx
        elif key in _ANSWER_KEYS:
            mapping["has_header"] = True
            mapping["answer_col"] = idx
        elif key in _CHAPTER_KEYS:
            mapping["has_header"] = True
            mapping["chapter_col"] = idx
        elif key in _TYPE_KEYS:
            mapping["has_header"] = True
            mapping["type_col"] = idx
        elif key in _OPTION_KEYS:
            mapping["has_header"] = True
            mapping["options_col"] = idx
        else:
            m = _LETTER_COL.match(cell)
            if m:
                letter = m.group(1).upper()
                if letter.isdigit():
                    letter = "ABCDEFGH"[int(letter) - 1]
                mapping["has_header"] = True
                mapping["option_cols"][letter] = idx
    return mapping


def _positional_mapping(first_row: Sequence[str]) -> Dict:
    """无表头时按列数推断：题干 | 选项A..D | 答案 [| 章节]。"""
    n = len(first_row)
    mapping = {
        "has_header": False,
        "stem_col": 0,
        "answer_col": n - 1,
        "chapter_col": n - 2 if n >= 7 else None,
        "type_col": None,
        "option_cols": {},
        "options_col": None,
    }
    if n >= 3:
        for i in range(1, mapping["answer_col"]):
            mapping["option_cols"]["ABCDEFGH"[i - 1]] = i
    return mapping


def _row_to_question(row: List[str], mapping: Dict, default_chapter: int) -> Optional[RawQuestion]:
    stem_col = mapping["stem_col"]
    if stem_col is None or stem_col >= len(row):
        return None
    stem = (row[stem_col] or "").strip()
    if not stem:
        return None

    options: List[str] = []
    if mapping["option_cols"]:
        for letter in sorted(mapping["option_cols"]):
            col = mapping["option_cols"][letter]
            if col < len(row) and (row[col] or "").strip():
                options.append(f"{letter}.{(row[col] or '').strip()}")
    elif mapping["options_col"] is not None and mapping["options_col"] < len(row):
        options = split_options_cell(row[mapping["options_col"]])

    answer = None
    if mapping["answer_col"] is not None and mapping["answer_col"] < len(row):
        answer = (row[mapping["answer_col"]] or "").strip()

    chapter = default_chapter
    if mapping["chapter_col"] is not None and mapping["chapter_col"] < len(row):
        chapter = (row[mapping["chapter_col"]] or "").strip() or default_chapter

    qtype = None
    if mapping["type_col"] is not None and mapping["type_col"] < len(row):
        qtype = (row[mapping["type_col"]] or "").strip() or None

    if not options and not answer:
        return None

    return RawQuestion(stem=stem, options=options, answer=answer,
                       chapter=chapter, qtype=qtype)


def split_options_cell(cell: str) -> List[str]:
    """把「A.xx B.xx C.xx」或「xx|yy|zz」形式的合并选项拆开。"""
    cell = (cell or "").strip()
    if not cell:
        return []
    matches = list(_OPTION_INLINE.finditer(cell))
    if len(matches) >= 2:
        parts: List[str] = []
        for i, m in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(cell)
            parts.append(cell[m.start():end].strip())
        return parts
    pieces = [p.strip() for p in _OPT_SPLIT.split(cell) if p.strip()]
    if len(pieces) >= 2:
        from ..schema import LETTERS

        return [f"{LETTERS[i]}.{p}" for i, p in enumerate(pieces) if i < len(LETTERS)]
    return []


def _section_chapter(row: List[str], mapping: Dict) -> Optional[int]:
    """检测「整行只有一个单元格」的章节标题行。"""
    filled = [(i, (c or "").strip()) for i, c in enumerate(row) if (c or "").strip()]
    if len(filled) != 1:
        return None
    text = filled[0][1]
    m = re.search(r"第?\s*([0-9一二三四五六七八九十]+)\s*[章节篇]", text)
    if not m:
        return None
    from .text_parser import _cn_to_int

    return _cn_to_int(m.group(1))


def _pad(row: List[str], size: int) -> List[str]:
    return list(row) + [""] * max(0, size - len(row))
