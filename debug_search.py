# -*- coding: utf-8 -*-
"""调试：设置搜索词后，dump 搜索弹窗内容。"""
import time
import uiautomation as auto

auto.SetGlobalSearchTimeout(5)

win = auto.WindowControl(ClassName="mmui::MainWindow", searchDepth=1)
print("main window:", win.Exists(3))
win.SetActive()
time.sleep(0.5)

search = win.EditControl(ClassName="mmui::XValidatorTextEdit")
print("search edit:", search.Exists(3))
try:
    search.Click(simulateMove=False)
    time.sleep(0.5)
    search.SendKeys("NBA", interval=0.1)
    time.sleep(0.5)
    try:
        print("value after typing:", repr(search.GetValuePattern().Value))
    except Exception as e:
        print("read value failed:", e)
except Exception as e:
    print("typing failed:", e)

time.sleep(2)

# 1) 打印所有顶层窗口
print("--- top-level windows ---")
for w in auto.GetRootControl().GetChildren():
    print("TOP:", repr(w.ClassName), repr((w.Name or "")[:40]), w.BoundingRectangle)

# 2) 在主窗口子树里找 SearchContent 相关元素
print("--- search-related in main window ---")
found = win.GetChildren()
def walk(c, depth=0, path=""):
    cls = c.ClassName or ""
    if "Search" in cls or "search" in cls:
        print("  " * depth + f"{c.ControlTypeName} {cls} {repr((c.Name or '')[:60])} {c.BoundingRectangle}")
    if depth < 6:
        for ch in c.GetChildren():
            walk(ch, depth + 1, path)
walk(win)
