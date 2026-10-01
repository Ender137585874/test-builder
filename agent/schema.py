# -*- coding: utf-8 -*-
"""标准题库数据结构定义与校验。

标准题目 JSON 结构（与参考项目完全一致）::

    {
        "id": 1,
        "chapter": 1,
        "type": "single" | "multi" | "judge",
        "question": "题干文本",
        "options": ["A.选项一", "B.选项二", ...],
        "answer": "B"            # 单选 / 判断：字符串
                  ["A", "B"]     # 多选：字符串数组
    }
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
QUESTION_TYPES = ("single", "multi", "judge")
TYPE_LABELS = {"single": "单选题", "multi": "多选题", "judge": "判断题"}
DEFAULT_JUDGE_OPTIONS = ["A.正确", "B.错误"]
DEFAULT_JUDGE_ANSWERS = {"A": ["正确", "对", "√", "V", "T", "true", "是", "1"],
                         "B": ["错误", "错", "×", "X", "F", "false", "否", "0"]}


class ValidationError(Exception):
    """题目数据不符合标准结构时抛出。"""


@dataclass
class Question:
    """一道标准题目。"""

    question: str
    options: List[str]
    answer: Union[str, List[str]]
    type: str = "single"
    chapter: int = 1
    id: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """按参考项目的字段顺序导出为标准 JSON 对象。"""
        return {
            "id": self.id,
            "chapter": self.chapter,
            "type": self.type,
            "question": self.question,
            "options": list(self.options),
            "answer": self.answer,
        }

    def validate(self) -> None:
        """校验字段完整性与取值合法性。"""
        if self.type not in QUESTION_TYPES:
            raise ValidationError(f"未知题型 type={self.type!r}")
        if not str(self.question).strip():
            raise ValidationError("题干 question 不能为空")
        if not isinstance(self.options, list) or len(self.options) < 2:
            raise ValidationError(f"选项 options 至少需要 2 项，当前={self.options!r}")

        letters = []
        for idx, opt in enumerate(self.options):
            if not isinstance(opt, str) or not opt.strip():
                raise ValidationError(f"第 {idx + 1} 个选项为空")
            expected = LETTERS[idx]
            if not opt.startswith(expected):
                raise ValidationError(
                    f"第 {idx + 1} 个选项应以 {expected} 开头，当前={opt!r}"
                )
            letters.append(opt[0])

        if self.type == "multi":
            if not isinstance(self.answer, list) or not self.answer:
                raise ValidationError(f"多选题 answer 应为非空数组，当前={self.answer!r}")
            if len(set(self.answer)) != len(self.answer):
                raise ValidationError(f"多选题 answer 存在重复项：{self.answer!r}")
            for a in self.answer:
                if a not in letters:
                    raise ValidationError(f"answer {a!r} 不在选项范围内 {letters}")
        else:
            if not isinstance(self.answer, str) or len(self.answer) != 1:
                raise ValidationError(f"{self.type} 题 answer 应为单个字母，当前={self.answer!r}")
            if self.answer not in letters:
                raise ValidationError(f"answer {self.answer!r} 不在选项范围内 {letters}")


@dataclass
class QuizMeta:
    """刷题系统的展示与配置元信息。"""

    title: str = "在线自测系统"
    subtitle: str = "自测系统"
    announcement: List[str] = field(default_factory=list)
    update_url: str = "#"
    chapters: Dict[int, str] = field(default_factory=dict)


@dataclass
class QuizDocument:
    """一份完整的刷题系统答卷：元信息 + 题目列表。"""

    meta: QuizMeta
    questions: List[Question] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def validate(self) -> None:
        """批量校验并回填 id。"""
        for idx, q in enumerate(self.questions, start=1):
            q.id = idx
            q.validate()

    def type_stats(self) -> Dict[str, int]:
        stats = {t: 0 for t in QUESTION_TYPES}
        for q in self.questions:
            stats[q.type] = stats.get(q.type, 0) + 1
        return stats

    def chapter_stats(self) -> Dict[int, int]:
        stats: Dict[int, int] = {}
        for q in self.questions:
            stats[q.chapter] = stats.get(q.chapter, 0) + 1
        return stats

    def auto_chapters(self) -> Dict[int, str]:
        """未显式提供章节名时，依据题目自动生成默认章节名。"""
        names = {c: f"第{c}章" for c in sorted(self.chapter_stats())}
        return names
