# -*- coding: utf-8 -*-
"""图形界面：题库一键导入 → 校验 → 一键生成 HTML 刷题系统。

界面分三步：
    第一步  导入题库（支持 JSON / CSV / TSV / Excel / Markdown / 纯文本，可多选）
    第二步  填写标题、副标题、公告与输出路径
    第三步  一键生成 HTML，并查看构建日志
"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import traceback
import webbrowser
from pathlib import Path
from typing import Callable, List, Optional

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import __version__
from .parsers import LLMConfig
from .parsers.base import SUPPORTED_SUFFIXES
from .pipeline import BuildOptions, FileValidation, run, validate_file
from .schema import QuizMeta

APP_TITLE = f"自测生成系统 v{__version__}"

_FILE_TYPES = [
    ("全部支持的题库", "*.json *.csv *.tsv *.xlsx *.xls *.md *.markdown *.txt"),
    ("JSON 题库", "*.json"),
    ("表格题库", "*.csv *.tsv *.xlsx *.xls"),
    ("Markdown / 文本", "*.md *.markdown *.txt"),
    ("全部文件", "*.*"),
]

_HELP_TEXT = """\
使用步骤
────────────────────────────────────────
第 1 步  导入题库
    · 点击「添加文件」可多选，或「添加文件夹」批量导入整个目录。
    · 支持格式：JSON、CSV / TSV、Excel(xlsx/xls)、Markdown、纯文本。
    · 导入后自动解析并做数据校验，列表中会显示每题文件的状态与题目数。

第 2 步  填写信息
    · 标题 / 副标题 / 公告 / 获取最新版地址：将写入生成的刷题系统页面。

第 3 步  一键生成 HTML
    · 选择输出路径后点击「一键生成 HTML」。
    · 生成成功后可「打开文件」或「打开所在文件夹」。

数据校验说明
────────────────────────────────────────
每道题都会校验：题干非空、选项不少于 2 个且以 A/B/C… 开头、
答案在选项范围内、多选答案为数组、题型为 单选/多选/判断。
校验未通过的题目会被跳过并在日志中列出原因，不会中断整体生成。

