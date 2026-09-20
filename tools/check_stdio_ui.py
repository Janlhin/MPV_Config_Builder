# -*- coding: utf-8 -*-
"""W-4 第③步实机验证：让 9 个页面**真正跑在 stdio 通道上**。

## 为什么需要这个脚本，而不是只写单元测试

第③步的承诺是「9 个页面零改动，只把传输换掉」。单元测试测不出这句话 ——
它只能在真浏览器里、用真后端验证：**页面照样转，而 HTTP 上一条 API 请求都没有**。

## 怎么做到"不开 HTTP 端口"又能在浏览器里验证

浏览器没法直接读进程的管道。所以中间放一个**极小的转发器**（本脚本自带）：

    浏览器 ──fetch──▶ 转发器（HTTP，仅 127.0.0.1）──stdin/stdout──▶ 真后端 --stdio

注入的 `__MPVCB_INVOKE__` 把请求 POST 给转发器，转发器原样转给 stdio 后端。
**注意转发器只转发 `/__bridge__` 这一个路径**，其它 `/api/...` 一律 404 ——
所以"页面上的 API 调用"没有别的路可走，只能走 stdio 通道。
再配合 `fetch` 拦截器记账：任何漏到 HTTP 的 `/api/` 调用都会被记下来并判失败。

## 判据

1. 9 个页面都能加载出真实数据（标题/版本/目标目录），不是白屏或报错；
2. 每个页面至少发了一条请求，且**全部经由 stdio 通道**；
3. `window.fetch` 从没被用去请求 `/api/`（漏一条就说明没换干净）；
4. stdio 后端的 stdout 里每一行都是合法 JSON（第②步那条约束在真实负载下仍成立）。

用法：py -3 tools/check_stdio_ui.py
"""
import http.server
import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from uidriver import Checker, connect, launch, stop, wait_page   # noqa: E402

SHOTS = ROOT / "_shots"
PAGES = [
    ("index.html", "index"), ("basic.html", "basic"), ("advanced.html", "advanced"),
    ("expert.html", "expert"), ("analyze.html", "analyze"), ("keys.html", "keys"),
    ("downloads.html", "downloads"), ("guide.html", "guide"), ("hell.html", "hell"),
]


