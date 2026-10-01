# -*- coding: utf-8 -*-
"""JSON 题库解析器：读取标准/宽松结构的 JSON 题库。

支持的顶层结构：
1. 题目对象数组：``[{"question": "...", "options": [...], "answer": "B"}, ...]``
2. 带 questions 字段的对象：``{"title": "...", "questions": [...]}``
3. 单个题目对象：``{"question": "...", ...}``

单题的字段名允许多种别名（中英文均可），选项支持数组、对象与合并字符串三种写法。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .base import BaseParser, ParsedDocument, RawQuestion
from .table_parser import split_options_cell

_STEM_KEYS = ("question", "stem", "title", "content", "题干", "题目", "问题", "试题")
_ANSWER_KEYS = ("answer", "answers", "key", "correct", "correctAnswer",
                "答案", "正确答案", "参考答案", "标准答案")
_OPTION_KEYS = ("options", "option", "choices", "choice", "选项", "备选项", "备选答案")
_CHAPTER_KEYS = ("chapter", "chapterId", "section", "章节", "章", "章节名")
_TYPE_KEYS = ("type", "qtype", "questionType", "题型", "类型", "题目类型")
_QUESTIONS_KEYS = ("questions", "items", "data", "list", "题目列表", "题库")


class JsonParser(BaseParser):
    """JSON 题库解析器。"""

    name = "json"

    @staticmethod
    def supports(path: Path) -> bool:
        return Path(path).suffix.lower() == ".json"

    def encoding(self) -> str:
        # 兼容带 BOM 的 UTF-8 JSON
        return "utf-8-sig"

    def parse(self, text: str, source: Optional[Path] = None) -> ParsedDocument:
        doc = ParsedDocument(parser=self.name)
        if not text.strip():
            doc.warnings.append("JSON 文件为空。")
            return doc
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON 语法错误（第 {exc.lineno} 行第 {exc.colno} 列）：{exc.msg}") from exc

        items = _extract_items(payload)
        if items is None:
            doc.warnings.append("未在 JSON 中找到题目数组（支持数组或含 questions 字段的对象）。")
            return doc

        for idx, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                doc.warnings.append(f"第 {idx} 条记录不是对象，已跳过。")
                continue
            rq = _item_to_question(item)
            if rq is None:
                doc.warnings.append(f"第 {idx} 条记录缺少题干，已跳过。")
                continue
            doc.questions.append(rq)
        return doc


def _extract_items(payload: Any) -> Optional[List[Any]]:
    """从任意顶层结构中取出题目数组。"""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in _QUESTIONS_KEYS:
            value = payload.get(key)
            if isinstance(value, list):
                return value
        # 单题对象
        if any(k in payload for k in _STEM_KEYS):
            return [payload]
    return None


def _pick(item: Dict[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        if key in item and item[key] not in (None, ""):
            return item[key]
        # 兼容大小写不同的键名
        for actual in item:
            if str(actual).lower() == key.lower() and item[actual] not in (None, ""):
                return item[actual]
    return None


def _item_to_question(item: Dict[str, Any]) -> Optional[RawQuestion]:
    stem = _pick(item, _STEM_KEYS)
    if stem is None or not str(stem).strip():
        return None

    options = _coerce_options(_pick(item, _OPTION_KEYS))
    answer = _pick(item, _ANSWER_KEYS)
    chapter = _pick(item, _CHAPTER_KEYS)
    qtype = _pick(item, _TYPE_KEYS)

    return RawQuestion(
        stem=str(stem),
        options=options,
        answer=answer,
        chapter=chapter if chapter is not None else 1,
        qtype=str(qtype) if qtype is not None else None,
    )


def _coerce_options(raw: Any) -> List[str]:
    """把各种选项写法统一为字符串列表。"""
    if raw is None:
        return []
    if isinstance(raw, dict):
        return [f"{key}.{raw[key]}" for key in sorted(raw)]
    if isinstance(raw, str):
        return split_options_cell(raw)
    if isinstance(raw, (list, tuple)):
        result: List[str] = []
        for value in raw:
            if isinstance(value, dict):
                # 形如 {"key": "A", "value": "内容"}
                key = value.get("key") or value.get("letter") or value.get("label")
                text = value.get("value") or value.get("text") or value.get("content") or ""
                result.append(f"{key}.{text}" if key else str(text))
            elif value is not None:
                result.append(str(value))
        return result
    return []
