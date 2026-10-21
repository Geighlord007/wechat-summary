# -*- coding: utf-8 -*-
"""最小验证：确认本机微信 4.x 的关键 UIA 元素可读取。
只做只读操作：找到主窗口、搜索框、会话列表、消息列表，并打印消息项。
"""
import sys
import uiautomation as auto

auto.SetGlobalSearchTimeout(5)


def main():
    win = auto.WindowControl(ClassName="mmui::MainWindow", searchDepth=1)
    if not win.Exists(3):
        print("FAIL: 找不到微信主窗口 (mmui::MainWindow)，请确认微信已登录且在桌面上")
        return 1
    print(f"OK: 找到微信主窗口 name={win.Name!r} rect={win.BoundingRectangle}")

    # 搜索框
    search = win.EditControl(ClassName="mmui::XValidatorTextEdit")
    print(f"搜索框: {'OK' if search.Exists(2) else 'MISSING'}")

    # 会话列表
    sessions = win.ListControl(ClassName="mmui::XTableView")
    if sessions.Exists(2):
        cells = sessions.GetChildren()
        print(f"会话列表: OK, 可见会话数={len(cells)}")
        for c in cells[:5]:
            print(f"  - [{c.ClassName}] {c.Name[:60] if c.Name else ''}")
    else:
        print("会话列表: MISSING")

    # 消息列表（当前打开的聊天）
    msglist = win.ListControl(ClassName="mmui::RecyclerListView")
    if not msglist.Exists(2):
        print("消息列表: MISSING（请先打开一个聊天窗口再验证）")
        return 1
    items = msglist.GetChildren()
    print(f"消息列表: OK, 当前可见消息数={len(items)}")
    for it in items:
        name = (it.Name or "").replace("\n", " ")
        print(f"  - [{it.ClassName}] {name[:70]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
