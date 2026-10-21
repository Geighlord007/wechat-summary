# -*- coding: utf-8 -*-
"""调试 ACP 完整流程：initialize -> initialized -> session/new -> session/prompt(图片)。
打印每一步的原始消息，找出挂起点。"""
import base64
import json
import queue
import subprocess
import threading

from paths import find_kimi

KIMI = find_kimi()

q = queue.Queue()
proc = subprocess.Popen(
    [KIMI, "acp"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    encoding="utf-8", errors="replace", bufsize=1,
)
threading.Thread(target=lambda: [q.put(l) for l in proc.stdout], daemon=True).start()


def send(obj):
    print("SEND:", obj.get("method") or f"resp#{obj.get('id')}", flush=True)
    proc.stdin.write(json.dumps(obj, ensure_ascii=False) + "\n")
    proc.stdin.flush()


def wait_response(rid, timeout=60):
    """等 id==rid 的响应；期间的 agent->client 请求自动应答，通知打印。"""
    import time
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            line = q.get(timeout=max(1, deadline - time.time()))
        except queue.Empty:
            break
        msg = json.loads(line)
        if msg.get("id") == rid and ("result" in msg or "error" in msg):
            print(f"RECV response#{rid}:", json.dumps(msg, ensure_ascii=False)[:300], flush=True)
            return msg
        if "method" in msg and "id" in msg:
            # agent 发来的请求：权限一律拒绝，其余返回空
            if msg["method"] == "session/request_permission":
                send({"jsonrpc": "2.0", "id": msg["id"],
                      "result": {"outcome": {"outcome": "rejected"}}})
            else:
                send({"jsonrpc": "2.0", "id": msg["id"],
                      "error": {"code": -32601, "message": "not implemented"}})
            print("AGENT-REQ:", msg["method"], flush=True)
        else:
            upd = msg.get("params", {}).get("update", {})
            print("NOTIFY:", upd.get("sessionUpdate", msg.get("method")), flush=True)
    return None


send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
    "protocolVersion": 1,
    "clientCapabilities": {"fs": {"readTextFile": False, "writeTextFile": False}},
    "clientInfo": {"name": "wxsum-debug", "version": "1.0"}}})
wait_response(1, 20)

send({"jsonrpc": "2.0", "method": "initialized", "params": {}})

send({"jsonrpc": "2.0", "id": 2, "method": "session/new",
      "params": {"cwd": ".", "mcpServers": []}})
resp = wait_response(2, 30)
sid = resp["result"]["sessionId"] if resp and "result" in resp else None
print("sessionId:", sid, flush=True)

if sid:
    b64 = base64.b64encode(open("test_screen.png", "rb").read()).decode()
    send({"jsonrpc": "2.0", "id": 3, "method": "session/prompt", "params": {
        "sessionId": sid,
        "prompt": [
            {"type": "image", "data": b64, "mimeType": "image/png"},
            {"type": "text", "text": "用一句中文描述这张图片，不超过30字"},
        ]}})
    wait_response(3, 180)

proc.terminate()
print("DONE", flush=True)
