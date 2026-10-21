# -*- coding: utf-8 -*-
"""探测：群聊消息项的子树里有没有发送人昵称。"""
import sys
import time
import uiautomation as auto
from clipboard_util import set_clipboard_text
from collect_chat import find_wechat, open_chat

auto.SetGlobalSearchTimeout(5)

win = find_wechat()
name = sys.argv[1] if len(sys.argv) > 1 else "示例群聊"
open_chat(win, name)
time.sleep(1)

msglist = win.ListControl(ClassName="mmui::RecyclerListView")
items = [c for c in msglist.GetChildren() if c.ClassName == "mmui::ChatTextItemView"]
print(f"文本消息项: {len(items)}")
if not items:
    sys.exit(1)

def walk(c, d=0, out=None):
    out.append("  " * d + f"{c.ControlTypeName} [{c.ClassName}] name={repr((c.Name or '')[:60])}")
    if d < 5:
        for ch in c.GetChildren():
            walk(ch, d + 1, out)

for it in items[-3:]:
    out = []
    walk(it, 0, out)
    print("\n".join(out))
    print("---")
