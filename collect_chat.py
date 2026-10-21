# -*- coding: utf-8 -*-
"""微信 4.x PC 客户端群消息采集器（只读）。

通过 UI Automation 打开指定聊天，向上翻页采集指定日期的消息，落盘为 UTF-8 文本。
不读数据库、不注入进程，只读取界面可见内容。

用法:
    python collect_chat.py --group "示例群聊" --day yesterday
    python collect_chat.py --group "示例群聊" --day 2026-08-11 --out out.txt
"""
import argparse
import datetime as dt
import re
import subprocess
import sys
import time
from pathlib import Path

import uiautomation as auto

from clipboard_util import set_clipboard_text

auto.SetGlobalSearchTimeout(8)

WEEKDAY_CN = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "日": 7, "天": 7}

MSG_CLASSES = {
    "mmui::ChatTextItemView",        # 文本消息
    "mmui::ChatBubbleItemView",      # 链接/小程序/通话等卡片
    "mmui::ChatBubbleReferItemView", # 图片/动画表情等
    "mmui::ChatSystemInfoItemView",  # 系统提示（撤回、入群等）
}
TIME_CLASS = "mmui::ChatItemView"   # 时间戳条

RE_HM = re.compile(r"^(\d{1,2}):(\d{2})$")
RE_YESTERDAY = re.compile(r"^昨天\s+(\d{1,2}):(\d{2})$")
RE_WEEK = re.compile(r"^星期([一二三四五六日天])\s+(\d{1,2}):(\d{2})$")
RE_MD = re.compile(r"^(\d{1,2})月(\d{1,2})日(?:\s*星期[一二三四五六日天])?\s+(\d{1,2}):(\d{2})$")
RE_YMD = re.compile(r"^(\d{4})[年/](\d{1,2})[月/](\d{1,2})[日]?(?:\s*星期[一二三四五六日天])?\s*(?:(\d{1,2}):(\d{2}))?")


def parse_time_marker(text: str, now: dt.datetime):
    """把微信时间戳文本解析为 datetime；不是时间戳返回 None。"""
    t = (text or "").strip()
    m = RE_HM.match(t)
    if m:
        return now.replace(hour=int(m[1]), minute=int(m[2]), second=0, microsecond=0)
    m = RE_YESTERDAY.match(t)
    if m:
        d = now - dt.timedelta(days=1)
        return d.replace(hour=int(m[1]), minute=int(m[2]), second=0, microsecond=0)
    m = RE_WEEK.match(t)
    if m:
        wd = WEEKDAY_CN[m[1]]
        delta = (now.isoweekday() - wd) % 7 or 7
        d = now - dt.timedelta(days=delta)
        return d.replace(hour=int(m[2]), minute=int(m[3]), second=0, microsecond=0)
    m = RE_MD.match(t)
    if m:
        return dt.datetime(now.year, int(m[1]), int(m[2]), int(m[3]), int(m[4]))
    m = RE_YMD.match(t)
    if m:
        hh = int(m[4]) if m[4] else 0
        mm = int(m[5]) if m[5] else 0
        return dt.datetime(int(m[1]), int(m[2]), int(m[3]), hh, mm)
    return None


WECHAT_CANDIDATES = [
    r"D:\Weixin\Weixin.exe",
    r"C:\Program Files\Tencent\Weixin\Weixin.exe",
    r"C:\Program Files (x86)\Tencent\Weixin\Weixin.exe",
]


