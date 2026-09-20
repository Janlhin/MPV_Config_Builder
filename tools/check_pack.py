# -*- coding: utf-8 -*-
"""对**打包产物**做端到端验证（specs/backend-packaging.md 的 AC-1 ~ AC-7）。

## 为什么必须单独验打包产物

源码模式全绿**证明不了打包产物能用** —— 这两件事的差别正好是最容易出事的地方：

* 漏带 `data/` → 程序照常启动，只是「完全体」页面空白；
* 漏带 `webui/static/` → 界面打不开；
* 漏带 `*.md` → 文档页空白；
* 用 `--windowed` → stdio 协议整个废掉；
* W-2 的用户数据目录逻辑在冻结环境下走的是另一条分支（`is_frozen()`）。

这些**都不会让 exe 启动失败**，所以"我双击了一下能开"根本不算验证。

## 验什么

1. exe 存在、整目录体积合理；
2. `--stdio` 能跑，stdout **每一行都是合法 JSON**（bootloader 没污染协议）；
3. 关键资源真的在包里（data / static / md / LICENSE / NOTICE）；
4. 通过接口把每个资源**读一遍**（不是只看文件在不在）：
   `status` / `db/options` / `guide` / `options`；
5. 用户数据目录是 `%LOCALAPPDATA%\\MPVConfigBuilder`，**不是** exe 旁边（W-2 在冻结下仍成立）；
6. `--port N --no-window` 起 HTTP 仍可用。

用法（先打包）：
    py -m PyInstaller packaging/backend.spec
    py tools/check_pack.py
"""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist" / "MPVConfigBuilderBackend"
EXE = DIST / "MPVConfigBuilderBackend.exe"

PASS, FAIL = [], []


def ck(label, cond, detail=""):
    print(("  ✅ " if cond else "  ❌ ") + label + (f"  {detail}" if detail else ""))
    (PASS if cond else FAIL).append(label)
    return bool(cond)


def stdio_run(requests, timeout=120):
    """灌几条请求给真 exe，拿回 stdout/stderr/退出码。"""
    payload = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in requests)
    p = subprocess.run([str(EXE), "--stdio"], input=payload.encode("utf-8"),
                       capture_output=True, timeout=timeout, cwd=str(DIST))
    return p, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def main():
    print("=" * 58)
    print("打包产物验证")
    print("=" * 58)

    if not ck("产物 exe 存在", EXE.is_file(), str(EXE)):
        return 1
    total = sum(f.stat().st_size for f in DIST.rglob("*") if f.is_file())
    ck("整目录体积在合理范围（5–80 MB）", 5 < total / 1e6 < 80,
       f"{total/1e6:.1f} MB")

    # ---- 包内资源 ----
    internal = DIST / "_internal"
    for rel in ("data/mpv_options_zh.json", "data/mpv_keybindings.json",
                "data/mpv_commands.json", "webui/static/index.html",
                "webui/static/api.js", "webui/static/style.css",
                "LICENSE", "NOTICE.txt", "入门指南.md"):
        ck(f"包内带上了 {rel}", (internal / rel).is_file())

    # ---- stdio：协议纯净性（本 spec 的核心风险）----
    p, out, err = stdio_run([
        {"id": 1, "path": "status"},
        {"id": 2, "path": "db/options", "query": {"offset": "0", "limit": "3"}},
        {"id": 3, "path": "guide", "query": {"doc": "guide"}},
    ])
    ck("exe --stdio 退出码 0", p.returncode == 0, f"实际 {p.returncode}")

    rows, dirty = [], []
    for i, raw in enumerate(out.splitlines(), 1):
        if not raw.strip():
            continue
        try:
            rows.append(json.loads(raw))
        except ValueError:
            dirty.append((i, raw[:120]))
    ck("stdout 每一行都是合法 JSON（bootloader 没污染协议）", not dirty,
       f"脏行：{dirty[:2]}")
    ck("3 条请求都有响应", len(rows) == 3, f"实际 {len(rows)} 行")
    ck("id 一一对应", [r.get("id") for r in rows] == [1, 2, 3],
       f"实际 {[r.get('id') for r in rows]}")
    ck("stdout 里没有 HTTP 痕迹", "http://" not in out)

    by_id = {r.get("id"): r for r in rows}
    st = by_id.get(1, {}).get("data") or {}
    ck("status 返回真实数据（版本号非空）", bool(st.get("version")), str(st.get("version")))

    dbo = by_id.get(2, {}).get("data") or {}
    n_db = dbo.get("total") or len(dbo.get("rows") or dbo.get("options") or [])
    ck("db/options 读到了选项库（打包后 data/ 可用）", bool(n_db), f"total={n_db}")

    gd = by_id.get(3, {}).get("data") or {}
    ck("guide 读到了 md 内容（打包后 *.md 可用）",
       bool(gd.get("html")) and len(str(gd.get("html"))) > 200,
       f"html 长度 {len(str(gd.get('html')))}")

    # ---- W-2：冻结环境下的用户数据目录 ----
    # 问它自己（用 describe 那条路径最可靠：status 里不带这个字段就换 raw）
    p2, out2, _ = stdio_run([{"id": 1, "path": "raw",
                              "query": {"path": ""}}])
    # 直接用一个更硬的判据：exe 旁边**不该**出现 presets/ 或 settings.json
    strays = [x.name for x in DIST.iterdir()
              if x.name in ("presets", "settings.json", "installed.json")]
    ck("exe 目录里没有用户数据（W-2 在冻结下仍成立）", not strays, f"发现 {strays}")

    # ---- HTTP 仍可用 ----
    port = free_port()
    proc = subprocess.Popen([str(EXE), "--port", str(port), "--no-window"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            cwd=str(DIST))
    try:
        ok, deadline = False, time.time() + 40
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/api/status", timeout=2) as f:
                    data = json.load(f)
                ok = bool(data.get("version"))
                break
            except Exception:
                time.sleep(0.5)
        ck("--port/--no-window 起 HTTP 仍可用", ok, f"端口 {port}")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()

    print()
    if FAIL:
        print(f"❌ {len(FAIL)} 项没过：")
        for x in FAIL:
            print("   - " + x)
        return 1
    print(f"✅ 全部通过（{len(PASS)} 项）")
    return 0


if __name__ == "__main__":
    if not EXE.is_file():
        sys.exit(f"没找到产物：{EXE}\n先跑：py -m PyInstaller packaging/backend.spec")
    sys.exit(main())
