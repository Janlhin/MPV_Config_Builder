# -*- coding: utf-8 -*-
"""发布前自检：一次跑完所有"发之前必须过"的检查。

为什么要有它：这个项目吃过"文档与实现不一致"的亏（README 说 20 个接口、实际 23），
也吃过"打包后才失效"的亏（文档路径用 `__file__` 推）。这些检查零散在各处，
发布时容易漏跑其中一项。这里串成一条，**退出码非 0 就别发**。

用法（仓库根目录）：
    py -3 tools/preflight.py

检查项：
    1. 单元测试全绿
    2. 全部源码可编译
    3. 文档数字与实测一致（调 tools/check_docs.py）
    4. 下载清单里的 URL 都还活着（要联网；用 --offline 跳过）
    5. 必带的发行文件都在（data / md / static）
    6. 没有残留的"机器专用绝对路径"
    7. 许可文件内容（GPL-3.0 全文 + 第三方归属）
    8. 顶栏常驻入口在 9 个页面上真的渲染出来了（要本机有 Edge/Chrome；没有就跳过）
    9. Electron 外壳能跑、页面能拿到后端数据（要装了 node_modules；没装就跳过）

⚠ 联网那一步（4）在国内网络下可能整体失败 —— 那是网络问题不是清单问题，
脚本会明确区分"清单失效"与"连不上"。
"""
import argparse
import compileall
import importlib.util
import io
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

# 界面上能在线打开的文档（webui/server.py 的 DOCS 白名单）+ 发行包该带的
REQUIRED_DOCS = [
    "入门指南.md", "MPV_Shader搭配说明书.md", "致谢与许可.md",
    "产品规划与路线图.md",
]
REQUIRED_DATA = [
    "data/mpv_options_zh.json", "data/mpv_keybindings.json", "data/mpv_commands.json",
]
REQUIRED_STATIC = ["webui/static/index.html", "webui/static/style.css",
                   "webui/static/api.js", "webui/static/state.js"]
# 合规文件：分发安装包时**必须**一并带上（GPL-3.0 的要求）。
# ⚠ 为什么把它们列进"必带"而不是只在结尾提醒一句：提醒是**空话** ——
# 忘了也没人拦。之前它们既不在这个清单里、也不在打包文档的 --add-data 里，
# 也就是说"提醒你带"和"检查你带了"之间是断的。
REQUIRED_LEGAL = ["LICENSE", "NOTICE.txt"]

# 不该再出现的"作者机器专用"路径（用户名硬编码）
FORBIDDEN = [re.compile(r"C:\\Users\\Janlhin", re.I)]


class Result:
    def __init__(self):
        self.items = []

    def add(self, name, ok, detail=""):
        self.items.append((name, ok, detail))
        mark = "✅" if ok else "❌"
        print(f"  {mark} {name}" + (f"：{detail}" if detail else ""))

    @property
    def failed(self):
        return [x for x in self.items if not x[1]]


def check_tests(r):
    suite = unittest.TestLoader().discover(str(ROOT / "tests"), top_level_dir=str(ROOT))
    res = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
    bad = len(res.failures) + len(res.errors)
    r.add(f"单元测试（{res.testsRun} 项）", bad == 0,
          "" if bad == 0 else f"{bad} 项失败/报错")


def check_compile(r):
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        ok = compileall.compile_dir(str(ROOT / "core"), quiet=2)
        ok = compileall.compile_dir(str(ROOT / "webui"), quiet=2) and ok
        ok = compileall.compile_dir(str(ROOT / "tests"), quiet=2) and ok
        ok = compileall.compile_dir(str(ROOT / "tools"), quiet=2) and ok
        ok = compileall.compile_file(str(ROOT / "legacy" / "mpv_config_builder.py"), quiet=2) and ok
    finally:
        sys.stdout = old
    r.add("源码可编译", bool(ok), buf.getvalue().strip()[:120])


