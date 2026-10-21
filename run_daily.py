# -*- coding: utf-8 -*-
"""按 config.json 执行：逐群采集 -> 逐群摘要 -> 每个群单独发一条到文件传输助手。
原始消息同时存 txt 和 json（时间/类型/内容；发送人昵称微信 4.x 界面不暴露，记为 null）。
每次运行的完整输出写入 logs/run_时间戳.log。

config.json 结构（可用 gui.py 可视化管理）：
{
  "groups": ["示例群聊"],
  "range": {"mode": "yesterday" | "today" | "last_hours" | "last_days",
            "hours": 24, "days": 7},
  "schedule": {"freq": "none" | "daily" | "hourly" | "weekly",
               "time": "09:07", "every_hours": 3, "weekday": "MON"},
  "send": true,
  "image_understanding": false
}

命令行覆盖（调试用）：
    python run_daily.py --no-send
    python run_daily.py --group "示例群聊" --range last_days --days 7
"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from collect_chat import collect_range, find_wechat, open_chat
from paths import BASE
from send_wechat import send_to_file_helper
from summarize import summarize

CONFIG_PATH = BASE / "config.json"

DEFAULT_CONFIG = {
    "groups": ["示例群聊"],
    "range": {"mode": "yesterday", "hours": 24, "days": 7},
    "schedule": {"freq": "daily", "time": "09:07", "every_hours": 3, "weekday": "MON"},
    "send": True,
    "image_understanding": False,
    "max_images": 8,
}


class Tee:
    """把 print 同时写到原 stdout（如有）和日志文件。"""

    def __init__(self, path):
        self.f = open(path, "w", encoding="utf-8")
        self.out = sys.__stdout__  # 无控制台/未重定向时为 None

    def write(self, s):
        if self.out is not None:
            try:
                self.out.write(s)
            except Exception:
                pass
        self.f.write(s)

    def flush(self):
        if self.out is not None:
            try:
                self.out.flush()
            except Exception:
                pass
        self.f.flush()


def load_config() -> dict:
    if CONFIG_PATH.exists():
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        merged = dict(DEFAULT_CONFIG)
        merged.update(cfg)
        merged["range"] = {**DEFAULT_CONFIG["range"], **cfg.get("range", {})}
        merged["schedule"] = {**DEFAULT_CONFIG["schedule"], **cfg.get("schedule", {})}
        return merged
    return dict(DEFAULT_CONFIG)


def save_config(cfg: dict):
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def resolve_range(cfg_range: dict):
    """返回 (start, end, 中文标签)。"""
    now = dt.datetime.now()
    mode = cfg_range.get("mode", "yesterday")
    if mode == "yesterday":
        start = dt.datetime.combine(now.date() - dt.timedelta(days=1), dt.time.min)
        end = start + dt.timedelta(days=1)
        label = f"昨日 {start.month}/{start.day}"
    elif mode == "today":
        start = dt.datetime.combine(now.date(), dt.time.min)
        end = now
        label = f"今日 {start.month}/{start.day} 截至 {now.strftime('%H:%M')}"
    elif mode == "last_hours":
        hours = max(1, int(cfg_range.get("hours", 24)))
        start = now - dt.timedelta(hours=hours)
        end = now
        label = f"最近{hours}小时"
    elif mode == "last_days":
        days = max(1, int(cfg_range.get("days", 7)))
        start = now - dt.timedelta(days=days)
        end = now
        label = f"最近{days}天"
    else:
        raise ValueError(f"未知 range.mode: {mode}")
    return start, end, label


def format_transcript(group: str, label: str, items) -> str:
    today = dt.date.today()
    lines = []
    for d, name, _kind in items:
        stamp = d.strftime("%H:%M") if d.date() == today else d.strftime("%m-%d %H:%M")
        lines.append(f"[{stamp}] {name}")
    return f"# {group}（{label}，{len(lines)} 条）\n" + "\n".join(lines)


def save_json_archive(path: Path, group: str, label: str, start, end, items):
    """原始消息 JSON 存档。sender 目前恒为 null（微信 4.x 界面不暴露发送人）。"""
    data = {
        "group": group,
        "range_label": label,
        "range_start": start.isoformat(),
        "range_end": end.isoformat(),
        "collected_at": dt.datetime.now().isoformat(),
        "message_count": len(items),
        "messages": [
            {
                "time": d.isoformat(),
                "sender": None,
                "type": kind,
                "content": name,
            }
            for d, name, kind in items
        ],
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-send", action="store_true")
    ap.add_argument("--group", action="append", help="覆盖配置里的群列表，可多次指定")
    ap.add_argument("--range", dest="range_mode",
                    choices=["yesterday", "today", "last_hours", "last_days"])
    ap.add_argument("--hours", type=int, default=None)
    ap.add_argument("--days", type=int, default=None)
    args = ap.parse_args()

    log_dir = BASE / "logs"
    log_dir.mkdir(exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    sys.stdout = sys.stderr = Tee(log_dir / f"run_{stamp}.log")

    cfg = load_config()
    groups = args.group or cfg["groups"]
    range_cfg = dict(cfg["range"])
    if args.range_mode:
        range_cfg["mode"] = args.range_mode
    if args.hours:
        range_cfg["hours"] = args.hours
    if args.days:
        range_cfg["days"] = args.days
    start, end, label = resolve_range(range_cfg)
    print(f"=== 运行 {stamp}，范围: {label}，群: {len(groups)} 个 ===", flush=True)

    out_dir = BASE / "output"
    out_dir.mkdir(exist_ok=True)

    win = find_wechat()
    do_send = cfg.get("send", True) and not args.no_send

    failures = []
    sent = 0
    for group in groups:
        try:
            open_chat(win, group)
            items = collect_range(
                win, group, start, end,
                caption_images=cfg.get("image_understanding", False),
                max_images=int(cfg.get("max_images", 8)),
                image_dir=out_dir / "images" / stamp,
            )
            transcript = format_transcript(group, label, items)
            safe_name = group.replace("/", "_")
            (out_dir / f"{safe_name}_{stamp}.txt").write_text(
                transcript + "\n", encoding="utf-8")
            save_json_archive(out_dir / f"{safe_name}_{stamp}.json",
                              group, label, start, end, items)
            print(f"[采集] {group}: {len(items)} 条", flush=True)

            if not items:
                summary = "没什么实质讨论"
            else:
                summary = summarize(transcript, group, label)
            (out_dir / f"{safe_name}_{stamp}_summary.txt").write_text(
                summary + "\n", encoding="utf-8")
            print(f"[摘要] {group}: 完成", flush=True)

            if do_send:
                message = f"📋 {group}（{label}）\n\n{summary}"
                if send_to_file_helper(win, message):
                    sent += 1
                    print(f"[发送] {group}: 已发送", flush=True)
                else:
                    print(f"[发送] {group}: 发送后未验证到消息", file=sys.stderr, flush=True)
                    failures.append(f"{group}(发送未验证)")
        except Exception as e:
            print(f"[失败] {group}: {e}", file=sys.stderr, flush=True)
            failures.append(group)

    if failures and do_send:
        send_to_file_helper(win, "⚠️ 群日报：以下群处理失败: " + "、".join(failures))
    print(f"=== 结束：成功 {len(groups) - len(failures)}/{len(groups)}，"
          f"发送 {sent} 条，失败 {len(failures)} ===", flush=True)
    if len(groups) - len(failures) == 0:
        return 3
    return 0 if not failures else 4


if __name__ == "__main__":
    sys.exit(main())