def find_wechat():
    win = auto.WindowControl(ClassName="mmui::MainWindow", searchDepth=1)
    if not win.Exists(5):
        login = auto.WindowControl(ClassName="mmui::LoginWindow", searchDepth=1)
        if not login.Exists(2):
            # 什么窗口都没有：微信整个退出了，尝试拉起
            exe = next((p for p in WECHAT_CANDIDATES if Path(p).exists()), None)
            if not exe:
                raise RuntimeError("找不到微信窗口，也未找到微信安装路径，请手动启动微信")
            print(f"微信未运行，尝试启动 {exe} ...", file=sys.stderr)
            subprocess.Popen([exe])
        # 等主窗口出现；出现一键登录窗就点「进入微信」
        deadline = time.time() + 60
        while time.time() < deadline:
            if win.Exists(2):
                break
            if login.Exists(1):
                enter = login.ButtonControl(Name="进入微信")
                if enter.Exists(0.5):
                    enter.Click(simulateMove=False)
                    print("点击了一键登录「进入微信」", file=sys.stderr)
                    time.sleep(3)
            time.sleep(1.5)
        if not win.Exists(1):
            raise RuntimeError("微信已启动但未完成登录（如需扫码请手动扫码后重跑）")
        time.sleep(3)  # 等界面加载完
    try:
        if win.IsMinimize():
            win.ShowWindow(auto.ShowWindow.Restore)
            time.sleep(1)
    except Exception:
        pass
    win.SetActive()
    time.sleep(0.5)
    return win


def ensure_main_view(win):
    """微信 4.x 有单聊紧凑模式（无搜索框/会话列表）。检测到就点「返回」回主界面。"""
    search = win.EditControl(ClassName="mmui::XValidatorTextEdit")
    if search.Exists(2):
        return
    back = win.ButtonControl(Name="返回", ClassName="mmui::XButton")
    if back.Exists(2):
        back.Click(simulateMove=False)
        time.sleep(1.0)
    if not search.Exists(3):
        raise RuntimeError("微信不在主界面（可能在单聊紧凑模式），且无法通过「返回」恢复")


def open_chat(win, name: str, retries: int = 2):
    """通过搜索框进入指定聊天，失败自动重试。"""
    last_err = None
    for attempt in range(retries + 1):
        try:
            return _open_chat_once(win, name)
        except Exception as e:
            last_err = e
            print(f"WARN: 进入聊天 {name!r} 第 {attempt + 1} 次失败: {e}", file=sys.stderr)
            try:
                win.SendKeys("{Esc}")
            except Exception:
                pass
            time.sleep(1.5)
    raise last_err


def _open_chat_once(win, name: str):
    ensure_main_view(win)
    search = win.EditControl(ClassName="mmui::XValidatorTextEdit")
    if not search.Exists(3):
        raise RuntimeError("找不到搜索框")

    # 真实点击获得焦点，清空残留内容，剪贴板粘贴（SetValue 不触发微信的搜索事件；
    # SendKeys 打不了中文和 emoji）
    search.Click(simulateMove=False)
    time.sleep(0.4)
    search.SendKeys("{Ctrl}a{Delete}")
    time.sleep(0.2)
    set_clipboard_text(name)
    search.SendKeys("{Ctrl}v")
    time.sleep(1.0)

    deadline = time.time() + 10
    target = None
    while time.time() < deadline:
        # 搜索弹窗是主窗口的子元素，不是顶层窗口
        pop = win.WindowControl(ClassName="mmui::SearchContentPopover")
        if pop.Exists(1):
            # 优先：联系人/群聊结果单元格
            cell = pop.ListItemControl(ClassName="mmui::SearchContentCellView", Name=name)
            if cell.Exists(1):
                target = cell
                break
            # 兜底：如「文件传输助手」在这台机器上不是联系人，
            # 只在「功能」分类下出现；点网络结果会跳到网页搜索，必须避开
            in_feature = False
            for item in pop.ListControl(ClassName="mmui::XTableView").GetChildren():
                if item.ClassName != "mmui::XTableCell":
                    continue
                if item.Name == "功能":
                    in_feature = True
                    continue
                if in_feature and item.Name == name:
                    target = item
                    break
            if target is not None:
                break
        time.sleep(0.4)
    if target is None:
        search.SendKeys("{Esc}")
        raise RuntimeError(f"搜索结果里找不到联系人/群: {name!r}")
    target.Click(simulateMove=False)
    time.sleep(1.5)
    # 清空残留搜索词（点击结果后一般会自己清空，防御一下）
    if search.Exists(1):
        try:
            search.SendKeys("{Esc}")
        except Exception:
            pass
    # 确认聊天真的打开了（标题栏文本等于目标名）
    deadline = time.time() + 8
    while time.time() < deadline:
        if win.TextControl(ClassName="mmui::XTextView", Name=name).Exists(1):
            return
        time.sleep(0.4)
    raise RuntimeError(f"点击搜索结果后聊天未打开: {name!r}")


