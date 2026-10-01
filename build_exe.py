# -*- coding: utf-8 -*-
"""打包脚本：用 PyInstaller 生成免运行时的单文件 exe。

用法（在项目根目录执行）：
    python build_exe.py                 # 使用当前解释器打包
    D:\\python3.12\\python.exe build_exe.py   # 指定 win-amd64 解释器

产物：
    dist/test-builder.exe   单文件可执行程序（内置模板与全部依赖，无需另装 Python）
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SEP = ";" if sys.platform.startswith("win") else ":"
APP_NAME = "test-builder"


def main() -> int:
    if sys.platform != "win32":
        print("本脚本用于生成 Windows exe，请在 Windows 环境执行。", file=sys.stderr)
        return 1

    try:
        import PyInstaller.__main__ as pyinstaller
    except ImportError:
        print("未检测到 PyInstaller。请先安装：pip install pyinstaller", file=sys.stderr)
        return 1

    template_dir = ROOT / "agent" / "templates"
    if not template_dir.is_dir():
        print(f"找不到模板目录：{template_dir}", file=sys.stderr)
        return 1

    # 清理上一次的产物，保证结果可复现
    for folder in ("build", "dist"):
        target = ROOT / folder
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)

    args = [
        str(ROOT / "app.py"),
        "--name", APP_NAME,
        "--onefile",           # 单文件，内置解释器与依赖
        "--console",           # 保留控制台，CLI 模式才能看到输出
        "--noconfirm",
        "--clean",
        # 内置 HTML 模板（运行时通过 sys._MEIPASS 定位）
        "--add-data", f"{template_dir}{SEP}agent/templates",
        # 确保动态导入的子模块被完整收集
        "--collect-submodules", "agent",
        "--hidden-import", "agent.gui",
        "--hidden-import", "agent.cli",
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(ROOT / "build"),
        "--specpath", str(ROOT / "build"),
    ]

    print("开始打包：", " ".join(args))
    pyinstaller.run(args)

    exe_path = ROOT / "dist" / f"{APP_NAME}.exe"
    if exe_path.is_file():
        size_mb = exe_path.stat().st_size / (1024 * 1024)
        print(f"\n打包完成：{exe_path}（约 {size_mb:.1f} MB）")
        print("双击运行进入图形界面；命令行可执行："
              f'{APP_NAME}.exe build -i samples -o out.html')
        return 0
    print("打包失败：未生成 exe。", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