def check_docs(r):
    p = subprocess.run([sys.executable, str(ROOT / "tools" / "check_docs.py")],
                       capture_output=True, text=True, encoding="utf-8",
                       cwd=str(ROOT))
    tail = (p.stdout or "").strip().splitlines()[-1:] or [""]
    r.add("文档数字与实测一致", p.returncode == 0, "" if p.returncode == 0 else tail[0])


def check_files(r):
    need = REQUIRED_DOCS + REQUIRED_DATA + REQUIRED_STATIC + REQUIRED_LEGAL
    missing = [f for f in need if not (ROOT / f).is_file()]
    r.add(f"发行必带文件（{len(need)} 个）",
          not missing, "缺：" + "、".join(missing) if missing else "")


def check_license_content(r):
    """合规文件不只是"存在"，还得**内容对**。

    光检查存在会漏掉最糟的情况：`LICENSE` 是个空文件、或者被人换成了别的东西 ——
    那样"带上了"却仍然不合规。所以这里额外验两件事：
      · `LICENSE` 确实是 **GPL-3.0 全文**（认标题、版本、结尾段，以及 0–17 条）；
      · `NOTICE.txt` 里写了本项目自身的许可与那几个第三方来源。
    """
    lic = ROOT / "LICENSE"
    if not lic.is_file():
        return r.add("许可文件内容", False, "没有 LICENSE")
    text = lic.read_text(encoding="utf-8", errors="replace")
    problems = []
    for label, needle in (("标题", "GNU GENERAL PUBLIC LICENSE"),
                          ("版本", "Version 3, 29 June 2007"),
                          ("第0条", "0. Definitions."),
                          ("第17条", "17. Interpretation of Sections 15 and 16."),
                          ("结尾段", "How to Apply These Terms to Your New Programs")):
        if needle not in text:
            problems.append(f"缺{label}")
    secs = sorted({int(x) for x in re.findall(r"^(\d{1,2})\. ", text, re.M)})
    if secs != list(range(18)):
        problems.append(f"条款编号不全（{secs}）")
    if len(text.encode("utf-8")) < 30000:
        problems.append(f"太短（{len(text.encode('utf-8'))} 字节）—— GPL-3.0 全文约 35 KB")

    notice = ROOT / "NOTICE.txt"
    if not notice.is_file():
        problems.append("没有 NOTICE.txt")
    else:
        nt = notice.read_text(encoding="utf-8", errors="replace")
        for label, needle in (("本项目许可声明", "GPL-3.0"),
                              ("数据来源", "mpv_doc-CN"),
                              ("下载来源", "uosc")):
            if needle not in nt:
                problems.append(f"NOTICE 里缺{label}")
    r.add("许可文件内容（GPL-3.0 全文 + 归属）", not problems,
          "；".join(problems) if problems else "")


def check_absolute_paths(r):
    hits = []
    for f in list((ROOT / "core").glob("*.py")) + [
            ROOT / "webui" / "server.py", ROOT / "legacy" / "mpv_config_builder.py"]:
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            for pat in FORBIDDEN:
                if pat.search(line):
                    hits.append(f"{f.name}:{i}")
    r.add("没有机器专用绝对路径", not hits, "；".join(hits[:5]))


def check_links(r, offline=False):
    if offline:
        r.add("下载清单链接可访问", True, "已用 --offline 跳过")
        return
    try:
        from core import dlcenter
        results = dlcenter.check_links(timeout=15)
    except Exception as e:
        r.add("下载清单链接可访问", False, f"检查本身失败：{type(e).__name__}")
        return
    bad = [x for x in results if not x["ok"]]
    net_down = bad and all("URLError" in x["detail"] or "timed out" in x["detail"]
                           or "getaddrinfo" in x["detail"] or x["status"] == 0
                           for x in bad)
    if net_down:
        r.add(f"下载清单链接可访问（{len(results)} 条）", True,
              "连不上网，无法判断 —— 不算失败，但发布前请在能联网的机器上再跑一次")
    else:
        r.add(f"下载清单链接可访问（{len(results)} 条）", not bad,
              "失效：" + "、".join(x["id"] for x in bad) if bad else "")


