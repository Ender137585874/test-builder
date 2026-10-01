# -*- coding: utf-8 -*-
"""test-builder（自测生成系统）统一入口。

双击运行时启动图形界面；带命令行参数时作为 CLI 使用：

    test-builder.exe                        # 图形界面
    test-builder.exe build -i samples -o out.html
    test-builder.exe validate -i samples
    test-builder.exe --help

打包为单个 exe 时采用 ``--console`` 模式，以便 CLI 输出可见；
双击（无参数）启动时会自动隐藏多余的控制台窗口。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# 保证源码运行时能定位到 agent 包
sys.path.insert(0, str(Path(__file__).resolve().parent))


def _hidden_by_double_click() -> bool:
    """判断当前进程是否由双击（独占控制台）启动，可安全隐藏控制台窗口。"""
    if os.name != "nt":
        return False
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        hwnd = kernel32.GetConsoleWindow()
        if not hwnd:
            return False
        # 控制台内只有当前进程 -> 双击启动，可以隐藏
        pids = (ctypes.c_uint * 4)()
        count = kernel32.GetConsoleProcessList(pids, 4)
        return count <= 1
    except Exception:  # noqa: BLE001 - 隐藏失败不影响功能
        return False


def _hide_console() -> None:
    try:
        import ctypes

        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE
    except Exception:  # noqa: BLE001
        pass


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if argv:
        # 命令行模式：保留控制台输出
        from agent.cli import main as cli_main

        return cli_main(argv)

    # 图形界面模式：双击启动时隐藏控制台
    if _hidden_by_double_click():
        _hide_console()

    try:
        from agent.gui import main as gui_main
    except ImportError as exc:  # 缺少 tkinter 时给出明确指引
        print("无法启动图形界面（缺少 tkinter）。请改用命令行模式："
              "test-builder.exe --help", file=sys.stderr)
        print(f"详细信息：{exc}", file=sys.stderr)
        return 1
    return gui_main()


if __name__ == "__main__":
    raise SystemExit(main())
