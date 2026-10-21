# -*- coding: utf-8 -*-
"""微信群日报 - 图形界面（customtkinter，朴素现代风）。

管理 config.json：群列表、时间范围、运行频率、发送与图片理解开关；
注册/删除 Windows 计划任务；手动运行并查看日志。
"""
import datetime as dt
import json
import queue
import subprocess
import threading
from pathlib import Path

import customtkinter as ctk

from paths import BASE, backend_cmd, backend_cmd_str

CONFIG_PATH = BASE / "config.json"
TASK_NAME = "WechatGroupDailySummary"

DEFAULT_CONFIG = {
    "groups": ["示例群聊"],
    "range": {"mode": "yesterday", "hours": 24, "days": 7},
    "schedule": {"freq": "daily", "time": "09:07", "every_hours": 3, "weekday": "MON"},
    "send": True,
    "image_understanding": False,
    "max_images": 8,
}

WEEKDAYS = [("MON", "周一"), ("TUE", "周二"), ("WED", "周三"), ("THU", "周四"),
            ("FRI", "周五"), ("SAT", "周六"), ("SUN", "周日")]

# 朴素设计语言：暖白底、细灰边、单一暖橙点缀
C_BG = "#FAF9F7"
C_CARD = "#FFFFFF"
C_BORDER = "#E7E4DF"
C_TEXT = "#26251F"
C_SUB = "#8A877F"
C_ACCENT = "#C96A45"
C_ACCENT_HOVER = "#B55A37"
FONT = "Microsoft YaHei UI"


def load_config():
    if CONFIG_PATH.exists():
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        out = dict(DEFAULT_CONFIG)
        out.update(cfg)
        out["range"] = {**DEFAULT_CONFIG["range"], **cfg.get("range", {})}
        out["schedule"] = {**DEFAULT_CONFIG["schedule"], **cfg.get("schedule", {})}
        return out
    return json.loads(json.dumps(DEFAULT_CONFIG))


def save_config(cfg):
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def schtasks_register(schedule: dict):
    freq = schedule["freq"]
    if freq == "none":
        return False, "未启用定时（仅手动运行）"
    time_str = schedule.get("time", "09:07")
    tr = backend_cmd_str()
    cmd = ["schtasks", "/create", "/tn", TASK_NAME, "/tr", tr, "/f"]
    if freq == "daily":
        cmd += ["/sc", "daily", "/st", time_str]
    elif freq == "hourly":
        cmd += ["/sc", "hourly", "/mo", str(max(1, int(schedule.get("every_hours", 3))))]
    elif freq == "weekly":
        cmd += ["/sc", "weekly", "/d", schedule.get("weekday", "MON"), "/st", time_str]
    else:
        return False, f"未知频率: {freq}"
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          encoding="gbk", errors="replace")
    return proc.returncode == 0, (proc.stdout + proc.stderr).strip()


def schtasks_delete():
    proc = subprocess.run(["schtasks", "/delete", "/tn", TASK_NAME, "/f"],
                          capture_output=True, text=True, encoding="gbk", errors="replace")
    return proc.returncode == 0, (proc.stdout + proc.stderr).strip()


def schtasks_query():
    proc = subprocess.run(["schtasks", "/query", "/tn", TASK_NAME, "/fo", "list"],
                          capture_output=True, text=True, encoding="gbk", errors="replace")
    return proc.stdout if proc.returncode == 0 else None


