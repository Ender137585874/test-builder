# -*- coding: utf-8 -*-
"""主流程编排：解析 -> 归一化 -> 去重 -> 校验 -> 生成 HTML。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Union

from .builder import build_html, write_html
from .normalize import build_question
from .parsers import LLMConfig, parse_path
from .parsers.base import SUPPORTED_SUFFIXES
from .parsers.dl_parser import _stem_key
from .schema import Question, QuizDocument, QuizMeta, ValidationError


@dataclass
class BuildOptions:
    """一次构建的可配置项。"""

    inputs: List[Path]
    output: Path
    meta: QuizMeta = field(default_factory=QuizMeta)
    llm: LLMConfig = field(default_factory=LLMConfig)
    template: Optional[Path] = None
    dedupe: bool = True
    strict: bool = False

    @classmethod
    def create(cls, inputs: Sequence[Union[str, Path]], output: Union[str, Path],
               **kwargs) -> "BuildOptions":
        inputs = [Path(p) for p in inputs]
        return cls(inputs=inputs, output=Path(output), **kwargs)


@dataclass
class BuildReport:
    """构建结果摘要，便于 CLI 展示与测试断言。"""

    total: int = 0
    by_type: Dict[str, int] = field(default_factory=dict)
    by_chapter: Dict[int, int] = field(default_factory=dict)
    sources: List[str] = field(default_factory=list)
    parsers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    output: Optional[Path] = None

    def summary(self) -> str:
        lines = [
            f"共 {self.total} 道题",
            "题型分布：" + ", ".join(f"{k}={v}" for k, v in self.by_type.items() if v),
            "章节分布：" + ", ".join(f"第{k}章={v}" for k, v in sorted(self.by_chapter.items())),
            f"解析通道：{', '.join(self.parsers) or '-'}",
            f"输出文件：{self.output}",
        ]
        if self.warnings:
            lines.append(f"警告 {len(self.warnings)} 条：")
            lines.extend(f"  - {w}" for w in self.warnings)
        return "\n".join(lines)


def collect_inputs(targets: Sequence[Union[str, Path]]) -> List[Path]:
    """把文件/目录展开为可解析的题库文件列表。"""
    files: List[Path] = []
    for target in targets:
        path = Path(target)
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file() and child.suffix.lower() in SUPPORTED_SUFFIXES:
                    files.append(child)
        elif path.is_file():
            files.append(path)
        else:
            raise FileNotFoundError(f"输入路径不存在：{path}")
    if not files:
        raise FileNotFoundError("未在给定路径下找到任何题库文件")
    return files


def run(options: BuildOptions) -> BuildReport:
    """执行完整构建流程。"""
    report = BuildReport()
    doc = QuizDocument(meta=options.meta)

    seen: Dict[str, int] = {}
    for path in options.inputs:
        parsed = parse_path(path, options.llm)
        report.sources.append(str(path))
        if parsed.parser:
            report.parsers.append(parsed.parser)
        for w in parsed.warnings:
            report.warnings.append(f"[{path.name}] {w}")

        for raw in parsed.questions:
            try:
                q = build_question(raw.stem, raw.options, raw.answer,
                                   chapter=raw.chapter, qtype=raw.qtype)
            except ValidationError as exc:
                msg = f"[{path.name}] 跳过题目（{exc}）：{str(raw.stem)[:40]}"
                if options.strict:
                    raise ValidationError(msg) from exc
                report.warnings.append(msg)
                continue
            except Exception as exc:  # noqa: BLE001 - 单题失败不应中断整体
                msg = f"[{path.name}] 题目处理异常（{exc}）：{str(raw.stem)[:40]}"
                if options.strict:
                    raise
                report.warnings.append(msg)
                continue

            if options.dedupe:
                key = _stem_key(q.question)
                if key in seen:
                    report.warnings.append(f"[{path.name}] 去重移除重复题：{q.question[:30]}")
                    continue
                seen[key] = len(doc.questions)

            doc.questions.append(q)

    if not doc.questions:
        raise ValidationError("没有解析出任何有效题目，请检查题库格式或开启调试日志")

    doc.validate()
    if not doc.meta.chapters:
        doc.meta.chapters = doc.auto_chapters()

    html = build_html(doc, template=_load_optional_template(options.template))
    report.output = write_html(html, options.output)

    report.total = len(doc.questions)
    report.by_type = doc.type_stats()
    report.by_chapter = doc.chapter_stats()
    return report


def _load_optional_template(path: Optional[Path]) -> Optional[str]:
    if path is None:
        return None
    return Path(path).read_text(encoding="utf-8")


@dataclass
class FileValidation:
    """单个题库文件的导入校验结果（供 GUI / CLI 展示）。"""

    path: Path
    parser: str = ""
    total: int = 0          # 解析出的原始题目数
    valid: int = 0          # 通过结构校验的题目数
    invalid: int = 0        # 校验失败的题目数
    questions: List[Question] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)     # 致命错误（文件级）
    warnings: List[str] = field(default_factory=list)   # 单题跳过/降级等

    @property
    def ok(self) -> bool:
        return not self.errors and self.valid > 0

    def describe(self) -> str:
        if self.errors:
            return "导入失败"
        if self.valid == 0:
            return "未解析出有效题目"
        if self.invalid:
            return f"{self.valid} 题有效 / {self.invalid} 题异常"
        return f"{self.valid} 题全部有效"


def validate_file(path: Union[str, Path], llm: Optional[LLMConfig] = None) -> FileValidation:
    """解析单个题库文件并逐题做结构校验，返回结构化结果。"""
    path = Path(path)
    result = FileValidation(path=path)
    try:
        parsed = parse_path(path, llm or LLMConfig.from_env(mode="rule"))
    except Exception as exc:  # noqa: BLE001 - 文件级错误统一收口
        result.errors.append(str(exc))
        return result

    result.parser = parsed.parser
    result.total = len(parsed.questions)
    result.warnings.extend(parsed.warnings)

    for idx, raw in enumerate(parsed.questions, start=1):
        try:
            q = build_question(raw.stem, raw.options, raw.answer,
                               chapter=raw.chapter, qtype=raw.qtype)
            q.validate()
        except ValidationError as exc:
            result.invalid += 1
            result.warnings.append(f"第 {idx} 题校验未通过：{exc}")
            continue
        except Exception as exc:  # noqa: BLE001 - 单题异常不影响其余题目
            result.invalid += 1
            result.warnings.append(f"第 {idx} 题处理异常：{exc}")
            continue
        result.valid += 1
        result.questions.append(q)
    return result


def validate_files(targets: Sequence[Union[str, Path]],
                   llm: Optional[LLMConfig] = None) -> List[FileValidation]:
    """批量校验题库文件（自动展开目录）。"""
    results: List[FileValidation] = []
    for target in targets:
        path = Path(target)
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file() and child.suffix.lower() in SUPPORTED_SUFFIXES:
                    results.append(validate_file(child, llm))
        elif path.is_file():
            results.append(validate_file(path, llm))
        else:
            broken = FileValidation(path=path)
            broken.errors.append(f"输入路径不存在：{path}")
            results.append(broken)
    return results
