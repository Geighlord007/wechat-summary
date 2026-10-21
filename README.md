# 微信群日报（wechat-summary）

自动采集指定微信群的消息，生成中文摘要，发送到微信「文件传输助手」。
带图形界面，可视化选择群、运行频率、每次总结的时间范围。

## 安装

需要 Windows、微信 PC 版 4.x、已登录的 Kimi Code CLI（`kimi` 命令可用；
安装位置不在 PATH 时可设置环境变量 `KIMI_BIN` 指向 kimi 可执行文件）。

```bat
git clone <本仓库地址>
cd wechat-summary
py -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

配置文件 `config.json` 不入库：首次在界面里保存设置会自动生成，
也可参照 `config.example.json` 手写一份。

## 启动界面

双击 `微信群日报.bat`（或运行 `.venv\Scripts\pythonw.exe gui.py`）。

界面里可以：

- **要总结的群**：手动输入群名添加；或点「读取微信会话列表」后双击候选填入
- **每次总结的时间范围**：昨天一整天 / 今天截至现在 / 最近 N 小时 / 最近 N 天
  （范围越长采集越慢：一天约一分钟，一周约几分钟；超长记录摘要会自动分块再合并）
- **运行频率**：不定时（仅手动运行）/ 每天 HH:MM / 每隔 N 小时 / 每周某天 HH:MM
- **保存并注册计划任务**：把当前设置写入 `config.json` 并按频率注册 Windows 计划任务；
  选「不定时」时会移除已注册的任务，只保留手动运行
- **立即运行一次**：手动触发完整流程，日志在「运行日志」页查看
- **删除计划任务** / **打开输出目录**

## 原理

只读 UI Automation（Windows 无障碍接口）操作本机微信 4.x PC 客户端的界面：
不碰协议、不注入进程、不读数据库。摘要由本机 Kimi Code CLI（`kimi -p` 非交互模式）生成，
图片理解通过 `kimi acp`（Agent Client Protocol）子进程协议调用。

## 使用前提

- 电脑开机、未锁屏、微信 PC 版已登录
- 脚本运行时请勿操作微信（会短暂操作窗口，几十秒到两分钟）

## 命令行用法（调试用）

```bat
.venv\Scripts\python.exe run_daily.py                    :: 按 config.json 运行
.venv\Scripts\python.exe run_daily.py --no-send          :: 只存盘，不发送
.venv\Scripts\python.exe run_daily.py --group "群名" --range last_hours --hours 6
.venv\Scripts\python.exe collect_chat.py --group "群名" --day yesterday
```

输出在 `output\` 目录：原始记录 `群名_时间戳.txt` / `群名_时间戳.json`，
摘要 `群名_时间戳_summary.txt`，完整运行日志在 `logs\`。

## 文件说明

- `gui.py` — 图形界面（customtkinter）
- `run_daily.py` — 配置驱动的编排：逐群采集、摘要、合并发送到文件传输助手
- `collect_chat.py` — 采集器：搜索进群、滚轮翻页、序列对齐去重、按时间段过滤
- `summarize.py` — 调 `kimi -p` 生成摘要（复用本机 Kimi Code 凭据）
- `acp_vision.py` — `kimi acp` 最小客户端，图片消息的视觉理解
- `send_wechat.py` — 发送到「文件传输助手」（唯一发送对象），发送后验证
- `clipboard_util.py` — 剪贴板工具（发送后恢复原剪贴板）
- `paths.py` — 路径与运行方式（源码 / PyInstaller 打包）、定位 kimi CLI
- `config.json` — 群列表 / 时间范围 / 频率 / 是否发送（本机生成，不入库）
- `config.example.json` — 配置示例
- `微信群日报.bat` — GUI 启动器
- `register_task.bat` — 注册每天 09:07 计划任务（命令行方式）
- `probe_uia.py` / `debug_search.py` / `debug_pop.py` / `debug_open.py` /
  `debug_sender.py` / `debug_acp.py` — 调试探针
- `微信群日报.spec` / `wxsum-run.spec` — PyInstaller 打包配置
  （`pyinstaller 微信群日报.spec` 生成带界面的 exe，`pyinstaller wxsum-run.spec` 生成后端）

## 已知限制

- 发送人昵称在 4.x 消息列表中不暴露，摘要里没有"谁说的"
- 图片/语音/表情只有占位标记，没有内容（开启「理解图片内容」后图片会带一句话描述）
- 公众号/链接卡片只能读到标题，语音读不到内容
- 锁屏后 UIA 读不到窗口，定时任务会失败退出（不会发出错误内容）
