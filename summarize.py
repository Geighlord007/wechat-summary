# -*- coding: utf-8 -*-
"""用本机 Kimi Code CLI（kimi -p 非交互模式）为群消息记录生成摘要。
记录较长时自动分块：先逐块摘要，再合并成最终摘要。
输出为纯文本（微信不渲染 Markdown）。"""
import re
import subprocess
import sys
from pathlib import Path

from paths import find_kimi

CHUNK_CHARS = 12000   # 每块消息记录的大致长度上限
MERGE_CHARS = 60000   # 超过则递归分块合并

STYLE_RULES = """硬性要求：
1. 纯文本！禁止使用任何 Markdown 语法：不要 ** 加粗、不要 ## 标题、不要 - 列表符号；
2. 按时间段分小节，每节开头用【凌晨】【上午】【下午】【晚间】这类方括号标签，单独占一行；
3. 节内用「·」开头逐条写要点，每条一行；
4. 总共 12 行以内。"""

PROMPT_TMPL = """你是一个微信群聊摘要助手。下面是一个微信群一段时间的消息记录（[时间] 内容，无发送人信息；「图片」「动画表情」是占位标记）。
请输出中文摘要，归纳讨论话题和结论，合并闲聊噪声；有约局/组队类消息时明确写出时间、人数缺口、平台链接。
消息太少或没有实质内容时，直接输出一行"没什么实质讨论"。
{style}

群名：{group}
时间范围：{day}
消息记录：
{transcript}
"""

PART_TMPL = """你是一个微信群聊摘要助手。下面是一个大群消息记录的第 {i}/{n} 部分。
把这部分的事实性内容压缩成要点：什么时间大致聊了什么话题、有哪些约定/链接/结论。
保留关键信息，去掉语气词和重复闲聊，不要评论。
硬性要求：纯文本，禁止 Markdown（不要 **、##、- 列表符号），用「·」开头逐条写，每条一行。

群名：{group}
消息记录（第 {i}/{n} 部分）：
{transcript}
"""

MERGE_TMPL = """你是一个微信群聊摘要助手。下面是按时间顺序分段整理的一个微信群（{group}，{day}）的要点。
请合并成一份简洁的中文摘要，合并重复内容；有约局/组队/约定类信息时明确写出时间、人数、平台。
没有实质内容就直接输出一行"没什么实质讨论"。
{style}

分段要点：
{transcript}
"""


def strip_markdown(text: str) -> str:
    """兜底去掉模型没听指令时残留的 Markdown 符号。"""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"(?<!\w)\*(.+?)\*(?!\w)", r"\1", text)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.M)
    text = re.sub(r"^[-*•]\s*", "· ", text, flags=re.M)
    text = re.sub(r"`+", "", text)
    return text.strip()


def _kimi(prompt: str, timeout: int = 600) -> str:
    proc = subprocess.run(
        [find_kimi(), "-p", prompt, "--output-format", "text"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"kimi -p 失败 (exit {proc.returncode}): {proc.stderr[:500]}")
    return strip_markdown(proc.stdout)


def _split_lines(text: str, max_chars: int):
    """按行切块，每块不超过 max_chars。"""
    chunks, cur, size = [], [], 0
    for line in text.splitlines():
        if size + len(line) > max_chars and cur:
            chunks.append("\n".join(cur))
            cur, size = [], 0
        cur.append(line)
        size += len(line) + 1
    if cur:
        chunks.append("\n".join(cur))
    return chunks


def summarize(transcript: str, group: str, day: str) -> str:
    if len(transcript) <= CHUNK_CHARS:
        return _kimi(PROMPT_TMPL.format(style=STYLE_RULES, group=group, day=day,
                                        transcript=transcript))
    # 长记录：分块 -> 逐块要点 -> 合并（仍过长则递归合并）
    chunks = _split_lines(transcript, CHUNK_CHARS)
    parts = []
    for i, chunk in enumerate(chunks, 1):
        parts.append(_kimi(PART_TMPL.format(i=i, n=len(chunks),
                                            group=group, transcript=chunk)))
    merged = "\n\n".join(parts)
    while len(merged) > MERGE_CHARS:
        sub = _split_lines(merged, MERGE_CHARS // 2)
        merged = "\n\n".join(
            _kimi(MERGE_TMPL.format(style=STYLE_RULES, group=group, day=day,
                                    transcript=s))
            for s in sub
        )
    return _kimi(MERGE_TMPL.format(style=STYLE_RULES, group=group, day=day,
                                   transcript=merged))


if __name__ == "__main__":
    src = Path(sys.argv[1])
    group = sys.argv[2] if len(sys.argv) > 2 else "群聊"
    day = sys.argv[3] if len(sys.argv) > 3 else ""
    text = src.read_text(encoding="utf-8")
    print(summarize(text, group, day))