def check_ui_nav(r):
    """顶栏常驻入口在 9 个页面上真的渲染出来了吗（U-1）。

    **没有 Edge/Chrome 就跳过，不算失败** —— 这是实机检查，不是每个人每台机器
    都能跑。但只要有浏览器，它就必须过：这个功能是纯 JS 注入的，
    HTML 里一个入口都看不到，只有真跑一遍才知道有没有撞上页面自己的 DOM/变量。
    """
    if importlib.util.find_spec("uidriver") is None and not (Path(__file__).parent / "uidriver.py").is_file():
        r.add("顶栏常驻入口实机检查", True, "跳过（找不到 tools/uidriver.py）")
        return
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from uidriver import find_browser                            # noqa: PLC0415
    if not find_browser():
        r.add("顶栏常驻入口实机检查", True, "跳过（本机没有 Edge/Chrome）")
        return
    p = subprocess.run([sys.executable, "-X", "utf8",
                        str(Path(__file__).parent / "check_topnav.py")],
                       capture_output=True, cwd=str(ROOT))
    tail = p.stdout.decode("utf-8", "replace").strip().splitlines()
    summary = tail[-1] if tail else "(没有输出)"
    r.add("顶栏常驻入口实机检查", p.returncode == 0, summary)


def check_electron_pack(r):
    """Electron 那套（如果本机备齐了工具链）能不能跑通。

    **没装 node_modules 就算跳过，不算失败** —— Electron 是可选的外壳，
    不是发布源码包的必要条件。但只要装了，它的实机检查就必须过。
    """
    el = ROOT / "electron"
    if not (el / "node_modules" / "electron" / "dist" / "electron.exe").is_file():
        r.add("Electron 外壳实机检查", True, "跳过（electron/node_modules 没装）")
        return
    if not (ROOT / "dist" / "MPVConfigBuilderBackend" / "MPVConfigBuilderBackend.exe").is_file():
        r.add("Electron 外壳实机检查", True,
              "跳过（后端 exe 还没打；先跑 py -m PyInstaller packaging/backend.spec）")
        return
    p = subprocess.run([sys.executable, "-X", "utf8",
                        str(Path(__file__).parent / "check_electron.py")],
                       capture_output=True, cwd=str(ROOT))
    tail = p.stdout.decode("utf-8", "replace").strip().splitlines()
    r.add("Electron 外壳实机检查", p.returncode == 0,
          tail[-1] if tail else "(没有输出)")

    if (el / "release" / "win-unpacked" / "MPV Config Builder.exe").is_file():
        p2 = subprocess.run([sys.executable, "-X", "utf8",
                             str(Path(__file__).parent / "check_electron_packaged.py")],
                            capture_output=True, cwd=str(ROOT))
        tail2 = p2.stdout.decode("utf-8", "replace").strip().splitlines()
        r.add("Electron 打包形态检查", p2.returncode == 0,
              tail2[-1] if tail2 else "(没有输出)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="跳过联网检查")
    args = ap.parse_args()

    print("=" * 58)
    print("发布前自检")
    print("=" * 58)
    r = Result()
    check_tests(r)
    check_compile(r)
    check_docs(r)
    check_files(r)
    check_license_content(r)
    check_absolute_paths(r)
    check_links(r, offline=args.offline)
    check_ui_nav(r)
    check_electron_pack(r)

    print("-" * 58)
    if r.failed:
        print(f"❌ 有 {len(r.failed)} 项没过，先修再发：")
        for name, _ok, detail in r.failed:
            print(f"   · {name} {detail}")
        return 1
    print("✅ 全部通过")
    print("\n提醒：发之前还想清楚 ——")
    print("   1. 打包命令要带全（否则文档页与选项库会空）：")
    print("      --add-data \"data;data\"  --add-data \"webui\\static;webui\\static\"")
    print("      --add-data \"LICENSE;.\"  --add-data \"NOTICE.txt;.\"   ← 合规要求")
    print("      --add-data \"*.md;.\"（界面里的文档是实时渲染它们的）")
    print("   2. 打包产物附上 GPL-3.0 全文（就是上面那个 LICENSE）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
