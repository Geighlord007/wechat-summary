# -*- coding: utf-8 -*-
"""调试：dump 搜索弹窗里所有单元格的类名和名字。"""
import sys
import time
import uiautomation as auto
from clipboard_util import set_clipboard_text

auto.SetGlobalSearchTimeout(5)
query = sys.argv[1] if len(sys.argv) > 1 else "文件传输助手"

win = auto.WindowControl(ClassName="mmui::MainWindow", searchDepth=1)
win.SetActive()
time.sleep(0.5)
search = win.EditControl(ClassName="mmui::XValidatorTextEdit")
search.Click(simulateMove=False)
time.sleep(0.4)
search.SendKeys("{Ctrl}a{Delete}")
set_clipboard_text(query)
search.SendKeys("{Ctrl}v")
time.sleep(2)

pop = win.WindowControl(ClassName="mmui::SearchContentPopover")
print("popover:", pop.Exists(2))
if pop.Exists(1):
    def walk(c, d=0):
        print("  " * d + f"{c.ControlTypeName} [{c.ClassName}] {repr((c.Name or '')[:80])}")
        if d < 4:
            for ch in c.GetChildren():
                walk(ch, d + 1)
    walk(pop)
search.SendKeys("{Esc}")
