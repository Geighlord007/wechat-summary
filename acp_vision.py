# -*- coding: utf-8 -*-
"""通过 kimi acp（Agent Client Protocol）调用本机 Kimi Code 的视觉能力描述图片。

kimi acp 是 CLI 官方的子进程协议，initialize 即声明支持 image 内容块。
最小客户端：initialize -> initialized -> session/new -> session/prompt(图片+文字)。
agent->client 的反向请求必须应答，否则对方会一直等（权限请求一律拒绝——
图片描述不需要任何工具）。"""
import base64
import json
import queue
import subprocess
import threading
import time
from pathlib import Path

from paths import find_kimi

CAPTION_PROMPT = (
    "这是微信群聊里一张图片消息的局部截图。请用一句中文描述图中图片的关键内容"
    "（是战绩/数据截图就说清数据和结论，是照片就说清场景主体，是表情包就说清含义）。"
    "如果画面主要是空白或完全无法辨认，直接回答「无法辨认」。不超过 40 字，不要客套话。"
)


class ACPError(RuntimeError):
    pass


class KimiACP:
    """最小 ACP 客户端：NDJSON over stdio。"""

    def __init__(self, cwd: str):
        self.proc = subprocess.Popen(
            [find_kimi(), "acp"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            cwd=cwd, encoding="utf-8", errors="replace", bufsize=1,
        )
        self._id = 0
        self._q = queue.Queue()
        threading.Thread(
            target=lambda: [self._q.put(l) for l in self.proc.stdout],
            daemon=True,
        ).start()
        self.session_id = None

    def _send(self, obj: dict):
        self.proc.stdin.write(json.dumps(obj, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()

    def request(self, method: str, params: dict, timeout: int = 240):
        self._id += 1
        rid = self._id
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        notifications = []
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                line = self._q.get(timeout=max(1, deadline - time.time()))
            except queue.Empty:
                break
            msg = json.loads(line)
            if msg.get("id") == rid and ("result" in msg or "error" in msg):
                if "error" in msg:
                    raise ACPError(f"{method} 失败: {msg['error']}")
                return msg.get("result", {}), notifications
            if "method" in msg and "id" in msg:
                # agent 发来的反向请求：权限一律拒绝（描述图片不需要工具）
                if msg["method"] == "session/request_permission":
                    self._send({"jsonrpc": "2.0", "id": msg["id"],
                                "result": {"outcome": {"outcome": "rejected"}}})
                else:
                    self._send({"jsonrpc": "2.0", "id": msg["id"],
                                "error": {"code": -32601, "message": "not implemented"}})
            else:
                notifications.append(msg)
        raise ACPError(f"{method} 超时（{timeout}s）")

    def start_session(self):
        self.request("initialize", {
            "protocolVersion": 1,
            "clientCapabilities": {"fs": {"readTextFile": False, "writeTextFile": False}},
            "clientInfo": {"name": "wxsum", "version": "1.0"},
        }, timeout=30)
        self._send({"jsonrpc": "2.0", "method": "initialized", "params": {}})
        result, _ = self.request("session/new",
                                 {"cwd": ".", "mcpServers": []}, timeout=60)
        self.session_id = result["sessionId"]
        return self.session_id

    def caption_image(self, session_id: str, png_path: str) -> str:
        b64 = base64.b64encode(Path(png_path).read_bytes()).decode("ascii")
        _, notifications = self.request("session/prompt", {
            "sessionId": session_id,
            "prompt": [
                {"type": "image", "data": b64, "mimeType": "image/png"},
                {"type": "text", "text": CAPTION_PROMPT},
            ],
        })
        chunks = []
        for msg in notifications:
            if msg.get("method") == "session/update":
                upd = msg.get("params", {}).get("update", {})
                if upd.get("sessionUpdate") == "agent_message_chunk":
                    content = upd.get("content", {})
                    if content.get("type") == "text":
                        chunks.append(content.get("text", ""))
        return "".join(chunks).strip()

    def close(self):
        try:
            self.proc.terminate()
        except Exception:
            pass


if __name__ == "__main__":
    import sys
    client = KimiACP(cwd=str(Path(__file__).parent))
    try:
        sid = client.start_session()
        print(client.caption_image(sid, sys.argv[1]))
    finally:
        client.close()
