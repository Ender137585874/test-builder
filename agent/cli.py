# -*- coding: utf-8 -*-
"""命令行入口：把原始题库转换为可运行的 HTML 刷题系统。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import __version__
from .parsers import LLMConfig
from .pipeline import BuildOptions, collect_inputs, run
from .schema import QuizMeta


def _load_config(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"找不到配置文件：{path}")
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".json":
        return json.loads(text)
    raise ValueError(f"暂不支持的配置格式：{path.suffix}（请使用 JSON）")


def _build_llm_config(raw: Optional[Dict[str, Any]]) -> LLMConfig:
    raw = raw or {}
    api_key = raw.get("api_key") or ""
    if not api_key:
        env_name = raw.get("api_key_env") or "QUIZ_LLM_API_KEY"
        api_key = os.getenv(env_name, "")
    return LLMConfig.from_env(
        enabled=raw.get("enabled", True),
        base_url=raw.get("base_url"),
        api_key=api_key or None,
        model=raw.get("model"),
        mode=raw.get("mode"),
        temperature=raw.get("temperature"),
        timeout=raw.get("timeout"),
    )


def _build_meta(cfg: Dict[str, Any], args: argparse.Namespace) -> QuizMeta:
    chapters: Dict[int, str] = {}
    for key, value in (cfg.get("chapters") or {}).items():
        try:
            chapters[int(key)] = str(value)
        except (TypeError, ValueError):
            continue

    announcement = cfg.get("announcement") or []
    if isinstance(announcement, str):
        announcement = [announcement]
    if args.announcement:
        announcement = list(args.announcement)

    return QuizMeta(
        title=args.title or cfg.get("title") or "在线自测系统",
        subtitle=args.subtitle or cfg.get("subtitle") or "自测系统@千纸鹤",
        announcement=announcement,
        update_url=args.update_url or cfg.get("update_url") or "#",
        chapters=chapters,
    )


def _resolve_inputs(cfg: Dict[str, Any], args: argparse.Namespace,
                    base: Path) -> List[Path]:
    inputs: List[str] = list(args.input) if args.input else list(cfg.get("input") or [])
    if not inputs:
        raise ValueError("必须通过 --input 或配置文件的 input 字段指定题库来源")
    resolved = []
    for item in inputs:
        p = Path(item)
        resolved.append(p if p.is_absolute() else (base / p))
    return collect_inputs(resolved)


def _cmd_build(args: argparse.Namespace) -> int:
    cfg: Dict[str, Any] = {}
    base = Path.cwd()
    if args.config:
        cfg_path = Path(args.config)
        cfg = _load_config(cfg_path)
        base = cfg_path.resolve().parent

    inputs = _resolve_inputs(cfg, args, base)
    output = args.output or cfg.get("output") or "output/quiz.html"
    output_path = Path(output)
    if not output_path.is_absolute():
        output_path = (base / output_path).resolve() if args.config else Path.cwd() / output_path

    llm_raw = dict(cfg.get("llm") or {})
    if args.no_llm:
        llm_raw["mode"] = "rule"

    options = BuildOptions(
        inputs=inputs,
        output=output_path,
        meta=_build_meta(cfg, args),
        llm=_build_llm_config(llm_raw),
        template=Path(args.template) if args.template else None,
        dedupe=not args.keep_duplicates,
        strict=args.strict,
    )

    print(f"自测生成系统 v{__version__}")
    print(f"输入 {len(inputs)} 个文件，LLM 通道：{'开启' if options.llm.usable else '关闭（规则模式）'}")
    report = run(options)
    print("-" * 48)
    print(report.summary())
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    """只做导入校验：解析题库并逐题做结构校验，不生成 HTML。"""
    from .pipeline import validate_files

    llm = LLMConfig.from_env(mode="rule" if args.no_llm else None)
    results = validate_files([Path(p) for p in args.input], llm)

    print(f"自测生成系统 v{__version__} · 题库导入校验")
    print("-" * 60)
    ok_files = total_valid = total_invalid = 0
    for res in results:
        status = "通过" if res.ok else "失败"
        print(f"[{status}] {res.path}")
        print(f"        解析通道 {res.parser or '-'} | 解析 {res.total} 题 | "
              f"有效 {res.valid} 题 | 异常 {res.invalid} 题 | {res.describe()}")
        for err in res.errors:
            print(f"        ! 错误：{err}")
        for warn in res.warnings:
            print(f"        - 提示：{warn}")
        if res.ok:
            ok_files += 1
        total_valid += res.valid
        total_invalid += res.invalid
    print("-" * 60)
    print(f"文件 {len(results)} 个（通过 {ok_files}） | 有效题目 {total_valid} 题 | "
          f"异常题目 {total_invalid} 题")
    return 0 if ok_files == len(results) and results else 1


def _cmd_parse(args: argparse.Namespace) -> int:
    """只做解析，输出标准 JSON（不生成 HTML）。"""
    from .normalize import build_question
    from .parsers import parse_path
    from .schema import Question, ValidationError

    llm = LLMConfig.from_env(mode="rule" if args.no_llm else None)
    questions = []
    for path in collect_inputs([Path(p) for p in args.input]):
        parsed = parse_path(path, llm)
        for raw in parsed.questions:
            try:
                q: Question = build_question(raw.stem, raw.options, raw.answer,
                                             chapter=raw.chapter, qtype=raw.qtype)
            except ValidationError:
                continue
            questions.append(q.to_dict())
    for idx, item in enumerate(questions, start=1):
        item["id"] = idx
    sys.stdout.write(json.dumps(questions, ensure_ascii=False, indent=4) + "\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="test-builder",
        description="自测生成系统：把原始题库自动转换为 HTML 刷题系统",
    )
    parser.add_argument("--version", action="version", version=f"自测生成系统 {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_build = sub.add_parser("build", help="解析题库并生成 HTML 刷题系统")
    p_build.add_argument("-c", "--config", help="JSON 配置文件路径")
    p_build.add_argument("-i", "--input", nargs="+", help="题库文件或目录（可多个）")
    p_build.add_argument("-o", "--output", help="输出 HTML 路径")
    p_build.add_argument("--title", help="标题（覆盖配置文件）")
    p_build.add_argument("--subtitle", help="副标题")
    p_build.add_argument("--announcement", nargs="+", help="公告内容，每项一段")
    p_build.add_argument("--update-url", dest="update_url", help="获取最新版跳转地址")
    p_build.add_argument("--template", help="自定义 HTML 模板路径")
    p_build.add_argument("--no-llm", action="store_true", help="禁用 LLM，仅用规则解析")
    p_build.add_argument("--keep-duplicates", action="store_true", help="不去重")
    p_build.add_argument("--strict", action="store_true", help="遇到无法解析的题目直接报错")
    p_build.set_defaults(func=_cmd_build)

    p_parse = sub.add_parser("parse", help="仅解析为标准 JSON 并打印")
    p_parse.add_argument("-i", "--input", nargs="+", required=True, help="题库文件或目录")
    p_parse.add_argument("--no-llm", action="store_true", help="禁用 LLM，仅用规则解析")
    p_parse.set_defaults(func=_cmd_parse)

    p_validate = sub.add_parser("validate", help="仅做题库导入校验，不生成 HTML")
    p_validate.add_argument("-i", "--input", nargs="+", required=True, help="题库文件或目录")
    p_validate.add_argument("--no-llm", action="store_true", help="禁用 LLM，仅用规则解析")
    p_validate.set_defaults(func=_cmd_validate)

    return parser


def _force_utf8_stdio() -> None:
    """让 CLI 输出在重定向/管道场景下也保持 UTF-8，避免中文乱码。"""
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            continue


def main(argv: Optional[List[str]] = None) -> int:
    _force_utf8_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("已取消", file=sys.stderr)
        return 130
    except Exception as exc:  # noqa: BLE001 - CLI 统一错误出口
        print(f"错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