class Card(ctk.CTkFrame):
    def __init__(self, master, title, subtitle=""):
        super().__init__(master, fg_color=C_CARD, corner_radius=10,
                         border_width=1, border_color=C_BORDER)
        ctk.CTkLabel(self, text=title, font=(FONT, 14, "bold"),
                     text_color=C_TEXT).pack(anchor="w", padx=16, pady=(12, 0))
        if subtitle:
            ctk.CTkLabel(self, text=subtitle, font=(FONT, 11),
                         text_color=C_SUB).pack(anchor="w", padx=16, pady=(2, 0))
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="x", padx=12, pady=(4, 12))


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("light")
        self.title("微信群日报")
        self.geometry("640x760")
        self.configure(fg_color=C_BG)
        self.cfg = load_config()
        self.log_queue = queue.Queue()
        self.running = False
        self.group_rows = []

        self._build()
        self._load_into_ui()
        self.after(200, self._drain_log)

    # ---------------- UI ----------------
    def _build(self):
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=20, pady=(18, 6))
        ctk.CTkLabel(head, text="微信群日报", font=(FONT, 20, "bold"),
                     text_color=C_TEXT).pack(side="left")
        self.status = ctk.CTkLabel(head, text="", font=(FONT, 11),
                                   text_color=C_SUB)
        self.status.pack(side="right")

        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True, padx=12, pady=6)

        self._build_groups_card()
        self._build_range_card()
        self._build_schedule_card()
        self._build_options_card()
        self._build_actions()
        self._build_log_card()

    def _build_groups_card(self):
        card = Card(self.scroll, "要总结的群", "名称需与微信里显示的完全一致")
        card.pack(fill="x", pady=6)
        self.groups_frame = ctk.CTkFrame(card.body, fg_color="transparent")
        self.groups_frame.pack(fill="x")

        row = ctk.CTkFrame(card.body, fg_color="transparent")
        row.pack(fill="x", pady=(6, 0))
        self.group_entry = ctk.CTkEntry(row, placeholder_text="输入群名…",
                                        font=(FONT, 12), height=32)
        self.group_entry.pack(side="left", fill="x", expand=True, padx=(2, 6))
        ctk.CTkButton(row, text="添加", width=64, height=32, fg_color=C_ACCENT,
                      hover_color=C_ACCENT_HOVER, font=(FONT, 12),
                      command=self._add_group).pack(side="left")
        ctk.CTkButton(card.body, text="从微信读取最近会话", height=28,
                      fg_color="transparent", border_width=1, border_color=C_BORDER,
                      text_color=C_TEXT, font=(FONT, 11),
                      command=self._load_sessions).pack(anchor="w", padx=2, pady=(6, 0))

        self.session_menu = ctk.CTkOptionMenu(
            card.body, values=["（先点上方按钮读取）"], height=28,
            fg_color=C_CARD, button_color=C_BORDER, button_hover_color=C_SUB,
            text_color=C_TEXT, font=(FONT, 11),
            command=self._pick_session)
        self.session_menu.pack(fill="x", padx=2, pady=(4, 2))

    def _build_range_card(self):
        card = Card(self.scroll, "每次总结的时间范围")
        card.pack(fill="x", pady=6)
        self.range_mode = ctk.StringVar(value="yesterday")
        seg = ctk.CTkSegmentedButton(
            card.body, values=["昨天一整天", "今天到现在", "最近N小时", "最近N天"],
            variable=self.range_mode,
            dynamic_resizing=True, font=(FONT, 12),
            fg_color=C_BORDER, selected_color=C_ACCENT,
            selected_hover_color=C_ACCENT_HOVER, unselected_color=C_CARD,
            text_color=C_TEXT)
        # segmented 用显示值做 variable，映射到 mode
        self.range_seg = seg
        seg.pack(anchor="w", padx=2, pady=(4, 0))
        row = ctk.CTkFrame(card.body, fg_color="transparent")
        row.pack(anchor="w", pady=(6, 0))
        ctk.CTkLabel(row, text="N =", font=(FONT, 12), text_color=C_SUB).pack(side="left")
        self.range_hours = ctk.CTkEntry(row, width=56, height=28, font=(FONT, 12))
        self.range_hours.pack(side="left", padx=(4, 2))
        ctk.CTkLabel(row, text="小时 /", font=(FONT, 12), text_color=C_SUB).pack(side="left")
        self.range_days = ctk.CTkEntry(row, width=56, height=28, font=(FONT, 12))
        self.range_days.pack(side="left", padx=(4, 2))
        ctk.CTkLabel(row, text="天（范围越长采集越慢）", font=(FONT, 12),
                     text_color=C_SUB).pack(side="left")

    def _build_schedule_card(self):
        card = Card(self.scroll, "运行频率", "不定时则只在你手动点「立即运行」时执行")
        card.pack(fill="x", pady=6)
        self.freq_seg = ctk.CTkSegmentedButton(
            card.body, values=["不定时", "每天", "每隔N小时", "每周"],
            font=(FONT, 12), fg_color=C_BORDER, selected_color=C_ACCENT,
            selected_hover_color=C_ACCENT_HOVER, unselected_color=C_CARD,
            text_color=C_TEXT)
        self.freq_seg.pack(anchor="w", padx=2, pady=(4, 0))
        row = ctk.CTkFrame(card.body, fg_color="transparent")
        row.pack(anchor="w", pady=(6, 0))
        ctk.CTkLabel(row, text="时间", font=(FONT, 12), text_color=C_SUB).pack(side="left")
        self.time_entry = ctk.CTkEntry(row, width=70, height=28, font=(FONT, 12))
        self.time_entry.pack(side="left", padx=(4, 8))
        ctk.CTkLabel(row, text="每隔", font=(FONT, 12), text_color=C_SUB).pack(side="left")
        self.every_hours = ctk.CTkEntry(row, width=50, height=28, font=(FONT, 12))
        self.every_hours.pack(side="left", padx=(4, 2))
        ctk.CTkLabel(row, text="小时", font=(FONT, 12), text_color=C_SUB).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(row, text="周几", font=(FONT, 12), text_color=C_SUB).pack(side="left")
        self.weekday = ctk.CTkOptionMenu(
            row, values=[f"{k} {v}" for k, v in WEEKDAYS], width=100, height=28,
            fg_color=C_CARD, button_color=C_BORDER, button_hover_color=C_SUB,
            text_color=C_TEXT, font=(FONT, 11))
        self.weekday.pack(side="left", padx=4)

    def _build_options_card(self):
        card = Card(self.scroll, "选项")
        card.pack(fill="x", pady=6)
        self.send_var = ctk.BooleanVar(value=True)
        ctk.CTkSwitch(card.body, text="运行后把摘要发到「文件传输助手」",
                      variable=self.send_var, font=(FONT, 12), text_color=C_TEXT,
                      progress_color=C_ACCENT).pack(anchor="w", padx=2, pady=3)
        self.image_var = ctk.BooleanVar(value=False)
        ctk.CTkSwitch(card.body, text="理解图片内容（每张开图截图，较慢）",
                      variable=self.image_var, font=(FONT, 12), text_color=C_TEXT,
                      progress_color=C_ACCENT).pack(anchor="w", padx=2, pady=3)

    def _build_actions(self):
        bar = ctk.CTkFrame(self.scroll, fg_color="transparent")
        bar.pack(fill="x", pady=(8, 4))
        ctk.CTkButton(bar, text="保存设置", height=34, fg_color=C_ACCENT,
                      hover_color=C_ACCENT_HOVER, font=(FONT, 13),
                      command=self._save).pack(side="left", padx=(4, 6))
        ctk.CTkButton(bar, text="保存并注册计划任务", height=34,
                      fg_color="transparent", border_width=1, border_color=C_ACCENT,
                      text_color=C_ACCENT, hover_color="#F5E9E3", font=(FONT, 13),
                      command=self._save_and_register).pack(side="left", padx=6)
        ctk.CTkButton(bar, text="立即运行一次", height=34,
                      fg_color="transparent", border_width=1, border_color=C_BORDER,
                      text_color=C_TEXT, font=(FONT, 13),
                      command=self._run_now).pack(side="left", padx=6)
        ctk.CTkButton(bar, text="打开输出目录", height=34,
                      fg_color="transparent", border_width=1, border_color=C_BORDER,
                      text_color=C_TEXT, font=(FONT, 13),
                      command=lambda: subprocess.Popen(["explorer", str(BASE / "output")])
                      ).pack(side="left", padx=6)

    def _build_log_card(self):
        card = Card(self.scroll, "运行日志")
        card.pack(fill="both", expand=True, pady=6)
        self.log = ctk.CTkTextbox(card.body, height=160, font=("Consolas", 10),
                                  fg_color="#FBFAF8", text_color=C_TEXT,
                                  border_width=1, border_color=C_BORDER)
        self.log.pack(fill="both", expand=True, padx=2, pady=2)
        self.log.configure(state="disabled")

    # ---------------- 配置 ----------------
    RANGE_TO_MODE = {"昨天一整天": "yesterday", "今天到现在": "today",
                     "最近N小时": "last_hours", "最近N天": "last_days"}
    FREQ_TO_MODE = {"不定时": "none", "每天": "daily",
                    "每隔N小时": "hourly", "每周": "weekly"}

    def _collect_ui(self):
        freq = self.FREQ_TO_MODE[self.freq_seg.get()]
        if freq in ("daily", "weekly"):
            try:
                hh, mm = self.time_entry.get().strip().split(":")
                assert 0 <= int(hh) <= 23 and 0 <= int(mm) <= 59
            except Exception:
                raise ValueError("运行时间格式应为 HH:MM，例如 09:07")
        groups = [r["name"] for r in self.group_rows]
        if not groups:
            raise ValueError("至少添加一个群")
        return {
            "groups": groups,
            "range": {"mode": self.RANGE_TO_MODE[self.range_seg.get()],
                      "hours": int(self.range_hours.get() or 24),
                      "days": int(self.range_days.get() or 7)},
            "schedule": {"freq": freq,
                         "time": self.time_entry.get().strip() or "09:07",
                         "every_hours": int(self.every_hours.get() or 3),
                         "weekday": (self.weekday.get() or "MON").split()[0]},
            "send": self.send_var.get(),
            "image_understanding": self.image_var.get(),
            "max_images": 8,
        }

    def _load_into_ui(self):
        for name in self.cfg["groups"]:
            self._append_group_row(name)
        self.range_seg.set(next(k for k, v in self.RANGE_TO_MODE.items()
                                if v == self.cfg["range"]["mode"]))
        self.range_hours.insert(0, str(self.cfg["range"]["hours"]))
        self.range_days.insert(0, str(self.cfg["range"].get("days", 7)))
        self.freq_seg.set(next(k for k, v in self.FREQ_TO_MODE.items()
                               if v == self.cfg["schedule"]["freq"]))
        self.time_entry.insert(0, self.cfg["schedule"]["time"])
        self.every_hours.insert(0, str(self.cfg["schedule"]["every_hours"]))
        wd = self.cfg["schedule"]["weekday"]
        self.weekday.set(next((f"{k} {v}" for k, v in WEEKDAYS if k == wd), "MON 周一"))
        self.send_var.set(self.cfg.get("send", True))
        self.image_var.set(self.cfg.get("image_understanding", False))
        self._refresh_status()

    def _refresh_status(self):
        self.status.configure(
            text="计划任务：已注册" if schtasks_query() else "计划任务：未注册")

    # ---------------- 群列表 ----------------
    def _append_group_row(self, name):
        row = ctk.CTkFrame(self.groups_frame, fg_color="#F5F3F0", corner_radius=6)
        row.pack(fill="x", pady=2, padx=2)
        ctk.CTkLabel(row, text=name, font=(FONT, 12),
                     text_color=C_TEXT).pack(side="left", padx=10, pady=5)
        entry = {"name": name, "widget": row}
        ctk.CTkButton(row, text="×", width=28, height=24, fg_color="transparent",
                      text_color=C_SUB, hover_color=C_BORDER, font=(FONT, 13),
                      command=lambda e=entry: self._remove_group_row(e)).pack(side="right", padx=6)
        self.group_rows.append(entry)

    def _remove_group_row(self, entry):
        entry["widget"].destroy()
        self.group_rows.remove(entry)

    def _add_group(self):
        name = self.group_entry.get().strip()
        if name and name not in [r["name"] for r in self.group_rows]:
            self._append_group_row(name)
        self.group_entry.delete(0, "end")

    def _load_sessions(self):
        self._append_log("正在读取微信会话列表…\n")
        def work():
            try:
                from collect_chat import find_wechat, list_recent_sessions
                titles = list_recent_sessions(find_wechat())
                self.log_queue.put(("sessions", titles))
            except Exception as e:
                self.log_queue.put(("log", f"读取失败: {e}\n"))
        threading.Thread(target=work, daemon=True).start()

    def _pick_session(self, name):
        if name and not name.startswith("（"):
            self.group_entry.delete(0, "end")
            self.group_entry.insert(0, name)

    # ---------------- 动作 ----------------
    def _save(self):
        try:
            self.cfg = self._collect_ui()
        except ValueError as e:
            self._append_log(f"设置有误: {e}\n")
            return
        save_config(self.cfg)
        self.status.configure(text="设置已保存")

    def _save_and_register(self):
        self._save()
        if self.cfg["schedule"]["freq"] == "none":
            schtasks_delete()
            self._append_log("已选择不定时，计划任务已移除（如原本存在）\n")
            self.status.configure(text="已保存；不定时，仅手动运行")
            return
        ok, out = schtasks_register(self.cfg["schedule"])
        self._append_log(out + "\n")
        self._refresh_status()

    def _run_now(self):
        if self.running:
            self._append_log("正在运行中，请等待完成\n")
            return
        self._save()
        self.running = True
        self._append_log(f"=== 手动运行 {dt.datetime.now():%H:%M:%S} ===\n")
        def work():
            proc = subprocess.Popen(
                backend_cmd(),
                cwd=str(BASE), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace")
            for line in proc.stdout:
                self.log_queue.put(("log", line))
            self.log_queue.put(("log", f"=== 结束，退出码 {proc.wait()} ===\n"))
            self.log_queue.put(("done", None))
        threading.Thread(target=work, daemon=True).start()

    # ---------------- 日志 ----------------
    def _append_log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _drain_log(self):
        try:
            while True:
                kind, payload = self.log_queue.get_nowait()
                if kind == "log":
                    self._append_log(payload)
                elif kind == "sessions":
                    self.session_menu.configure(values=payload or ["（没有读到会话）"])
                    self._append_log(f"读到 {len(payload)} 个会话\n")
                elif kind == "done":
                    self.running = False
        except queue.Empty:
            pass
        self.after(200, self._drain_log)


if __name__ == "__main__":
    App().mainloop()
