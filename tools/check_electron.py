# -*- coding: utf-8 -*-
"""Electron 外壳的实机验证（B1-4）。

## 为什么必须自动化验，而不是"打开看一眼"

GUI 应用没法靠命令行断定它对不对，而"我双击了一下能开"几乎什么都证明不了。
前几步已经吃过几次亏：**看不出来的错才是真错**（样式没生效、exe 崩在 import）。
所以这里走和浏览器版一样的路子：给 Electron 开一个**本地**调试端口，
用 CDP 连进去，把该验的事一条条验掉。

## 验什么

1. **窗口起来了、页面渲染了**（不是白屏、没有未捕获异常）
2. **数据是后端给的** —— 页面上的版本号/目标目录来自 Python，
   而 Electron 里**没有任何 HTTP 服务**，所以能显示出来就证明
   `页面 → preload → IPC → 主进程 → 后端 stdio` 这条链是通的
3. **preload 注入生效**：`window.__MPVCB_INVOKE__` 在，且 `window.require` 等
   Node 能力**不在**（contextIsolation 没白开）
4. **9 个页面都能在 Electron 里打开**并拿到数据
5. **单实例**：第二次启动不会开出第二个窗口/第二个后端
6. **退出时后端被杀干净**（不留孤儿进程占着配置目录）

用法：
    node scripts/sync-renderer.js          # 或 npm run sync
    py tools/check_electron.py
"""
import json
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ELECTRON_DIR = ROOT / "electron"
ELECTRON_EXE = ELECTRON_DIR / "node_modules" / "electron" / "dist" / "electron.exe"
BACKEND_EXE = ROOT / "dist" / "MPVConfigBuilderBackend" / "MPVConfigBuilderBackend.exe"

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
    """等 Electron 的调试端口起来，拿页面的 WebSocket 地址。"""
    deadline = time.time() + timeout
    last = ""
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/json/list", timeout=2) as f:
                tabs = json.load(f)
            page = next((t for t in tabs if t.get("type") == "page"), None)
            if page and page.get("webSocketDebuggerUrl"):
                return page["webSocketDebuggerUrl"]
            last = f"还没有 page：{tabs}"
        except Exception as e:
            last = str(e)
        time.sleep(0.6)
    return None


def backend_procs():
    """有没有后端进程在跑。

    ⚠⚠ 别用 `tasklist /FI "IMAGENAME eq X.exe"`。
    实测踩过：在 cmd 里那条过滤器是**一个参数**（带引号），
    而 Python 用 list 传参时会拆成 `IMAGENAME` / `eq` / `X.exe` 三个 ——
    tasklist 不认，于是**永远返回 0**。现象极具迷惑性：
    同一时刻后端明明活着（IPC 调得通、`tasklist` 不带过滤器也能看到它），
    只有这条检查在报"没有后端进程"。

    正确做法：列全部进程，在 Python 里数。慢一点，但判据是真的。
    """
    try:
        out = subprocess.run(["tasklist", "/NH", "/FO", "CSV"],
                             capture_output=True, text=True, timeout=30).stdout
    except Exception:
        return -1
    return sum(1 for line in out.splitlines()
               if "MPVConfigBuilderBackend.exe".lower() in line.lower())


def wait_backend(want, timeout=20):
    """等后端进程数达到 want。

    ⚠ 为什么必须等：调试端口是主进程一起来就开的，而 spawn 后端与它几乎同时发生
    —— 于是「刚连上 CDP 就查进程」会抢在后端真正出现之前，假报 0。
    实测踩过：第一次跑 check_electron 时这条假红，而同一时刻 IPC 调用是成功的。
    **报错和成功同时出现时，先怀疑检查本身。**
    """
    deadline = time.time() + timeout
    n = backend_procs()
    while time.time() < deadline:
        n = backend_procs()
        if n == want:
            return n
        time.sleep(0.4)
    return n


def report():
    print()
    if FAIL:
        print(f"❌ {len(FAIL)} 项没过：")
        for x in FAIL:
            print("   - " + x)
        return 1
    print(f"✅ 全部通过（{len(PASS)} 项）")
    return 0


def sync_diff():
    """renderer/ 与 webui/static/ 有没有差异。

    这是「同一个东西不存两份」那条决策的守门人：renderer/ 是构建期复制产物，
    一旦有人在里面手改（或忘了重新同步），Electron 里跑的就是**另一套页面** ——
    而我的其它实机脚本测的还是 webui/static 那份，于是「测试全绿、发出去的却是别的」。
    """
    import hashlib

    def digest(d):
        out = {}
        for f in sorted(d.rglob("*")):
            if f.is_file():
                out[str(f.relative_to(d))] = hashlib.sha256(f.read_bytes()).hexdigest()
        return out

    src = digest(ROOT / "webui" / "static")
    dst = digest(ELECTRON_DIR / "renderer")
    only_src = sorted(set(src) - set(dst))
    only_dst = sorted(set(dst) - set(src))
    modified = sorted(k for k in set(src) & set(dst) if src[k] != dst[k])
    return only_src, only_dst, modified


