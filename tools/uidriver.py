# -*- coding: utf-8 -*-
"""实机验证用的浏览器驱动（零依赖：手写 WebSocket + Chrome DevTools Protocol）。

抽出来是因为现在有两个验证脚本要用它：
  · `tools/verify.py ui`       候选值下拉
  · `tools/verify.py presets`  我自己的预设

**不装 Playwright / Selenium** —— 这个项目"零第三方依赖"的约束在验证工具上
一样成立。Edge / Chrome 本身就能开调试端口，用 stdlib 的 socket 讲 WebSocket
足够了（只用到文本帧）。

用法：
    from uidriver import find_browser, launch, connect, wait_page
    proc = launch(9222)                 # 起一个 headless 浏览器
    c = connect(9222)                   # 连上，拿到 CDP 客户端
    wait_page(c, "http://127.0.0.1:8765/advanced.html")
    c.js("document.title")
    c.click(100, 200)
    proc.terminate()
"""
import base64
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

BROWSER_CANDIDATES = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
)


def find_browser():
    for c in BROWSER_CANDIDATES:
        if os.path.exists(c):
            return c
    sys.exit("没找到 Edge / Chrome —— 这个验证需要本机有一个 Chromium 内核浏览器")


class CDP:
    """极简 WebSocket 客户端（只够用 CDP：文本帧、无分片、服务端帧不掩码）。"""

    def __init__(self, ws_url):
        u = urlparse(ws_url)
        s = socket.create_connection((u.hostname, u.port), timeout=30)
        key = base64.b64encode(os.urandom(16)).decode()
        s.sendall((f"GET {u.path} HTTP/1.1\r\nHost: {u.hostname}:{u.port}\r\n"
                   "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                   f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
                   ).encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += s.recv(4096)
        assert b"101" in buf.split(b"\r\n")[0], buf[:200]
        self.sock, self.buf, self.n = s, buf.split(b"\r\n\r\n", 1)[1], 0

    def _frame(self, payload):
        data, mask = payload.encode(), os.urandom(4)
        n = len(data)
        hdr = b"\x81"
        if n < 126:
            hdr += bytes([0x80 | n])
        elif n < 65536:
            hdr += bytes([0x80 | 126]) + n.to_bytes(2, "big")
        else:
            hdr += bytes([0x80 | 127]) + n.to_bytes(8, "big")
        self.sock.sendall(hdr + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def _exact(self, n):
        out = self.buf
        while len(out) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise EOFError
            out += chunk
        self.buf = out[n:]
        return out[:n]

    def _read(self):
        _, b1 = self._exact(2)
        ln = b1 & 0x7F
        if ln == 126:
            ln = int.from_bytes(self._exact(2), "big")
        elif ln == 127:
            ln = int.from_bytes(self._exact(8), "big")
        return self._exact(ln).decode("utf-8", "replace")

    def call(self, method, **params):
        self.n += 1
        mid = self.n
        self._frame(json.dumps({"id": mid, "method": method, "params": params}))
        while True:
            msg = json.loads(self._read())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})

    def js(self, expr):
        """在页面里求值，返回可 JSON 化的结果。页面里抛异常会在这里抛出来。"""
        r = self.call("Runtime.evaluate", expression=expr, returnByValue=True,
                      awaitPromise=True)
        if r.get("exceptionDetails"):
            raise RuntimeError(str(r["exceptionDetails"])[:400])
        return r.get("result", {}).get("value")

    def click(self, x, y):
        for t in ("mousePressed", "mouseReleased"):
            self.call("Input.dispatchMouseEvent", type=t, x=x, y=y,
                      button="left", clickCount=1)

    def key(self, name, vk):
        self.call("Input.dispatchKeyEvent", type="rawKeyDown", key=name, code=name,
                  windowsVirtualKeyCode=vk, nativeVirtualKeyCode=vk)
        self.call("Input.dispatchKeyEvent", type="keyUp", key=name, code=name,
                  windowsVirtualKeyCode=vk, nativeVirtualKeyCode=vk)

    def shot(self, path):
        r = self.call("Page.captureScreenshot", format="png")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(base64.b64decode(r["data"]))
        return path


def launch(port, window="1440,900", headless=True):
    """起一个浏览器进程，调试端口开在 `port`。返回 Popen（用完记得 terminate）。"""
    profile = tempfile.mkdtemp(prefix="dsh-cdp-")
    args = [find_browser()]
    if headless:
        args.append("--headless=new")
    args += [f"--remote-debugging-port={port}", f"--user-data-dir={profile}",
             "--no-first-run", "--no-default-browser-check",
             f"--window-size={window}", "--hide-scrollbars",
             "--force-device-scale-factor=1", "about:blank"]
    return subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def connect(port, timeout_s=30):
    """等浏览器起来并连上第一个 page。"""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/json/list", timeout=1) as f:
                tabs = json.load(f)
            page = next((t for t in tabs if t["type"] == "page"), None)
            if page:
                return CDP(page["webSocketDebuggerUrl"])
        except Exception:
            pass
        time.sleep(0.5)
    sys.exit(f"等不到浏览器调试端口 {port}")


def wait_page(c, url, wait_s=4.0):
    """导航过去并等一会儿（页面 boot() 要读 options / catalog）。"""
    c.call("Page.enable")
    c.call("Runtime.enable")
    c.call("Page.navigate", url=url)
    time.sleep(wait_s)
    return c


def stop(proc):
    if proc is None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except Exception:
        proc.kill()


class Checker:
    """把 ✅/❌ 那套收集起来，最后统一判定（至少有一个 ❌ 就非零退出）。"""

    def __init__(self):
        self.fails = []

    def __call__(self, label, cond, detail=""):
        print(("  ✅ " if cond else "  ❌ ") + label + (f"  {detail}" if detail else ""))
        if not cond:
            self.fails.append(label)
        return bool(cond)

    def done(self):
        print()
        if self.fails:
            print(f"❌ {len(self.fails)} 项没过：")
            for f in self.fails:
                print("   - " + f)
            return 1
        print("✅ 全部通过")
        return 0
