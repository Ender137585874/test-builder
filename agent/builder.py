# -*- coding: utf-8 -*-
"""HTML 构建器：把标准题目数据嵌入参考项目的模板，产出刷题系统。

模板占位符：
    {{TITLE}}            标题（<title> 与 <h1>）
    {{SUBTITLE}}         副标题
    {{CHAPTER_OPTIONS}}  章节下拉框 <option> 列表
    {{ANNOUNCEMENT}}     公告正文
    {{UPDATE_URL}}       "获取最新版" 跳转地址
    {{QUESTIONS_JSON}}   题库 JSON（最后注入，避免题干内的占位符被二次替换）
"""

from __future__ import annotations

import html as _html
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Union

from .schema import QuizDocument


def _resolve_template_path() -> Path:
    """定位内置模板；兼容 PyInstaller 打包后的临时解包目录。"""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass) / "agent" / "templates" / "quiz_template.html"
    return Path(__file__).resolve().parent / "templates" / "quiz_template.html"


TEMPLATE_PATH = _resolve_template_path()

_OPTION_INDENT = " " * 24
_ANNOUNCE_INDENT = " " * 12

_UNRESOLVED = re.compile(r"\{\{[A-Z_]+\}\}")


def load_template(path: Optional[Union[str, Path]] = None) -> str:
    """读取 HTML 模板文本。"""
    template_path = Path(path) if path else TEMPLATE_PATH
    if not template_path.is_file():
        raise FileNotFoundError(f"找不到 HTML 模板：{template_path}")
    return template_path.read_text(encoding="utf-8")


def render_chapter_options(chapters: Dict[int, str]) -> str:
    """生成章节下拉框的 <option> 列表。"""
    if not chapters:
        chapters = {1: "第一章"}
    lines: List[str] = []
    for key in sorted(chapters):
        label = _html.escape(str(chapters[key]))
        lines.append(f'{_OPTION_INDENT}<option value="{key}">{label}</option>')
    return "\n".join(lines)


def render_announcement(lines: Sequence[str]) -> str:
    """生成公告正文段落。"""
    items = [str(l).strip() for l in (lines or []) if str(l).strip()]
    if not items:
        items = ["欢迎使用本刷题系统，祝学习顺利！"]
    return "\n".join(f"{_ANNOUNCE_INDENT}<p>{_html.escape(l)}</p>" for l in items)


def _dump_questions(questions: Sequence) -> str:
    """把题目对象序列化为 JSON 数组文本。"""
    payload = [q.to_dict() if hasattr(q, "to_dict") else dict(q) for q in questions]
    text = json.dumps(payload, ensure_ascii=False, indent=4)
    # 防御：题干若含 </script> 会提前闭合脚本块
    return text.replace("</script>", "<\\/script>")


def build_html(doc: QuizDocument, template: Optional[str] = None) -> str:
    """把 QuizDocument 渲染为完整的刷题系统 HTML。"""
    tpl = template if template is not None else load_template()
    meta = doc.meta

    chapters = dict(meta.chapters) or doc.auto_chapters()

    tpl = tpl.replace("{{TITLE}}", _html.escape(meta.title or "在线自测系统"))
    tpl = tpl.replace("{{SUBTITLE}}", _html.escape(meta.subtitle or "自测系统"))
    tpl = tpl.replace("{{CHAPTER_OPTIONS}}", render_chapter_options(chapters))
    tpl = tpl.replace("{{ANNOUNCEMENT}}", render_announcement(meta.announcement))
    tpl = tpl.replace("{{UPDATE_URL}}", str(meta.update_url or "#"))

    # 题库 JSON 最后注入：防止题干/选项中的占位符串被再次替换
    tpl = tpl.replace("{{QUESTIONS_JSON}}", _dump_questions(doc.questions))

    leftover = _UNRESOLVED.findall(tpl)
    if leftover:
        raise RuntimeError(f"模板存在未替换的占位符：{sorted(set(leftover))}")
    return tpl


def write_html(content: str, out_path: Union[str, Path]) -> Path:
    """写出 HTML 文件，自动创建父目录。"""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")
    return out_path
