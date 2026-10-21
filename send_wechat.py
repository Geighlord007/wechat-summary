# -*- coding: utf-8 -*-
"""把文本发送到微信「文件传输助手」。只此一个发送对象。"""
import time

import uiautomation as auto

from clipboard_util import get_clipboard_text, set_clipboard_text

FILE_HELPER = "文件传输助手"


def send_to_file_helper(win, text: str) -> bool:
    """发送成功返回 True。通过消息列表末尾出现该文本来验证。"""
    from collect_chat import open_chat  # 复用搜索进入聊天的逻辑

    old_clip = ""
    try:
        old_clip = get_clipboard_text()
    except Exception:
        pass

    try:
        open_chat(win, FILE_HELPER)
        time.sleep(1.0)

        edit = win.EditControl(ClassName="mmui::ChatInputField")
        if not edit.Exists(3):
            raise RuntimeError("找不到聊天输入框")
        edit.Click(simulateMove=False)
        time.sleep(0.3)
        set_clipboard_text(text)
        edit.SendKeys("{Ctrl}v")
        time.sleep(0.8)

        send_btn = win.ButtonControl(ClassName="mmui::XOutlineButton", Name="发送")
        if not send_btn.Exists(3):
            raise RuntimeError("找不到发送按钮")
        send_btn.Click(simulateMove=False)
        time.sleep(1.5)

        # 验证：消息列表最后一条应包含摘要开头
        msglist = win.ListControl(ClassName="mmui::RecyclerListView")
        if msglist.Exists(2):
            children = msglist.GetChildren()
            tail = "\n".join((c.Name or "") for c in children[-3:])
            head = text.replace("\n", " ")[:20]
            if text[:20] in tail or head in tail:
                return True
        return False
    finally:
        try:
            set_clipboard_text(old_clip)  # 恢复用户剪贴板
        except Exception:
            pass
