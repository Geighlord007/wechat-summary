# -*- coding: utf-8 -*-
"""路径与运行方式：源码运行 vs PyInstaller 打包运行。"""
import os
import shutil
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    BASE = Path(sys.executable).parent   # 打包后：exe 所在目录
else:
    BASE = Path(__file__).parent         # 源码运行：项目目录


def find_kimi() -> str:
    """定位本机 Kimi Code CLI 可执行文件：环境变量 KIMI_BIN > PATH > 默认安装位置。"""
    exe = os.environ.get("KIMI_BIN") or shutil.which("kimi")
    if exe:
        return exe
    default = Path.home() / ".kimi-code" / "bin" / "kimi.exe"
    if default.exists():
        return str(default)
    raise RuntimeError("找不到 kimi CLI：请安装 Kimi Code CLI 并加入 PATH，"
                       "或设置环境变量 KIMI_BIN 指向 kimi 可执行文件")


def backend_cmd():
    """后端（采集+摘要+发送）的启动命令。"""
    if getattr(sys, "frozen", False):
        return [str(BASE / "wxsum-run.exe")]
    return [str(BASE / ".venv" / "Scripts" / "python.exe"),
            str(BASE / "run_daily.py")]


def backend_cmd_str():
    """给 schtasks 用的命令行字符串。"""
    return " ".join(f'"{c}"' for c in backend_cmd())
