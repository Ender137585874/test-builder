# -*- coding: utf-8 -*-
"""解析器注册与分发：按文件类型选择合适的解析通道。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

from .base import BaseParser, ParsedDocument, RawQuestion, SUPPORTED_SUFFIXES
from .dl_parser import HybridParser, LLMConfig, LLMParser
from .json_parser import JsonParser
from .markdown_parser import MarkdownParser
from .table_parser import TableParser, parse_delimited
from .text_parser import TextParser
from .xlsx_reader import read_xlsx

_TEXT_SUFFIXES = (".txt", ".text")
_MARKDOWN_SUFFIXES = (".md", ".markdown")
_TABLE_SUFFIXES = (".csv", ".tsv")
_EXCEL_SUFFIXES = (".xlsx", ".xls")
_JSON_SUFFIXES = (".json",)


def select_parser(path: Union[str, Path], config: Optional[LLMConfig] = None) -> BaseParser:
    """根据文件扩展名返回解析器实例。"""
    suffix = Path(path).suffix.lower()
    config = config or LLMConfig.from_env()
    if suffix in _TEXT_SUFFIXES:
        return HybridParser(config, TextParser())
    if suffix in _MARKDOWN_SUFFIXES:
        return HybridParser(config, MarkdownParser())
    if suffix in _TABLE_SUFFIXES:
        return TableParser()
    if suffix in _EXCEL_SUFFIXES:
        return TableParser()
    if suffix in _JSON_SUFFIXES:
        return JsonParser()
    return HybridParser(config, TextParser())


def parse_path(path: Union[str, Path], config: Optional[LLMConfig] = None) -> ParsedDocument:
    """解析单个题库文件（自动识别格式）。"""
    path = Path(path)
    suffix = path.suffix.lower()
    config = config or LLMConfig.from_env()

    if suffix in _EXCEL_SUFFIXES:
        try:
            rows = read_xlsx(path)
        except Exception as exc:  # noqa: BLE001 - 向上返回友好错误
            raise RuntimeError(f"读取 Excel 失败：{path} -> {exc}") from exc
        return TableParser.parse_rows(rows, parser_name="excel")

    if suffix in _JSON_SUFFIXES:
        try:
            return JsonParser().parse_file(path)
        except ValueError as exc:
            raise RuntimeError(f"读取 JSON 失败：{path} -> {exc}") from exc

    return select_parser(path, config).parse_file(path)


__all__ = [
    "BaseParser",
    "ParsedDocument",
    "RawQuestion",
    "SUPPORTED_SUFFIXES",
    "TextParser",
    "MarkdownParser",
    "TableParser",
    "JsonParser",
    "LLMParser",
    "HybridParser",
    "LLMConfig",
    "parse_delimited",
    "read_xlsx",
    "select_parser",
    "parse_path",
]
