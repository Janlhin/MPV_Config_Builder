# -*- coding: utf-8 -*-
"""验证**打包后的 Electron 应用**（release/win-unpacked）能真跑。

## 为什么必须单独验打包形态

开发形态（`electron .`）与打包形态的差别，恰好是路径解析最容易出错的地方：
  * `app.isPackaged` 从 false 变成 true，后端路径整条分支不一样；
  * 代码进了 `app.asar`（只读归档），`__dirname` 的语义跟着变；
  * renderer 从 asar 里读，`file://` 路径变了。

**而且这些错都不会让窗口打不开** —— 只是数据出不来了。所以判据还是那一条：
**页面必须显示出后端给的数据**。

用法：
    cd electron && npm run dist:dir      # 只打包不生成安装器，快
    py tools/check_electron_packaged.py
"""
import json
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EL = ROOT / "electron"
APP = EL / "release" / "win-unpacked" / "MPV Config Builder.exe"

PASS, FAIL = [], []


def ck(label, cond, detail=""):
    print(("  ✅ " if cond else "  ❌ ") + label + (f"  {detail}" if detail else ""))
    (PASS if cond else FAIL).append(label)
    return bool(cond)


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def find_ws(port, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/json/list", timeout=2) as f:
                tabs = json.load(f)
            page = next((t for t in tabs if t.get("type") == "page"), None)
            if page and page.get("webSocketDebuggerUrl"):
                return page["webSocketDebuggerUrl"]
        except Exception:
            pass
        time.sleep(0.6)
    return None


def backend_procs():
    # ⚠ 别用 tasklist 的 /FI 过滤器：Python 传 list 时引号会被拆开，永远匹配不到
    out = subprocess.run(["tasklist", "/NH", "/FO", "CSV"],
                         capture_output=True, text=True, timeout=30).stdout
    return sum(1 for l in out.splitlines()
               if "MPVConfigBuilderBackend.exe".lower() in l.lower())


def report():
    print()
    if FAIL:
        print(f"❌ {len(FAIL)} 项没过：")
        for x in FAIL:
            print("   - " + x)
        return 1
    print(f"✅ 全部通过（{len(PASS)} 项）")
    return 0


def main():
    print("=" * 58)
    print("打包后的 Electron 应用验证")
    print("=" * 58)

    if not ck("打包产物存在", APP.is_file(),
              "先跑：cd electron && npm run dist:dir" if not APP.is_file() else str(APP)):
        return report()

    res = EL / "release" / "win-unpacked" / "resources"
    for rel in ("backend/MPVConfigBuilderBackend.exe", "LICENSE", "NOTICE.txt"):
        ck(f"打包产物里带上了 {rel}", (res / rel).is_file())

    port = free_port()
    proc = subprocess.Popen([str(APP), f"--debug-port={port}"], cwd=str(APP.parent),
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        ws = find_ws(port)
        if not ck("打包后的应用能启动并创建窗口", bool(ws), f"port={port}"):
            return report()

        sys.path.insert(0, str(ROOT / "tools"))
        from uidriver import CDP                          # noqa: PLC0415
        cdp = CDP(ws)
        cdp.call("Page.enable")
        cdp.call("Runtime.enable")
        time.sleep(3.5)

        ck("打包形态下后端被拉起来了", backend_procs() >= 1,
           f"命中 {backend_procs()} 个")

        got = cdp.js("""(() => ({
          url: location.href,
          text: document.body.innerText.slice(0, 400),
          hasInvoke: typeof window.__MPVCB_INVOKE__ === 'function',
          nav: document.querySelectorAll('.topnav > *').length,
          leaked: typeof window.require
        }))()""")
        ck("页面从 asar 里加载成功", "app.asar" in got.get("url", ""),
           got.get("url", ""))
        ck("页面显示出后端数据（打包形态路径解析正确）",
           "v0.1.0" in got.get("text", ""), f"前 60 字：{got.get('text','')[:60]!r}")
        ck("preload 在打包形态下也生效", bool(got.get("hasInvoke")))
        ck("顶栏入口在打包形态下也在", got.get("nav") == 3, str(got.get("nav")))
        ck("contextIsolation 在打包形态下仍生效",
           got.get("leaked") == "undefined", str(got.get("leaked")))

        # 打一发真接口，确认 asar 里的 renderer + resources 里的后端都工作
        call = cdp.js("""(async () => {
          const r = await window.__MPVCB_INVOKE__({path: 'options'});
          return {ok: r.ok,
                  core: r.data && r.data.core ? r.data.core.length : null,
                  native: r.data && r.data.native ? r.data.native.length : null};
        })()""")
        ck("打包形态下接口可取到选项库（resources 里的 data/ 可读）",
           call.get("ok") and (call.get("core") or 0) > 0,
           json.dumps(call, ensure_ascii=False))
    finally:
        try:
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=15)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    left = 0
    deadline = time.time() + 15
    while time.time() < deadline:
        left = backend_procs()
        if left == 0:
            break
        time.sleep(0.5)
    ck("退出后没有孤儿后端进程", left == 0, f"还剩 {left} 个")
    return report()


if __name__ == "__main__":
    sys.exit(main())
