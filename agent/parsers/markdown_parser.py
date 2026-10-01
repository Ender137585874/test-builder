# -*- coding: utf-8 -*-
"""Markdown 题库解析器。

支持两种常见写法：
1) Markdown 表格（| 题干 | 选项 | 答案 |）
2) 普通 Markdown 列表 / 段落，去除标记后交给文本解析器
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

from .base import BaseParser, ParsedDocument
from .table_parser import TableParser
from .text_parser import TextParser

_TABLE_BLOCK = re.compile(
    r"((?:^[ \t]*\|.*\|[ \t]*\n)+)",
    re.M,
)
_SEPARATOR_ROW = re.compile(r"^[ \t]*\|[\s:|-]+\|[ \t]*$")
_HEADING = re.compile(r"^[ \t]*#{1,6}[ \t]*(.+?)[ \t]*#*[ \t]*$", re.M)
_LIST_MARK = re.compile(r"^[ \t]*[-+][ \t]+", re.M)
_BOLD = re.compile(r"(\*\*|__)(.*?)\1", re.S)
_ITALIC = re.compile(r"\*([^*\n]+)\*")
_CODE = re.compile(r"`([^`]*)`")
_QUOTE = re.compile(r"^[ \t]*>[ \t]?", re.M)


class MarkdownParser(BaseParser):
    """Markdown 题库解析器。"""

    name = "markdown"

    @staticmethod
    def supports(path: Path) -> bool:
        return Path(path).suffix.lower() in (".md", ".markdown")

    def parse(self, text: str, source: Optional[Path] = None) -> ParsedDocument:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        tables = _extract_tables(text)
        doc = ParsedDocument(parser=self.name)
        if tables:
            all_rows: List[List[str]] = []
            for rows in tables:
                all_rows.extend(rows)
            parsed = TableParser.parse_rows(all_rows, parser_name=self.name)
            doc.questions.extend(parsed.questions)
            doc.warnings.extend(parsed.warnings)

            remainder = _TABLE_BLOCK.sub("\n", text)
            remainder = _strip_markdown(remainder)
            if len(remainder.strip()) > 200:
                doc.warnings.append("Markdown 中检测到表格外的文本内容，已忽略。")
            return doc

        plain = _strip_markdown(text)
        parsed = TextParser().parse(plain)
        doc.questions.extend(parsed.questions)
        doc.warnings.extend(parsed.warnings)
        return doc


def _extract_tables(text: str) -> List[List[List[str]]]:
    """抽取所有 Markdown 表格，返回 [[row, ...], ...]。"""
    tables: List[List[List[str]]] = []
    for block in _TABLE_BLOCK.findall(text):
        lines = [l.strip() for l in block.strip().split("\n") if l.strip()]
        rows: List[List[str]] = []
        for line in lines:
            if _SEPARATOR_ROW.match(line):
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            rows.append(cells)
        if len(rows) >= 2:
            tables.append(rows)
    return tables


def _strip_markdown(text: str) -> str:
    """去除常见 Markdown 标记，保留纯文本。"""
    s = _HEADING.sub(r"\1", text)
    s = _BOLD.sub(r"\2", s)
    s = _CODE.sub(r"\1", s)
    s = _QUOTE.sub("", s)
    s = _ITALIC.sub(r"\1", s)
    # 只去掉列表符号，保留正文；题号本身由文本解析器处理
    s = _LIST_MARK.sub("", s)
    return s