def read_visible(msglist):
    """返回当前可见消息项列表: [(key, class, name, control)]，key 用于翻页去重。"""
    out = []
    for it in msglist.GetChildren():
        cls = it.ClassName
        if cls not in MSG_CLASSES and cls != TIME_CLASS:
            continue
        name = (it.Name or "").strip()
        out.append((f"{cls}|{name}", cls, name, it))
    return out


def focus_message_list(win, msglist):
    """把焦点放进消息列表，让 PageUp 生效。点列表中部空白处，避开消息气泡。"""
    rect = msglist.BoundingRectangle
    x = rect.left + (rect.right - rect.left) // 2
    y = rect.top + (rect.bottom - rect.top) // 2
    auto.Click(x, y)
    time.sleep(0.3)


def page_up(msglist):
    """小步滚轮上翻：步幅小、页间重叠大，拼接才可靠。"""
    msglist.WheelUp(wheelTimes=2)
    time.sleep(0.9)


def merge_pages(merged, visible, max_anchor: int = 8, min_run: int = 3):
    """把新翻出来的一屏拼到已有序列前面。
    候选对齐：merged[a] == visible[i]，从 (a, i) 起向后连续匹配 run 条。
    取 run 最长的候选（正确对齐的重叠区最长，泛用短文本不会胜出），
    且 run 必须 >= min_run。visible[:i-a] 为更老的新消息。
    返回 (新序列, 是否找到可靠重叠)。"""
    keys_v = [k for k, *_ in visible]
    keys_m = [k for k, *_ in merged]
    best = None
    for a in range(min(max_anchor, len(keys_m))):
        for i in range(len(keys_v) - 1, a - 1, -1):
            if keys_v[i] != keys_m[a]:
                continue
            run = 1
            while (a + run < len(keys_m) and i + run < len(keys_v)
                   and keys_v[i + run] == keys_m[a + run]):
                run += 1
            if best is None or run > best[2]:
                best = (a, i, run)
    if best is None or best[2] < min_run:
        return visible + merged, False
    a, i, _ = best
    return visible[: i - a] + merged, True


def visible_datetimes(visible, now):
    out = []
    for _, cls, name, _ in visible:
        if cls == TIME_CLASS:
            parsed = parse_time_marker(name, now)
            if parsed:
                out.append(parsed)
    return out


def seek_to_recent(msglist, start: dt.datetime, now, max_steps: int = 60):
    """微信会记住上次滚动位置。若当前视口整页都比采集起点老，
    先一路 PageDown 向最新方向找，直到视口里出现 >= start 的时间戳。"""
    prev_keys = None
    stale = 0
    for _ in range(max_steps):
        visible = read_visible(msglist)
        dts = visible_datetimes(visible, now)
        if any(d >= start for d in dts):
            return True
        keys = [k for k, *_ in visible]
        if keys == prev_keys:
            stale += 1
            if stale >= 3:
                return False
        else:
            stale = 0
        prev_keys = keys
        msglist.SendKeys("{PAGEDOWN}")
        time.sleep(0.8)
    return False


def _neighbor_ctx(seq, i):
    """图片消息的对齐上下文：前后邻居的 key（用来跨页去重和最终回填）。"""
    prev_k = seq[i - 1][0] if i > 0 else ""
    next_k = seq[i + 1][0] if i + 1 < len(seq) else ""
    return (prev_k, next_k)