class StdioBackend:
    """真的 spawn 一个 `server.py --stdio`，按行收发。"""

    def __init__(self):
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        self.proc = subprocess.Popen(
            [sys.executable, "-X", "utf8", str(ROOT / "webui" / "server.py"), "--stdio"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=str(ROOT), env=env)
        self.lock = threading.Lock()
        self.seq = 0
        self.dirty_stdout = []          # stdout 里不是合法 JSON 的行（判据 4）
        self.stderr_lines = []

    def call(self, req):
        """发一条请求，等一条响应。串行 —— 与后端"逐条处理"的设计一致。"""
        with self.lock:
            self.seq += 1
            req = dict(req)
            req["id"] = self.seq
            line = json.dumps(req, ensure_ascii=False)
            try:
                self.proc.stdin.write((line + "\n").encode("utf-8"))
                self.proc.stdin.flush()
            except (BrokenPipeError, ValueError) as e:
                return {"ok": False, "error": f"后端写入失败：{e}"}
            raw = self.proc.stdout.readline()
            if not raw:
                return {"ok": False, "error": "后端没有响应（进程可能已退出）"}
            text = raw.decode("utf-8", "replace").strip()
            try:
                return json.loads(text)
            except ValueError:
                self.dirty_stdout.append(text)
                return {"ok": False, "error": "后端 stdout 出现了非 JSON 行"}

    def drain_stderr(self):
        try:
            while True:
                chunk = self.proc.stderr.readline()
                if not chunk:
                    break
                self.stderr_lines.append(chunk.decode("utf-8", "replace").rstrip())
        except Exception:
            pass

    def close(self):
        for s in (self.proc.stdin, self.proc.stdout, self.proc.stderr):
            try:
                s.close()
            except Exception:
                pass
        try:
            self.proc.wait(timeout=10)
        except Exception:
            self.proc.kill()


def make_bridge(backend):
    """把浏览器发来的请求转给 stdio 后端，并**顺便同源提供静态文件**。

    ⚠ 为什么要连静态文件一起发：如果页面在 A 源、转发器在 B 源，
    注入的 `fetch('/__bridge__')` 就是跨源请求；`Content-Type: application/json`
    还会触发 OPTIONS 预检 —— 那就得给转发器加一整套 CORS 头，
    而**这套头在真实 Electron 里根本不存在**（那边是 file:// + 管道）。
    同源提供之后 CORS 问题自然消失，测试也更接近真场景。

    **只认 `/__bridge__` 这一个 API 路径**，其它 `/api/...` 一律 404 ——
    所以页面上的 API 调用没有别的路可走，只能走 stdio 通道。
    """
    import mimetypes
    static = ROOT / "webui" / "static"

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, obj, code=200):
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_file(self, rel):
            # 只允许静态目录里的文件，挡掉 ../ 穿越
            target = (static / rel).resolve()
            if not str(target).startswith(str(static.resolve())) or not target.is_file():
                self._send({"ok": False, "error": "没有这个文件"}, 404)
                return
            body = target.read_bytes()
            ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype.endswith(("javascript", "json")):
                ctype += "; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?")[0]
            if path in ("/", ""):
                path = "/index.html"
            if path.startswith("/api/"):
                # 故意 404：证明前端的 API 调用没走 HTTP
                self._send({"ok": False, "error": "本测试里 /api/ 一律不通，必须走 stdio"}, 404)
                return
            self._send_file(path.lstrip("/"))

        def do_POST(self):
            if self.path != "/__bridge__":
                self._send({"ok": False, "error": "只有 /__bridge__，别的路径不走这里"}, 404)
                return
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n) if n else b"{}"
            try:
                req = json.loads(raw.decode("utf-8"))
            except ValueError:
                self._send({"ok": False, "error": "转发器收到的不是 JSON"}, 400)
                return
            self._send(backend.call(req))

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


# 页面里注入的东西：把 API 调用改道到转发器，并记账任何漏到 HTTP 的 /api/ 请求。
#
# ⚠ 顺序非常重要：**先存原始 fetch，再覆盖它**。
# 第一版把 `window.fetch = ...` 写在前面、把 `__MPVCB_ORIG_FETCH__` 的赋值写在后面，
# 于是覆盖进去的那个函数引用的 `window.__MPVCB_ORIG_FETCH__` 已经指向新 fetch
# —— 自己调自己，无限递归，页面报 "Maximum call stack size exceeded"。
# 当时我是靠把错误栈抓出来才定位到的（光看报错文本只会以为页面代码有问题）。
INJECT = """
(() => {
  const port = %d;
  window.__MPVCB_STDIO_CALLS__ = [];
  window.__MPVCB_HTTP_LEAKS__ = [];
  window.__MPVCB_ERR__ = '';

  // ① 先留好原始 fetch（必须在覆盖之前）
  const origFetch = window.fetch.bind(window);
  window.__MPVCB_ORIG_FETCH__ = origFetch;

  // ② stdio 通道：把协议请求 POST 给转发器
  window.__MPVCB_INVOKE__ = async (req) => {
    window.__MPVCB_STDIO_CALLS__.push(req.path);
    try {
      const r = await origFetch('http://127.0.0.1:' + port + '/__bridge__', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(req)
      });
      return await r.json();
    } catch (e) {
      // 把栈留下来 —— 这种问题光看报错文本定位不到（踩过）
      window.__MPVCB_ERR__ = String((e && e.stack) || e);
      throw e;
    }
  };

  // ③ 最后才覆盖 fetch。记账：任何还想走 /api/ 的 fetch 都是"没换干净"的证据
  window.fetch = (url, opts) => {
    const s = String(url);
    if (s.indexOf('/api/') >= 0) window.__MPVCB_HTTP_LEAKS__.push(s);
    return origFetch(url, opts);
  };

  // ④ 记录页面自身的报错，免得只看到"内容为空"却不知道原因
  window.addEventListener('error', e => {
    window.__MPVCB_ERR__ = String((e.error && e.error.stack) || e.message || e);
  });
  window.addEventListener('unhandledrejection', e => {
    const r = e.reason;
    window.__MPVCB_ERR__ = String((r && r.stack) || r);
  });
  return true;
})()
"""