常见问题
────────────────────────────────────────
· 提示「未解析出有效题目」：请检查题库是否包含题干与答案，或改用标准 JSON。
· Excel 读取失败：请确认文件未加密，且题目在第一个工作表内。
· JSON 语法错误：日志会给出具体行号与列号。
"""


class TestBuilderApp:
    """主窗口。"""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.files: List[Path] = []
        self.validations: dict = {}
        self._queue: "queue.Queue" = queue.Queue()
        self._busy = False

        root.title(APP_TITLE)
        root.geometry("900x680")
        root.minsize(820, 600)

        self._build_menu()
        self._build_widgets()
        self._set_status("就绪。请先导入题库文件。")

    # ------------------------------------------------------------------ 界面
    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="添加文件…", command=self.add_files)
        file_menu.add_command(label="添加文件夹…", command=self.add_folder)
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self.root.destroy)
        menubar.add_cascade(label="文件", menu=file_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="操作指引", command=self.show_help)
        help_menu.add_command(label="关于", command=self.show_about)
        menubar.add_cascade(label="帮助", menu=help_menu)
        self.root.config(menu=menubar)

    def _build_widgets(self) -> None:
        outer = ttk.Frame(self.root, padding=10)
        outer.pack(fill="both", expand=True)

        head = ttk.Frame(outer)
        head.pack(fill="x")
        ttk.Label(head, text=APP_TITLE, font=("Microsoft YaHei UI", 13, "bold")).pack(side="left")
        ttk.Button(head, text="操作指引", command=self.show_help).pack(side="right")

        # 第一步：导入题库
        step1 = ttk.LabelFrame(outer, text=" 第一步：导入题库（JSON / CSV / Excel / Markdown / 文本） ", padding=8)
        step1.pack(fill="both", expand=True, pady=(10, 0))

        bar = ttk.Frame(step1)
        bar.pack(fill="x", pady=(0, 6))
        ttk.Button(bar, text="添加文件", command=self.add_files).pack(side="left")
        ttk.Button(bar, text="添加文件夹", command=self.add_folder).pack(side="left", padx=6)
        ttk.Button(bar, text="移除选中", command=self.remove_selected).pack(side="left")
        ttk.Button(bar, text="清空列表", command=self.clear_files).pack(side="left", padx=6)
        ttk.Button(bar, text="重新校验", command=self.revalidate).pack(side="left")

        columns = ("name", "format", "status", "count")
        self.tree = ttk.Treeview(step1, columns=columns, show="headings", height=8)
        for col, text, width in (
            ("name", "文件名", 320),
            ("format", "格式", 90),
            ("status", "校验状态", 200),
            ("count", "有效题目", 90),
        ):
            self.tree.heading(col, text=text)
            self.tree.column(col, width=width, anchor="w")
        self.tree.pack(side="left", fill="both", expand=True)

        scroll = ttk.Scrollbar(step1, orient="vertical", command=self.tree.yview)
        scroll.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scroll.set)

        # 第二步：生成信息
        step2 = ttk.LabelFrame(outer, text=" 第二步：填写刷题系统信息 ", padding=8)
        step2.pack(fill="x", pady=(10, 0))
        step2.columnconfigure(1, weight=1)

        self.var_title = tk.StringVar(value="在线自测系统")
        self.var_subtitle = tk.StringVar(value="自测系统")
        self.var_update = tk.StringVar(value="#")
        self.var_llm = tk.BooleanVar(value=False)

        ttk.Label(step2, text="标题").grid(row=0, column=0, sticky="w", padx=(0, 6), pady=3)
        ttk.Entry(step2, textvariable=self.var_title).grid(row=0, column=1, columnspan=2, sticky="ew", pady=3)
        ttk.Label(step2, text="副标题").grid(row=1, column=0, sticky="w", padx=(0, 6), pady=3)
        ttk.Entry(step2, textvariable=self.var_subtitle).grid(row=1, column=1, columnspan=2, sticky="ew", pady=3)
        ttk.Label(step2, text="更新地址").grid(row=2, column=0, sticky="w", padx=(0, 6), pady=3)
        ttk.Entry(step2, textvariable=self.var_update).grid(row=2, column=1, columnspan=2, sticky="ew", pady=3)
        ttk.Label(step2, text="公告内容").grid(row=3, column=0, sticky="nw", padx=(0, 6), pady=3)
        self.txt_announce = tk.Text(step2, height=3, wrap="word")
        self.txt_announce.grid(row=3, column=1, columnspan=2, sticky="ew", pady=3)
        self.txt_announce.insert("1.0", "欢迎使用本刷题系统，祝学习顺利！")

        ttk.Label(step2, text="输出文件").grid(row=4, column=0, sticky="w", padx=(0, 6), pady=3)
        self.var_output = tk.StringVar(value=str(self._default_output()))
        ttk.Entry(step2, textvariable=self.var_output).grid(row=4, column=1, sticky="ew", pady=3)
        ttk.Button(step2, text="浏览…", command=self.choose_output).grid(row=4, column=2, padx=(6, 0))

        ttk.Checkbutton(step2, text="启用深度学习语义解析（需配置 QUIZ_LLM_API_KEY，未配置时自动降级为规则解析）",
                        variable=self.var_llm).grid(row=5, column=1, columnspan=2, sticky="w", pady=3)

        # 第三步：生成
        step3 = ttk.LabelFrame(outer, text=" 第三步：一键生成 HTML ", padding=8)
        step3.pack(fill="both", expand=True, pady=(10, 0))

        action = ttk.Frame(step3)
        action.pack(fill="x")
        self.btn_generate = ttk.Button(action, text="一键生成 HTML", command=self.generate)
        self.btn_generate.pack(side="left")
        ttk.Button(action, text="打开文件", command=self.open_output).pack(side="left", padx=6)
        ttk.Button(action, text="打开所在文件夹", command=self.open_output_folder).pack(side="left")

        self.txt_log = tk.Text(step3, height=10, wrap="word", state="disabled")
        self.txt_log.pack(fill="both", expand=True, pady=(6, 0))

        self.var_status = tk.StringVar(value="")
        ttk.Label(self.root, textvariable=self.var_status, relief="sunken", anchor="w",
                  padding=(8, 3)).pack(fill="x", side="bottom")

        self._poll_queue()

    # ---------------------------------------------------------------- 工具
    @staticmethod
    def _default_output() -> Path:
        desktop = Path.home() / "Desktop"
        base = desktop if desktop.is_dir() else Path.cwd()
        return base / "刷题系统.html"

    def _set_status(self, text: str) -> None:
        self.var_status.set(text)

    def _log(self, text: str) -> None:
        self.txt_log.configure(state="normal")
        self.txt_log.insert("end", text.rstrip() + "\n")
        self.txt_log.see("end")
        self.txt_log.configure(state="disabled")

    def _clear_log(self) -> None:
        self.txt_log.configure(state="normal")
        self.txt_log.delete("1.0", "end")
        self.txt_log.configure(state="disabled")

    def _poll_queue(self) -> None:
        try:
            while True:
                callback, result, error = self._queue.get_nowait()
                self._busy = False
                self.btn_generate.state(["!disabled"])
                callback(result, error)
        except queue.Empty:
            pass
        self.root.after(120, self._poll_queue)

    def _run_async(self, work: Callable, on_done: Callable) -> None:
        if self._busy:
            messagebox.showinfo("请稍候", "当前任务正在执行，请等待完成。")
            return
        self._busy = True
        self.btn_generate.state(["disabled"])

        def runner() -> None:
            try:
                self._queue.put((on_done, work(), None))
            except Exception as exc:  # noqa: BLE001 - 交由回调统一提示
                self._queue.put((on_done, None, exc))

        threading.Thread(target=runner, daemon=True).start()

    # ------------------------------------------------------------ 题库导入
    def add_files(self) -> None:
        paths = filedialog.askopenfilenames(title="选择题库文件", filetypes=_FILE_TYPES)
        self._add_paths([Path(p) for p in paths])

    def add_folder(self) -> None:
        folder = filedialog.askdirectory(title="选择题库文件夹")
        if not folder:
            return
        found = [p for p in sorted(Path(folder).rglob("*"))
                 if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES]
        if not found:
            messagebox.showwarning("未找到题库", "该文件夹下没有找到支持格式的题库文件。")
            return
        self._add_paths(found)

    def _add_paths(self, paths: List[Path]) -> None:
        added = 0
        for path in paths:
            if path.suffix.lower() not in SUPPORTED_SUFFIXES:
                self._log(f"[跳过] 不支持的文件格式：{path.name}")
                continue
            if path in self.files:
                continue
            self.files.append(path)
            self.tree.insert("", "end", iid=str(path), values=(path.name, path.suffix.lstrip("."), "待校验", "-"))
            added += 1
        if not added:
            return
        self._log(f"[导入] 新增 {added} 个文件，开始解析与校验…")
        self._do_validate()

    def remove_selected(self) -> None:
        for iid in self.tree.selection():
            path = Path(iid)
            if path in self.files:
                self.files.remove(path)
            self.validations.pop(path, None)
            self.tree.delete(iid)

    def clear_files(self) -> None:
        self.files.clear()
        self.validations.clear()
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self._set_status("已清空题库列表。")

    def revalidate(self) -> None:
        if not self.files:
            messagebox.showinfo("提示", "请先导入题库文件。")
            return
        self._do_validate()

    def _do_validate(self) -> None:
        targets = list(self.files)
        self._set_status(f"正在校验 {len(targets)} 个文件…")
        self._run_async(lambda: [validate_file(p, self._llm_config()) for p in targets],
                        self._on_validated)

    def _on_validated(self, results, error) -> None:
        if error is not None:
            self._report_error("校验失败", error)
            return
        for res in results:
            self.validations[res.path] = res
            status = res.describe()
            count = str(res.valid) if res.valid else "-"
            self.tree.item(str(res.path), values=(res.path.name, res.path.suffix.lstrip("."),
                                                  status, count))
            for warn in res.warnings:
                self._log(f"  · [{res.path.name}] {warn}")
            for err in res.errors:
                self._log(f"  ! [{res.path.name}] {err}")
        good = [r for r in results if r.ok]
        bad = [r for r in results if not r.ok]
        total = sum(r.valid for r in results)
        self._log(f"[校验完成] 通过 {len(good)} 个文件 / 共 {len(results)} 个，"
                  f"有效题目 {total} 题。")
        if bad:
            self._log("  ! 未通过的文件：" + "、".join(r.path.name for r in bad))
        self._set_status(f"校验完成：{len(good)}/{len(results)} 个文件可用，共 {total} 题。")

    # ------------------------------------------------------------ 生成环节
    def choose_output(self) -> None:
        path = filedialog.asksaveasfilename(title="保存 HTML 到", defaultextension=".html",
                                            initialfile="刷题系统.html",
                                            filetypes=[("HTML 文件", "*.html")])
        if path:
            self.var_output.set(path)

    def _llm_config(self) -> LLMConfig:
        if not self.var_llm.get():
            return LLMConfig.from_env(mode="rule")
        if not os.getenv("QUIZ_LLM_API_KEY"):
            self._log("[提示] 未检测到 QUIZ_LLM_API_KEY，本次自动降级为规则解析。")
            return LLMConfig.from_env(mode="rule")
        return LLMConfig.from_env(mode="hybrid")

    def generate(self) -> None:
        if not self.files:
            messagebox.showwarning("缺少题库", "请先在第一步导入至少一个题库文件。")
            return
        usable = [p for p in self.files if self.validations.get(p) and self.validations[p].ok]
        if not usable:
            messagebox.showerror("无法生成", "当前没有校验通过的题库文件，请检查导入结果或点击「重新校验」。")
            return

        output = Path(self.var_output.get().strip())
        if not output.suffix:
            output = output.with_suffix(".html")
        if not output.parent.is_dir():
            try:
                output.parent.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                messagebox.showerror("输出路径不可用", f"无法创建输出目录：\n{output.parent}\n{exc}")
                return

        meta = QuizMeta(
            title=self.var_title.get().strip() or "在线自测系统",
            subtitle=self.var_subtitle.get().strip() or "自测系统",
            announcement=[l for l in self.txt_announce.get("1.0", "end").splitlines() if l.strip()],
            update_url=self.var_update.get().strip() or "#",
        )
        options = BuildOptions(inputs=usable, output=output, meta=meta, llm=self._llm_config())
        self._clear_log()
        self._set_status(f"正在生成：{output.name} …")
        self._log(f"[生成] 输入 {len(usable)} 个文件 -> {output}")
        self._run_async(lambda: run(options), self._on_generated)

    def _on_generated(self, report, error) -> None:
        if error is not None:
            self._report_error("生成失败", error)
            return
        self._log("[完成] " + report.summary().replace("\n", "\n        "))
        self._set_status(f"生成成功：{report.output}")
        messagebox.showinfo("生成成功",
                            f"共生成 {report.total} 道题。\n\n输出文件：\n{report.output}")

    def open_output(self) -> None:
        path = Path(self.var_output.get().strip())
        if path.is_file():
            webbrowser.open(path.as_uri())
        else:
            messagebox.showinfo("提示", "输出文件尚未生成。")

    def open_output_folder(self) -> None:
        path = Path(self.var_output.get().strip())
        folder = path.parent if path.parent.is_dir() else Path.cwd()
        try:
            if sys.platform.startswith("win"):
                subprocess.Popen(["explorer", str(folder)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except OSError as exc:
            messagebox.showerror("打开失败", str(exc))

    # ------------------------------------------------------------ 提示信息
    def _report_error(self, title: str, error: Exception) -> None:
        detail = "".join(traceback.format_exception_only(type(error), error)).strip()
        self._log(f"[错误] {detail}")
        self._set_status(f"{title}：{detail}")
        if self._log_has_traceback(error):
            self._log(traceback.format_exc())
        messagebox.showerror(title, detail)

    @staticmethod
    def _log_has_traceback(error: Exception) -> bool:
        return not isinstance(error, (ValueError, RuntimeError, FileNotFoundError))

    def show_help(self) -> None:
        win = tk.Toplevel(self.root)
        win.title("操作指引")
        win.geometry("640x560")
        text = tk.Text(win, wrap="word", padx=12, pady=12)
        text.pack(fill="both", expand=True)
        text.insert("1.0", _HELP_TEXT)
        text.configure(state="disabled")

    def show_about(self) -> None:
        messagebox.showinfo("关于", f"{APP_TITLE}\n\n"
                                    "将任意格式题库一键转换为 HTML 刷题系统。\n"
                                    "支持 JSON / CSV / Excel / Markdown / 纯文本。")


def main() -> int:
    """启动图形界面。"""
    root = tk.Tk()
    try:
        root.call("tk", "scaling", 1.2)
    except tk.TclError:
        pass
    TestBuilderApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