def _grab_image_region(ctl):
    """直接截取消息项里的缩略图区域，不点开图片。
    别人发的图在左侧，自己发的在右侧；先左后右，取像素更丰富的那个。"""
    from PIL import ImageGrab, ImageStat
    r = ctl.BoundingRectangle
    w = r.right - r.left
    h = r.bottom - r.top
    # 水平取中段 55%（避开头像和最远端的空白），垂直留 10% 边距
    x0, x1 = int(r.left + w * 0.05), int(r.left + w * 0.55)
    y0, y1 = int(r.top + h * 0.08), int(r.bottom - h * 0.08)
    best, best_score = None, -1
    for (a, b) in [(x0, x1), (int(r.left + w * 0.45), int(r.right - w * 0.02))]:
        img = ImageGrab.grab(bbox=(a, y0, b, y1))
        score = ImageStat.Stat(img.convert("L")).stddev[0]
        if score > best_score:
            best, best_score = img, score
    if best_score < 8:  # 基本是纯色，没截到内容
        return None
    best.thumbnail((1280, 1280))
    return best


def _caption_visible_images(visible, captions, client, image_dir, max_images, win,
                            list_rect=None):
    """对当前屏里的图片消息直接截缩略图，用视觉模型生成一句话描述。
    不点开查看器（点击/Esc 会扰乱窗口状态）。单张失败不影响主流程。"""
    for i, (key, cls, name, ctl) in enumerate(visible):
        if len(captions) >= max_images:
            return
        if not (cls == "mmui::ChatBubbleReferItemView" and name == "图片"):
            continue
        # 跳过被遮挡/半屏外的条目（截出来会是标题栏或别的内容）
        if list_rect:
            r = ctl.BoundingRectangle
            if r.top < list_rect.top + 5 or r.bottom > list_rect.bottom - 5:
                continue
        ctx = _neighbor_ctx(visible, i)
        if ctx in captions:
            continue
        captions[ctx] = None
        try:
            img = _grab_image_region(ctl)
            if img is None:
                continue
            image_dir.mkdir(parents=True, exist_ok=True)
            path = image_dir / f"img_{len([v for v in captions.values() if v])}.png"
            img.save(path)
            captions[ctx] = client.caption_image(client.session_id, str(path)) or None
            print(f"[图片] 已描述 {path.name}: {(captions[ctx] or '')[:30]}", flush=True)
        except Exception as e:
            print(f"WARN: 图片描述失败: {e}", file=sys.stderr)


def collect_range(win, group: str, start: dt.datetime, end: dt.datetime,
                  max_pages: int = 400, caption_images: bool = False,
                  max_images: int = 8, image_dir=None):
    """采集 [start, end) 时间段内的群消息。
    返回 [(datetime, 文本, 类型), ...]（旧->新）；
    caption_images=True 时图片消息会尽量带上视觉模型的一句话描述。"""
    msglist = win.ListControl(ClassName="mmui::RecyclerListView")
    if not msglist.Exists(3):
        raise RuntimeError("找不到消息列表，进入聊天失败？")

    focus_message_list(win, msglist)

    now = dt.datetime.now()
    if not seek_to_recent(msglist, start, now):
        raise RuntimeError("无法把消息列表定位到目标时间段附近（PageDown 未生效？）")

    acp_client = None
    if caption_images:
        from acp_vision import KimiACP
        if image_dir:
            image_dir.mkdir(parents=True, exist_ok=True)
        acp_client = KimiACP(cwd=str(Path(__file__).parent))
        acp_client.session_id = acp_client.start_session()
    captions = {}  # 邻居上下文 -> 描述

    merged = []            # 已确认的完整序列（旧->新）
    prev_keys = None
    stale_rounds = 0
    gap_warned = False
    seen_in_range = False  # 是否已经见过 >= start 的时间戳

    try:
        for page in range(max_pages):
            # 每页重新获取列表控件：开/关图片查看器后微信会重建列表，旧引用会失效
            msglist = win.ListControl(ClassName="mmui::RecyclerListView")
            if not msglist.Exists(2):
                raise RuntimeError("消息列表控件丢失（窗口被切换？）")
            visible = read_visible(msglist)
            if not visible:
                time.sleep(0.8)
                continue

            keys = [k for k, *_ in visible]
            if prev_keys == keys:
                stale_rounds += 1
            else:
                stale_rounds = 0
                if not merged:
                    merged = list(visible)
                else:
                    merged, overlapped = merge_pages(merged, visible)
                    if not overlapped and not gap_warned:
                        print("WARN: 某一屏与已采集内容无重叠，可能有少量消息缺口", file=sys.stderr)
                        gap_warned = True
            prev_keys = keys

            dts = visible_datetimes(visible, now)
            if any(d >= start for d in dts):
                seen_in_range = True

            # 图片理解：只处理与目标时段有交集的页面
            if acp_client and len(captions) < max_images:
                intersects = (not dts) or (min(dts) < end and max(dts) >= start)
                if intersects:
                    _caption_visible_images(visible, captions, acp_client,
                                            image_dir, max_images, win,
                                            list_rect=msglist.BoundingRectangle)

            # 停止条件 1：已采到目标时段内容，且本屏整页都比起点老（已穿过目标时段）
            if seen_in_range and dts and max(dts) < start:
                break
            # 停止条件 2：连续两页翻不出新内容（到顶了）
            if stale_rounds >= 2:
                break

            page_up(msglist)
    finally:
        if acp_client:
            acp_client.close()

    # 按时间戳把消息归到时间点，只保留 [start, end)；图片回填描述
    result = []
    cur_dt = None
    for j, (_, cls, name, _) in enumerate(merged):
        if cls == TIME_CLASS:
            parsed = parse_time_marker(name, now)
            if parsed:
                cur_dt = parsed
            continue
        if cur_dt and start <= cur_dt < end:
            kind = classify_message(cls, name)
            if kind == "image" and captions:
                caption = captions.get(_neighbor_ctx(merged, j))
                if caption:
                    name = f"图片（{caption}）"
            result.append((cur_dt, name, kind))
    return result


