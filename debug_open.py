# -*- coding: utf-8 -*-
"""测试：从紧凑模式恢复 + emoji 群名搜索进群。"""
import sys
import time
import uiautomation as auto
from collect_chat import find_wechat, open_chat

auto.SetGlobalSearchTimeout(6)

win = find_wechat()
name = sys.argv[1] if len(sys.argv) > 1 else "示例群聊"
open_chat(win, name)
print(f"OK: 已进入 {name}")