# 每个页面：至少要能看到真实数据；同时读出这一页发生的调用。
PROBE = """
(() => ({
  title: document.title,
  bodyText: document.body.innerText.slice(0, 400),
  stdioCalls: (window.__MPVCB_STDIO_CALLS__ || []).slice(),
  httpLeaks: (window.__MPVCB_HTTP_LEAKS__ || []).slice(),
  err: window.__MPVCB_ERR__ || ''
}))()
"""


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def main():
    c = Checker()
    backend = StdioBackend()
    httpd = browser = None
    try:
        # 后端要先能用
        first = backend.call({"path": "status"})
        if not c("stdio 后端能响应 status", bool(first.get("ok")),
                 json.dumps(first, ensure_ascii=False)[:200]):
            return c.done()

        httpd, port = make_bridge(backend)
        print(f"转发器：http://127.0.0.1:{port}/__bridge__（只转发这一个路径）\n")

        cdp_port = free_port()
        browser = launch(cdp_port)
        cdp = connect(cdp_port)
        SHOTS.mkdir(exist_ok=True)

        all_calls, all_leaks = 0, []
        for name, page in PAGES:
            # 每个页面都要重新注入（导航会清掉 window 上的东西）
            cdp.call("Page.enable")
            cdp.call("Runtime.enable")
            # 先开一个同源空白页，注入后再跳转 —— 这样导航后 inject 不丢
            wait_page(cdp, f"http://127.0.0.1:{port}/__bridge__", wait_s=0.4)
            cdp.call("Page.addScriptToEvaluateOnNewDocument", source=INJECT % port)
            wait_page(cdp, f"http://127.0.0.1:{port}/{name}", wait_s=2.6)

            got = cdp.js(PROBE)
            print(f"—— {name} ——")
            if got.get("err"):
                print("    ⚠ 页面里捕获到的错误栈：")
                for l in str(got["err"]).splitlines()[:8]:
                    print("      " + l)
            calls, leaks = got["stdioCalls"], got["httpLeaks"]
            all_calls += len(calls)
            all_leaks += leaks
            c(f"{name}：页面加载了（有标题）", bool(got["title"]), got["title"])
            c(f"{name}：至少发了一条请求走 stdio 通道", len(calls) > 0,
              f"调用：{calls[:4]}")
            c(f"{name}：没有一条请求漏到 HTTP", not leaks, f"漏了：{leaks[:3]}")
            c(f"{name}：页面有真实内容（不是白屏/报错）",
              len(got["bodyText"].strip()) > 60,
              f"前 60 字：{got['bodyText'][:60]!r}")
            cdp.shot(str(SHOTS / f"61_stdio_{page}.png"))

        print()
        c("9 个页面共走了 stdio 通道", all_calls > 20, f"合计 {all_calls} 次调用")
        c("全程零 HTTP 泄漏", not all_leaks, f"{len(all_leaks)} 条")
        c("stdio 后端 stdout 每一行都是合法 JSON", not backend.dirty_stdout,
          f"脏行：{backend.dirty_stdout[:2]}")
        return c.done()
    finally:
        stop(browser)
        if httpd:
            httpd.shutdown()
        backend.close()


if __name__ == "__main__":
    raise SystemExit(main())
