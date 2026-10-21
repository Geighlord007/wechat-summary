# -*- coding: utf-8 -*-
"""剪贴板工具（ctypes，无第三方依赖）。"""
import ctypes
from ctypes import wintypes

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32

# 64 位下句柄/指针必须显式声明，否则被截断成 32 位 int
_kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
_kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
_kernel32.GlobalLock.restype = wintypes.LPVOID
_kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
_kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
_kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
_user32.SetClipboardData.restype = wintypes.HANDLE
_user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
_user32.GetClipboardData.restype = wintypes.HANDLE
_user32.GetClipboardData.argtypes = [wintypes.UINT]


def set_clipboard_text(text: str):
    if not _user32.OpenClipboard(None):
        raise RuntimeError("OpenClipboard 失败")
    try:
        _user32.EmptyClipboard()
        data = text.encode("utf-16-le") + b"\x00\x00"
        h = _kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not h:
            raise RuntimeError("GlobalAlloc 失败")
        ptr = _kernel32.GlobalLock(h)
        ctypes.memmove(ptr, data, len(data))
        _kernel32.GlobalUnlock(h)
        if not _user32.SetClipboardData(CF_UNICODETEXT, h):
            _kernel32.GlobalFree(h)
            raise RuntimeError("SetClipboardData 失败")
    finally:
        _user32.CloseClipboard()


def get_clipboard_text() -> str:
    if not _user32.OpenClipboard(None):
        return ""
    try:
        h = _user32.GetClipboardData(CF_UNICODETEXT)
        if not h:
            return ""
        ptr = _kernel32.GlobalLock(h)
        if not ptr:
            return ""
        try:
            return ctypes.wstring_at(ptr)
        finally:
            _kernel32.GlobalUnlock(h)
    finally:
        _user32.CloseClipboard()
