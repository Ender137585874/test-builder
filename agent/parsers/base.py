# -*- coding: utf-8 -*-
"""解析器基础设施：松散题目模型与解析器接口。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional, Sequence


@dataclass
class RawQuestion:
    """解析器产出的「未归一化」题目，字段允许缺失/脏数据。"""

    stem: str
    options: List[str] = field(default_factory=list)
    answer: Any = None
    chapter: Any = 1
    qtype: Optional[str] = None


@dataclass
class ParsedDocument:
    """一次解析的结果。"""

    questions: List[RawQuestion] = field(default_factory=list)
    parser: str = ""
    warnings: List[str] = field(default_factory=list)

    def extend(self, other: "ParsedDocument") -> None:
        self.questions.extend(other.questions)
        self.warnings.extend(other.warnings)


class BaseParser(ABC):
    """所有解析器的统一接口。"""

    name: str = "base"

    @abstractmethod
    def parse(self, text: str, source: Optional[Path] = None) -> ParsedDocument:
        """解析纯文本内容。"""

    def parse_file(self, path: Path) -> ParsedDocument:
        path = Path(path)
        text = path.read_text(encoding=self.encoding())
        doc = self.parse(text, source=path)
        doc.parser = doc.parser or self.name
        return doc

    def encoding(self) -> str:
        return "utf-8"

    @staticmethod
    def supports(path: Path) -> bool:
        return False


SUPPORTED_SUFFIXES: Sequence[str] = (".txt", ".text", ".md", ".markdown",
                                     ".csv", ".tsv", ".xlsx", ".xls", ".json")