def main():
    print("=" * 58)
    print("Electron 外壳验证")
    print("=" * 58)

    if not ck("electron 二进制就位", ELECTRON_EXE.is_file(), str(ELECTRON_EXE)):
        return report()
    if not ck("后端 exe 就位（打包产物）", BACKEND_EXE.is_file(),
              "先跑：py -m PyInstaller packaging/backend.spec"):
        return report()
    if not ck("renderer 已同步（webui/static → electron/renderer）",
              (ELECTRON_DIR / "renderer" / "index.html").is_file(),
              "先跑：cd electron && npm run sync"):
        return report()

    # 内容一致性：光有文件不算同步，得逐字节一样
    only_src, only_dst, modified = sync_diff()
    ck("renderer 与 webui/static 逐字节一致（没人在副本上手改）",
       not (only_src or only_dst or modified),
       f"缺 {only_src} 多 {only_dst} 改了 {modified}")

    port = free_port()
    env = dict(**__import__("os").environ)
    env["ELECTRON_ENABLE_LOGGING"] = "1"
    proc = subprocess.Popen(
        [str(ELECTRON_EXE), ".", f"--debug-port={port}"],
        cwd=str(ELECTRON_DIR), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    try:
        ws = find_ws(port)
        if not ck("Electron 调试端口起来了（窗口已创建）", bool(ws), f"port={port}"):
            return report()

        sys.path.insert(0, str(ROOT / "tools"))
        from uidriver import CDP                      # noqa: PLC0415
        cdp = CDP(ws)
        cdp.call("Page.enable")
        cdp.call("Runtime.enable")
        time.sleep(3.0)          # 等页面 boot() 把 status/catalog 拉完

        ck("后端进程被拉起来了", wait_backend(1) == 1,
           f"tasklist 命中 {backend_procs()} 个")

        # ---- 1. 页面渲染 ----
        got = cdp.js("""(() => ({
          title: document.title,
          text: document.body.innerText.slice(0, 500),
          hasInvoke: typeof window.__MPVCB_INVOKE__ === 'function',
          leakedRequire: typeof window.require,
          leakedProcess: typeof window.process,
          hasTopnav: !!document.querySelector('.topnav'),
          navItems: [...document.querySelectorAll('.topnav > *')].map(e => e.textContent.trim())
        }))()""")
        ck("页面加载了（有标题）", bool(got.get("title")), str(got.get("title")))
        ck("页面渲染出了内容（不是白屏）", len(got.get("text", "").strip()) > 80,
           f"前 70 字：{got.get('text', '')[:70]!r}")
        ck("顶栏常驻入口也在（U-1 在 Electron 下同样生效）",
           bool(got.get("hasTopnav")) and len(got.get("navItems") or []) == 3,
           str(got.get("navItems")))

        # ---- 2. 数据来自后端（Electron 里没有 HTTP，所以这证明 IPC→stdio 通了）----
        ck("页面显示出了后端给的版本号",
           "v0.1.0" in got.get("text", ""), "文本里含 v0.1.0")
        ck("页面显示出了后端探测到的 mpv 目录",
           "portable_config" in got.get("text", ""),
           "文本里含 portable_config")

        # ---- 3. preload 只暴露该暴露的 ----
        ck("preload 注入了 __MPVCB_INVOKE__", bool(got.get("hasInvoke")))
        ck("contextIsolation 生效：页面拿不到 window.require",
           got.get("leakedRequire") == "undefined", str(got.get("leakedRequire")))
        ck("nodeIntegration 关闭：页面拿不到 window.process",
           got.get("leakedProcess") == "undefined", str(got.get("leakedProcess")))

        # ---- 4. 直接打一发 IPC，确认协议形状对 ----
        call = cdp.js("""(async () => {
          const r = await window.__MPVCB_INVOKE__({path: 'status', method: 'GET', query: {}});
          return {ok: r.ok, version: (r.data && r.data.version) || null};
        })()""")
        ck("IPC 直调 status 成功且形状正确",
           call.get("ok") and call.get("version") == "0.1.0",
           json.dumps(call, ensure_ascii=False))

        bad = cdp.js("""(async () => {
          const r = await window.__MPVCB_INVOKE__({path: '根本没有这个接口'});
          return {ok: r.ok, error: r.error};
        })()""")
        ck("不存在的接口返回 ok=false + error（不是抛异常）",
           bad.get("ok") is False and bool(bad.get("error")),
           json.dumps(bad, ensure_ascii=False))

        # ---- 5. 9 个页面都能开 ----
        pages = ["index.html", "basic.html", "advanced.html", "expert.html",
                 "analyze.html", "keys.html", "downloads.html", "guide.html",
                 "hell.html"]
        base = (ELECTRON_DIR / "renderer").as_uri()
        page_bad = []
        for name in pages:
            cdp.call("Page.navigate", url=f"{base}/{name}")
            time.sleep(1.6)
            r = cdp.js("""(() => ({
              len: document.body.innerText.trim().length,
              nav: document.querySelectorAll('.topnav > *').length
            }))()""")
            if r.get("len", 0) < 40 or r.get("nav") != 3:
                page_bad.append(f"{name}(len={r.get('len')}, nav={r.get('nav')})")
        ck("9 个页面在 Electron 里都能打开且有内容", not page_bad, "；".join(page_bad))

        # ---- 6. 单实例 ----
        second = subprocess.Popen(
            [str(ELECTRON_EXE), ".", f"--debug-port={free_port()}"],
            cwd=str(ELECTRON_DIR), env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(4.0)
        n_after = wait_backend(1, timeout=8)
        ck("第二次启动不会开出第二个后端（单实例生效）", n_after == 1,
           f"后端进程数 {n_after}")
        try:
            second.terminate()
        except Exception:
            pass
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

    # ---- 7. 退出时杀干净（必须在 finally 之后查）----
    # 同样要等：进程退出有延迟，立刻查会查到还没消失的那个
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