def classify_message(cls: str, name: str) -> str:
    if cls == "mmui::ChatTextItemView":
        return "text"
    if cls == "mmui::ChatBubbleReferItemView":
        if name == "图片":
            return "image"
        if name.startswith("动画表情"):
            return "sticker"
        return "refer"
    if cls == "mmui::ChatBubbleItemView":
        return "card"      # 链接/小程序/通话记录等卡片
    if cls == "mmui::ChatSystemInfoItemView":
        return "system"
    return "other"


def collect_for_day(win, group: str, target: dt.date, max_pages: int = 400):
    """采集某一自然日的消息，返回 ['[HH:MM] 内容', ...]。"""
    start = dt.datetime.combine(target, dt.time.min)
    end = start + dt.timedelta(days=1)
    items = collect_range(win, group, start, end, max_pages)
    return [f"[{d.strftime('%H:%M')}] {name}" for d, name, _ in items]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", required=True, help="群/联系人名称（需与微信里显示的一致）")
    ap.add_argument("--day", default="yesterday", help="yesterday / today / YYYY-MM-DD")
    ap.add_argument("--out", default=None, help="输出文件路径")
    args = ap.parse_args()

    today = dt.date.today()
    if args.day == "yesterday":
        target = today - dt.timedelta(days=1)
    elif args.day == "today":
        target = today
    else:
        target = dt.date.fromisoformat(args.day)

    win = find_wechat()
    open_chat(win, args.group)
    lines = collect_for_day(win, args.group, target)

    out = Path(args.out) if args.out else (
        Path(__file__).parent / "output" / f"{args.group}_{target.isoformat()}.txt"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    header = f"# {args.group} {target.isoformat()} 消息记录（{len(lines)} 条）\n"
    out.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
    print(f"OK: {len(lines)} 条消息 -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())


def list_recent_sessions(win, max_cells: int = 40):
    """读取会话列表里可见的聊天标题（供 GUI 选群用）。
    单元格 Name 是多行文本，第一行就是标题。"""
    sessions = win.ListControl(ClassName="mmui::XTableView")
    if not sessions.Exists(3):
        return []
    titles = []
    for cell in sessions.GetChildren()[:max_cells]:
        if cell.ClassName != "mmui::ChatSessionCell":
            continue
        title = (cell.Name or "").split("\n")[0].strip()
        if title:
            titles.append(title)
    return titles
