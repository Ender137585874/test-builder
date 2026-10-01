# -*- coding: utf-8 -*-
"""深度学习语义解析器（Transformer / LLM）。

说明
----
本模块的「深度学习」能力来自预训练的 Transformer 大语言模型（LLM）：
通过 OpenAI 兼容的 Chat Completions 接口，让模型把任意非结构化的原始题库
直接「翻译」成标准题目 JSON。相比正则规则，模型能正确处理排版混乱、
中英混排、答案与题干粘连、选项换行等长尾情况。

为避免过度承诺：本模块不包含从零训练模型的代码（那需要标注数据与 GPU），
而是通过 API 调用现成的 Transformer 模型 —— 这也是工业界落地的主流做法。
当模型不可用（未配置 API Key / 网络异常）时，自动降级为本地规则解析器，
保证 Agent 在任何环境下都能产出结果。
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import BaseParser, ParsedDocument, RawQuestion
from .text_parser import TextParser

_SYSTEM_PROMPT = """你是一个题库结构化专家。用户的输入是杂乱的中文/英文题目原始文本。
请把它转换成一个 JSON 数组，数组每个元素表示一道题，字段严格如下：
{
  "question": "题干（不含题号，不含答案）",
  "options": ["A.选项内容", "B.选项内容", ...],
  "answer": "B" 或 ["A","C"],
  "type": "single" | "multi" | "judge",
  "chapter": 1
}
规则：
1. 选项必须保留大写字母前缀与英文句点，如 "A.中国"；按 A、B、C、D 顺序排列。
2. 单选题 answer 为单个字母字符串；多选题 answer 为字母数组；判断题 answer 为 "A"(正确) 或 "B"(错误)。
3. 判断题若原题没有选项，options 固定为 ["A.正确", "B.错误"]。
4. 题干中不要残留 "（答案：A）" 之类的文字。
5. chapter 从原文的章节标题推断，推断不出时填 1。
6. 只输出 JSON 数组本身，不要输出任何解释、Markdown 代码块或多余文字。"""

_USER_TEMPLATE = "请把下面的题目原文转换为 JSON 数组：\n\n---\n{content}\n---"


@dataclass
class LLMConfig:
    """LLM 接入配置。"""

    enabled: bool = True
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    model: str = "gpt-4o-mini"
    temperature: float = 0.0
    timeout: int = 90
    max_chars: int = 6000
    mode: str = "hybrid"  # hybrid | llm | rule

    @classmethod
    def from_env(cls, **overrides) -> "LLMConfig":
        cfg = cls(
            base_url=os.getenv("QUIZ_LLM_BASE_URL", cls.base_url),
            api_key=os.getenv("QUIZ_LLM_API_KEY", "") or os.getenv("OPENAI_API_KEY", ""),
            model=os.getenv("QUIZ_LLM_MODEL", cls.model),
            mode=os.getenv("QUIZ_LLM_MODE", cls.mode),
        )
        for key, value in overrides.items():
            if value is not None and hasattr(cfg, key):
                setattr(cfg, key, value)
        return cfg

    @property
    def usable(self) -> bool:
        return bool(self.enabled and self.api_key and self.mode != "rule")


class LLMError(RuntimeError):
    pass


class LLMParser(BaseParser):
    """基于 Transformer 大模型的语义解析器。"""

    name = "llm"

    def __init__(self, config: LLMConfig):
        self.config = config

    def parse(self, text: str, source: Optional[Path] = None) -> ParsedDocument:
        doc = ParsedDocument(parser=self.name)
        chunks = _chunk_text(text, self.config.max_chars)
        for i, chunk in enumerate(chunks):
            try:
                raw = self._complete(chunk)
                questions = _parse_llm_json(raw)
            except LLMError as exc:
                doc.warnings.append(f"第 {i + 1} 段 LLM 解析失败：{exc}")
                continue
            for item in questions:
                rq = _to_raw_question(item)
                if rq is not None:
                    doc.questions.append(rq)
        return doc

    def _complete(self, content: str) -> str:
        url = self.config.base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": self.config.model,
            "temperature": self.config.temperature,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _USER_TEMPLATE.format(content=content)},
            ],
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.config.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "ignore")[:300]
            raise LLMError(f"HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise LLMError(f"网络错误: {exc}") from exc

        try:
            return body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"响应结构异常: {str(body)[:300]}") from exc


class HybridParser(BaseParser):
    """混合解析器：LLM 语义解析 + 规则解析双通道。

    - 规则通道保证「结构化文本一定解析得出来」；
    - LLM 通道负责「非结构化 / 脏数据」的召回；
    - 两者按题干归一化 key 去重合并，并保留规则通道的原始顺序。
    """

    name = "hybrid"

    def __init__(self, config: Optional[LLMConfig] = None,
                 rule_parser: Optional[BaseParser] = None):
        self.config = config or LLMConfig.from_env()
        self._rule = rule_parser or TextParser()
        self._llm = LLMParser(self.config)

    def parse(self, text: str, source: Optional[Path] = None) -> ParsedDocument:
        rule_doc = self._rule.parse(text, source)
        doc = ParsedDocument(parser=self.name)
        doc.questions.extend(rule_doc.questions)
        doc.warnings.extend(rule_doc.warnings)

        if not self.config.usable:
            reason = "已关闭" if not self.config.enabled or self.config.mode == "rule" else "未配置 API Key"
            doc.warnings.append(f"LLM 通道{reason}，仅使用规则解析（降级模式）。")
            return doc

        try:
            llm_doc = self._llm.parse(text, source)
        except LLMError as exc:  # pragma: no cover - 网络异常保护
            doc.warnings.append(f"LLM 通道异常，已降级为规则解析：{exc}")
            return doc

        doc.warnings.extend(llm_doc.warnings)
        rule_keys = {_stem_key(q.stem) for q in rule_doc.questions if q.stem}
        added = 0
        for rq in llm_doc.questions:
            key = _stem_key(rq.stem)
            if not key or key in rule_keys:
                continue
            rule_keys.add(key)
            doc.questions.append(rq)
            added += 1

        doc.warnings.append(
            f"混合解析：规则命中 {len(rule_doc.questions)} 题，LLM 补充 {added} 题。"
        )
        return doc


def _stem_key(stem: str) -> str:
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]", "", stem or "")[:120]


def _chunk_text(text: str, max_chars: int) -> List[str]:
    """按空行/题号边界把长文本切成不超过 max_chars 的片段。"""
    text = text.strip()
    if len(text) <= max_chars:
        return [text] if text else []
    blocks = re.split(r"\n\s*\n", text)
    chunks: List[str] = []
    current: List[str] = []
    size = 0
    for block in blocks:
        if size and size + len(block) > max_chars:
            chunks.append("\n\n".join(current))
            current, size = [], 0
        current.append(block)
        size += len(block) + 2
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def _parse_llm_json(raw: str) -> List[Dict[str, Any]]:
    if not raw or not raw.strip():
        raise LLMError("模型返回空内容")
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1:
        raise LLMError(f"未找到 JSON 数组：{text[:200]!r}")
    try:
        parsed = json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        raise LLMError(f"JSON 解析失败：{exc}") from exc
    if isinstance(parsed, dict):
        parsed = [parsed]
    if not isinstance(parsed, list):
        raise LLMError("JSON 顶层不是数组")
    return [item for item in parsed if isinstance(item, dict)]


def _to_raw_question(item: Dict[str, Any]) -> Optional[RawQuestion]:
    stem = item.get("question") or item.get("stem") or item.get("题干")
    if not stem:
        return None
    options = item.get("options") or item.get("选项") or []
    if isinstance(options, str):
        options = [options]
    return RawQuestion(
        stem=str(stem),
        options=[str(o) for o in options],
        answer=item.get("answer", item.get("答案")),
        chapter=item.get("chapter", 1),
        qtype=item.get("type") or item.get("题型"),
    )
