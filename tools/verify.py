# -*- coding: utf-8 -*-
"""验证工具总入口：把「证明它真的对」的检查收拢到一个命令。

原来的 tools/ 里有 10 个各自为政的验证脚本（preflight / check_docs /
check_topnav / check_stdio_ui / check_presets / check_ui / check_electron /
check_electron_packaged / check_pack / compare_conflicts），每个都重复一遍
「找仓库根 + 插 sys.path + main()」的样板。2026-10-09 合并到这里 ——
**只收拢，不改逻辑**，每个子命令都保留了原脚本自己的说明（见各函数 docstring）。
2026-11-16 Electron 整体移除：check_electron / check_electron_packaged 两个
子命令随之删除，外壳只剩 Tauri（`tauri`）。

用法（仓库根目录）：

    python tools/verify.py               # = all：发布前自检（跑全量）
    python tools/verify.py <子命令>      # 单跑一项

子命令：

    all        发布前自检：一次跑完所有「发之前必须过」的检查
    precommit  提交门禁：秒级检查，脏提交进不了历史（.githooks/pre-commit 调它）
    commitmsg  提交信息门禁：Conventional Commits + 400 行提示（.githooks/commit-msg 调它）
    layout     根目录白名单（git ls-files 顶层条目 + README 目录声明）
    stack      技术栈与运行时版本登记（版本文件 / CI / README 同源）
    docs       文档里的数字与实测是否一致
    i18n       i18n 键集合 / 占位符（静态）+ 真浏览器切换与刷新保持（动态）
    status     实机验证 9 页共用的状态栏、离线横幅与右键菜单
    ctxmenu    实机验证右键菜单（复制选项名 / 当前值 / 恢复默认 / 完整说明）
    hotkeys    实机验证键盘快捷键层（Ctrl+S 主操作 / ? 帮助面板 / 选项行导航）
    motion     实机验证界面动效（page-in / 展开过渡 / 侧栏淡入 / 保存回执 / reduced-motion）
    topnav     实机验证 9 个页面的顶栏常驻入口
    stdio      实机验证 9 个页面跑在 stdio 通道上
    presets    实机验证「我自己的预设」存读
    ui         实机验证候选值下拉
    tauri      实机验证 Tauri 外壳（stdio 桥、不开端口、退出不留孤儿）
    pack       对打包产物做端到端验证
    conflicts  冲突规则重构前后等价性（4699 组枚举）

`all` 与 `tauri` / `pack` 依赖编译产物（Tauri exe / 后端 exe），缺了会自动跳过
（不算失败）；`topnav` / `stdio` / `presets` / `ui` 要本机有 Edge/Chrome，
没有也会跳过。细节看各子命令自己的说明。
"""
import argparse
import importlib.util
import io
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.stdout.reconfigure(encoding="utf-8")


def script_baseline_problems():
    """脚本基线（工程规则 Pwsh-only）—— **规则全仓库只有这一份**。

    为什么要抽出来：`cmd_all` 的 `check_script_baseline` 与提交门禁
    `cmd_precommit` 都要判它。两处各写一遍，迟早会长歪 —— 这正是
    `AGENTS.md` §2.6「数字不要手抄」的同种毛病，只不过抄的是规则。

    判两条（2026-10-14 立：启动.bat 转成 启动.ps1、仓库 Pwsh-only 之后）：
      1. 仓库里**没有** `.bat` / `.cmd`。构建产物目录除外 —— `dist` /
         `tauri/src-tauri/target` 不入库、由编译重新生成，判它们等于判打包机。
      2. `.ps1` 必须是 **UTF-8 带 BOM + CRLF**。BOM 是必须的：Windows
         PowerShell 5.1 靠 BOM 识别 UTF-8（无 BOM 中文乱码），Pwsh 7 两种都认。
         ⚠ 与 2026-10-09 的 .bat「**无** BOM」结论正好相反，别把旧结论套过来。

    返回 `(问题列表, 统计dict)`。
    """
    bad = []
    # 1. 全仓库扫 .bat / .cmd（跳过构建产物与依赖目录）
    SKIP_DIRS = {".git", "node_modules", "__pycache__", "dist",
                 "release", "win-unpacked", "cache", ".venv", "venv"}
    bats = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if fn.lower().endswith((".bat", ".cmd")):
                bats.append(str((Path(dirpath) / fn).relative_to(ROOT)))
    if bats:
        bad.append(f"仓库还有 {len(bats)} 个 .bat/.cmd（Pwsh-only 基线，见 AGENTS.md §2.4）："
                   + "、".join(sorted(bats)[:5]))
    # 2. .ps1 格式（BOM 必须**有**，CRLF 必须纯）
    BOM = b"\xef\xbb\xbf"
    ps1s = sorted(ROOT.glob("*.ps1")) + sorted(ROOT.glob("*/*.ps1"))
    for p in ps1s:
        b = p.read_bytes()
        rel = str(p.relative_to(ROOT))
        if not b.startswith(BOM):
            bad.append(f"{rel} 缺 BOM（.ps1 必须带 BOM：5.1 靠它识别 UTF-8；"
                       f"跑 python tools\\build.py ps1）")
        lf = b.count(b"\n") - b.count(b"\r\n")
        if lf:
            bad.append(f"{rel} 有 {lf} 处裸 LF（.ps1 要 CRLF）")
    return bad, {"bat": len(bats), "ps1": len(ps1s)}


# ==========================================================================
# all（原 preflight.py）
# ==========================================================================
def cmd_all():
    """发布前自检：一次跑完所有"发之前必须过"的检查。

    为什么要有它：这个项目吃过"文档与实现不一致"的亏（README 说 20 个接口、实际 23），
    也吃过"打包后才失效"的亏（文档路径用 `__file__` 推）。这些检查零散在各处，
    发布时容易漏跑其中一项。这里串成一条，**退出码非 0 就别发**。

    用法（仓库根目录）：
        py -3 tools/verify.py

    检查项：
        1. 单元测试全绿
        2. 全部源码可编译
        3. 文档数字与实测一致（调 verify.py docs）
        4. 下载清单里的 URL 都还活着（要联网；用 --offline 跳过）
        5. 必带的发行文件都在（data / md / static）
        6. 没有残留的"机器专用绝对路径"
        7. 许可文件内容（GPL-3.0 全文 + 第三方归属）
        8. 顶栏常驻入口在 9 个页面上真的渲染出来了（要本机有 Edge/Chrome；没有就跳过）
        9. Tauri 外壳（唯一外壳）能跑、页面能拿到后端数据
           （静态约定每次都查；实机要 cargo build 出的 exe，没有就跳过）

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
    # 2026-11-17 起它们都在 docs/（根目录只留五个文档，见 README「目录结构」）
    REQUIRED_DOCS = [
        "docs/入门指南.md", "docs/MPV_Shader搭配说明书.md", "docs/致谢与许可.md",
        "docs/产品规划与路线图.md",
    ]
    REQUIRED_DATA = [
        "data/mpv_options_zh.json", "data/mpv_keybindings.json", "data/mpv_commands.json",
        "data/_mpv_options_raw.txt",
    ]
    REQUIRED_STATIC = ["webui/static/index.html", "webui/static/style.css",
                       "webui/static/api.js", "webui/static/state.js"]
    # 合规文件：分发安装包时**必须**一并带上（GPL-3.0 的要求）。
    # ⚠ 为什么把它们列进"必带"而不是只在结尾提醒一句：提醒是**空话** ——
    # 忘了也没人拦。之前它们既不在这个清单里、也不在打包文档的 --add-data 里，
    # 也就是说"提醒你带"和"检查你带了"之间是断的。
    REQUIRED_LEGAL = ["LICENSE", "docs/NOTICE.txt"]

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
        buf = io.StringIO()
        suite = unittest.TestLoader().discover(str(ROOT / "tests"), top_level_dir=str(ROOT))
        res = unittest.TextTestRunner(stream=buf, verbosity=2).run(suite)
        bad = len(res.failures) + len(res.errors)
        if bad:
            # 只报「N 项失败」等于把排查成本推给下一次运行 —— CI 上尤其致命：
            # 那边没有交互式环境可以随手重跑，一次运行几分钟。所以明细必须打出来。
            print("\n—— 单元测试失败明细 ——")
            print(buf.getvalue().strip()[-4000:])
            print("————————————————————\n")
        names = [t.id().split("tests.")[-1] for t, _ in (res.failures + res.errors)]
        r.add(f"单元测试（{res.testsRun} 项）", bad == 0,
              "" if bad == 0 else f"{bad} 项失败/报错：" + "、".join(names[:6]))


    def check_compile(r):
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            ok = compileall.compile_dir(str(ROOT / "core"), quiet=2)
            ok = compileall.compile_dir(str(ROOT / "webui"), quiet=2) and ok
            ok = compileall.compile_dir(str(ROOT / "tests"), quiet=2) and ok
            ok = compileall.compile_dir(str(ROOT / "tools"), quiet=2) and ok
            # 旧界面（Tkinter）2026-10-09 移出仓库、归档在 ..\MPV_Config_Builder_legacy\，
            # 所以这里不再编它 —— 归档副本不随发行包走，也不该拖住发布自检。
            # 它自己的可运行性由那份归档里的 `自检.py` 负责。
        finally:
            sys.stdout = old
        r.add("源码可编译", bool(ok), buf.getvalue().strip()[:120])


    def check_docs(r):
        p = subprocess.run([sys.executable, str(ROOT / "tools" / "verify.py"), "docs"],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace",
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

        notice = ROOT / "docs" / "NOTICE.txt"
        if not notice.is_file():
            problems.append("没有 docs/NOTICE.txt")
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
        for f in list((ROOT / "core").glob("*.py")) + [ROOT / "webui" / "server.py"]:
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
                            str(Path(__file__).parent / "verify.py"), "topnav"],
                           capture_output=True, cwd=str(ROOT))
        tail = p.stdout.decode("utf-8", "replace").strip().splitlines()
        summary = tail[-1] if tail else "(没有输出)"
        r.add("顶栏常驻入口实机检查", p.returncode == 0, summary)


    def check_i18n(r):
        """i18n 机制在真浏览器里真的能切换语言吗（U-2）。

        静态那半（两张语言表的键是否一致、占位符有没有漏填）不需要浏览器，
        在 cmd_i18n 里用 Python 直接判；这里跑的是**动态那半**——
        点了按钮文字是否真的变、刷新后偏好是否还在。

        **没有 Edge/Chrome 就跳过，不算失败** —— 和顶栏检查同一个道理：
        这是实机检查，不是每台机器都跑得了。但只要能跑，它就必须过。
        """
        if importlib.util.find_spec("uidriver") is None and not (Path(__file__).parent / "uidriver.py").is_file():
            r.add("i18n 切换实机检查", True, "跳过（找不到 tools/uidriver.py）")
            return
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from uidriver import find_browser                            # noqa: PLC0415
        if not find_browser():
            r.add("i18n 切换实机检查", True, "跳过（本机没有 Edge/Chrome）")
            return
        p = subprocess.run([sys.executable, "-X", "utf8",
                            str(Path(__file__).parent / "verify.py"), "i18n"],
                           capture_output=True, cwd=str(ROOT))
        tail = p.stdout.decode("utf-8", "replace").strip().splitlines()
        err = p.stderr.decode("utf-8", "replace").strip().splitlines()
        detail = tail[-1] if tail else "(没有输出)"
        if p.returncode != 0 and err:
            detail += " ‖ stderr: " + " / ".join(err[-4:])
        r.add("i18n 切换实机检查", p.returncode == 0,
              tail[-1] if tail else "(没有输出)")


    def check_script_baseline(r):
        """脚本基线：仓库无 `.bat`/`.cmd`；`.ps1` 带 BOM + CRLF。

        2026-10-14 立。为什么门禁要查：工程规则把「禁止 cmd/bat、统一 Pwsh」
        列为**护栏而非调度变量**（不得为不停机而降级），所以它必须可机器判定。
        规则只有一份，在 `script_baseline_problems`，提交门禁共用。
        .ps1 的 BOM 要求与 2026-10-09 的 .bat「无 BOM」结论相反，原因见那函数。
        """
        bad, st = script_baseline_problems()
        r.add("脚本基线（无 .bat/.cmd，.ps1 带 BOM+CRLF）", not bad,
              "；".join(bad) if bad
              else f".bat/.cmd {st['bat']} 个 · .ps1 {st['ps1']} 个且格式正确")


    def check_status(r):
        """状态栏 / 后端离线提示在真浏览器里对吗（界面打磨第一批）。

        判的是两件事：**状态栏活着**（读得到目标路径、后端状态对），
        以及**后端挂了会说话**（不再白屏）。

        **没有 Edge/Chrome 就跳过，不算失败** —— 和顶栏、i18n 同一个道理：
        这是实机检查，不是每台机器都跑得了。
        """
        if importlib.util.find_spec("uidriver") is None and not (Path(__file__).parent / "uidriver.py").is_file():
            r.add("状态栏与后端提示实机检查", True, "跳过（找不到 tools/uidriver.py）")
            return
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from uidriver import find_browser                            # noqa: PLC0415
        if not find_browser():
            r.add("状态栏与后端提示实机检查", True, "跳过（本机没有 Edge/Chrome）")
            return
        p = subprocess.run([sys.executable, "-X", "utf8",
                            str(Path(__file__).parent / "verify.py"), "status"],
                           capture_output=True, cwd=str(ROOT))
        tail = p.stdout.decode("utf-8", "replace").strip().splitlines()
        err = p.stderr.decode("utf-8", "replace").strip().splitlines()
        detail = tail[-1] if tail else "(没有输出)"
        if p.returncode != 0 and err:
            detail += " ‖ stderr: " + " / ".join(err[-4:])
        r.add("状态栏与后端提示实机检查", p.returncode == 0,
              tail[-1] if tail else "(没有输出)")


    def check_ctxmenu(r):
        """右键菜单在真浏览器里对吗（界面打磨第二批）。

        判四件事：能弹出、复制的是对的那一行、Esc 能关、恢复默认真的把状态改回去。
        **没有 Edge/Chrome 就跳过，不算失败** —— 同顶栏 / i18n / 状态栏。
        """
        if importlib.util.find_spec("uidriver") is None and not (Path(__file__).parent / "uidriver.py").is_file():
            r.add("右键菜单实机检查", True, "跳过（找不到 tools/uidriver.py）")
            return
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from uidriver import find_browser                            # noqa: PLC0415
        if not find_browser():
            r.add("右键菜单实机检查", True, "跳过（本机没有 Edge/Chrome）")
            return
        p = subprocess.run([sys.executable, "-X", "utf8",
                            str(Path(__file__).parent / "verify.py"), "ctxmenu"],
                           capture_output=True, cwd=str(ROOT))
        tail = p.stdout.decode("utf-8", "replace").strip().splitlines()
        err = p.stderr.decode("utf-8", "replace").strip().splitlines()
        detail = tail[-1] if tail else "(没有输出)"
        if p.returncode != 0 and err:
            detail += " ‖ stderr: " + " / ".join(err[-4:])
        r.add("右键菜单实机检查", p.returncode == 0,
              tail[-1] if tail else "(没有输出)")


    def check_hotkeys(r):
        """键盘快捷键层在真浏览器里对吗（界面打磨·快捷键切片，R-28）。

        判六件事：? 开面板 / Esc 关 / 面板只列本页生效的条目 /
        Ctrl+S 触发主操作并拦浏览器默认 / 打字不被劫持 / 选项行方向键导航。
        写配置的接口在检查内部已换成桩（不会真写 mpv.conf）。
        **没有 Edge/Chrome 就跳过，不算失败** —— 同顶栏 / i18n / 状态栏 / 右键菜单。
        """
        if importlib.util.find_spec("uidriver") is None and not (Path(__file__).parent / "uidriver.py").is_file():
            r.add("键盘快捷键实机检查", True, "跳过（找不到 tools/uidriver.py）")
            return
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from uidriver import find_browser                            # noqa: PLC0415
        if not find_browser():
            r.add("键盘快捷键实机检查", True, "跳过（本机没有 Edge/Chrome）")
            return
        p = subprocess.run([sys.executable, "-X", "utf8", "-u",
                            str(Path(__file__).parent / "verify.py"), "hotkeys"],
                           capture_output=True, cwd=str(ROOT))
        tail = p.stdout.decode("utf-8", "replace").strip().splitlines()
        err = p.stderr.decode("utf-8", "replace").strip().splitlines()
        detail = tail[-1] if tail else "(没有输出)"
        if p.returncode != 0 and err:
            detail += " ‖ stderr: " + " / ".join(err[-4:])
        r.add("键盘快捷键实机检查", p.returncode == 0,
              tail[-1] if tail else "(没有输出)")


    def check_motion(r):
        """界面动效在真浏览器里对吗（R-27 执行轮）。

        判七件事：page-in 入场 / 展开走 grid-rows / 侧栏 pane-in / 保存回执 /
        applyTop 绑定回归 / 模拟 prefers-reduced-motion 后全部归零。
        写接口在检查内部已换成桩（不会真写 mpv.conf）。
        **没有 Edge/Chrome 就跳过，不算失败** —— 同其余实机检查。
        """
        if importlib.util.find_spec("uidriver") is None and not (Path(__file__).parent / "uidriver.py").is_file():
            r.add("界面动效实机检查", True, "跳过（找不到 tools/uidriver.py）")
            return
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from uidriver import find_browser                            # noqa: PLC0415
        if not find_browser():
            r.add("界面动效实机检查", True, "跳过（本机没有 Edge/Chrome）")
            return
        p = subprocess.run([sys.executable, "-X", "utf8", "-u",
                            str(Path(__file__).parent / "verify.py"), "motion"],
                           capture_output=True, cwd=str(ROOT))
        tail = p.stdout.decode("utf-8", "replace").strip().splitlines()
        err = p.stderr.decode("utf-8", "replace").strip().splitlines()
        detail = tail[-1] if tail else "(没有输出)"
        if p.returncode != 0:
            # 一行不够定位：带出最后 8 行 stdout + stderr 尾部
            detail = " ‖ ".join(tail[-8:]) or "(没有输出)"
            if err:
                detail += " ‖ stderr: " + " / ".join(err[-4:])
        r.add("界面动效实机检查", p.returncode == 0, detail)


    def check_tauri(r):
        """Tauri 预览外壳（待做 §〇 第 15 项）。

        静态部分每次都跑（几毫秒，守「前端不复制副本 / 不开端口 / 退出先礼后兵」）。
        实机部分要 `cargo build` 出 exe 才有，**没有就跳过不算失败** ——
        预览版是可选形态，不该拖住每次发布自检；但 exe 在，它就必须过。
        """
        if not (ROOT / "tauri" / "src-tauri" / "tauri.conf.json").is_file():
            r.add("Tauri 预览外壳检查", True, "跳过（没有 tauri/ 脚手架）")
            return
        p = subprocess.run([sys.executable, "-X", "utf8",
                            str(Path(__file__).parent / "verify.py"), "tauri"],
                           capture_output=True, cwd=str(ROOT))
        tail = p.stdout.decode("utf-8", "replace").strip().splitlines()
        err = p.stderr.decode("utf-8", "replace").strip().splitlines()
        detail = tail[-1] if tail else "(没有输出)"
        if p.returncode != 0:
            detail = " ‖ ".join(tail[-6:]) or "(没有输出)"
            if err:
                detail += " ‖ stderr: " + " / ".join(err[-4:])
        r.add("Tauri 预览外壳检查", p.returncode == 0, detail)


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
        check_script_baseline(r)
        r.add("根目录白名单与 README 目录声明", cmd_layout() == 0, "")
        r.add("技术栈版本登记同源", cmd_stack() == 0, "")
        check_links(r, offline=args.offline)
        check_ui_nav(r)
        check_i18n(r)
        check_status(r)
        check_ctxmenu(r)
        check_hotkeys(r)
        check_motion(r)
        check_tauri(r)

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
        print("      --add-data \"LICENSE;.\"  --add-data \"docs;docs\"   ← 合规要求")
        print("      （界面文档与 NOTICE.txt 都在 docs/，打包时整目录带上）")
        print("   2. 打包产物附上 GPL-3.0 全文（就是上面那个 LICENSE）")
        return 0
    sys.exit(main())

# ==========================================================================
# docs（原 check_docs.py）
# ==========================================================================
def cmd_docs():
    """文档数字守门人：检查文档里的关键数字是否与实测一致。

    为什么要有它：这个项目吃过一次亏 —— README 说 20 个接口、另一份文档说 21 个，
    实际 23 个；测试数在三份文档里分别写成 181 / 167 / 199（实际 199）。
    人肉维护数字迟早会对不上，所以做成一个能跑的检查。

    用法（仓库根目录）：
        py -3 tools/verify.py docs
    退出码：0 = 全部一致；1 = 有对不上的地方。

    约定：`产品规划与路线图.md` 的「### 结论摘要」一节曾经是**故意保留的历史基线**，
    检查会跳过它 —— 别把基线数字刷成现值，那会让"改进了多少"看不出来。
    2026-10-09 拆文档时那一节已移出仓库（在 git 历史里），现在全文都要守；
    `baseline_span()` 留着，以后再放回类似的基线节时照旧能用。
    """
    import re
    import sys
    from pathlib import Path

    ROOT = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(ROOT))
    sys.stdout.reconfigure(encoding="utf-8")

    from webui import api, server  # noqa: E402

    # ⚠ 路由表在 W-4 之后搬到了 `webui/api.py`（表里存的是 server 里的属性名）。
    # 别改回去读 server.ROUTES_* —— 那三张表已经不在那儿了。
    routes = len(api.ROUTES_GET) + len(api.ROUTES_QUERY) + len(api.ROUTES_POST)
    pages = len(list((ROOT / "webui/static").glob("*.html")))
    modules = len([p for p in (ROOT / "core").glob("*.py") if p.name != "__init__.py"])


    def count_tests():
        """测试数 —— 用**真的跑一遍**的结果，不是 grep 出来的假数字。

        为什么较真：以前用正则数 `def test*` 会把手写的验证脚本也算进去，
        而那些脚本没有 `TestCase`，`unittest discover` **一个都不会收集**。
        实测过：归档 4 个 `_api_*.py` 之后 `Ran N tests` 一点没变，
        但 grep 出来的数字掉了 25 —— 说明那个数字一直是虚的。
        """
        import io
        import unittest
        suite = unittest.TestLoader().discover(str(ROOT / "tests"), top_level_dir=str(ROOT))
        res = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
        return res.testsRun, len(res.failures) + len(res.errors)


    tests, failures = count_tests()

    from core.options_db import load_db  # noqa: E402

    _db = load_db()
    n_options = _db["meta"].get("count", 0)      # 能写进配置的条数（滤掉命令行专用项之后）
    n_zh = _db["meta"].get("with_zh", 0)

    CHECKS = [
        # 只认「历史上真的出现过的测试数」，不能写 \d{3} —— 那会把 829（选项数）、
        # 726（中文说明数）、117（精选项数）全当成测试数来报。
        # ⚠ 每次测试数变了，**这里也要跟着加**，否则新数字不在白名单里 = 没人守它。
        #
        # ⚠⚠ 白名单有个**天生的盲区**：写错的数字要是不在名单里，就永远匹配不上，
        # 也就永远查不出来（实测：把 424 手滑成 420，这个模式一个字都不匹配，
        # 检查照样报"一致 ✓"）。所以底下还有一条「按上下文兜底」的规则。
        (r"(?<![\d])(181|199|220|222|228|236|259|287|327|352|358|360|392|424|444|476|497|509|547|548|575|595|606|615|645|648|649|650|654|701|705|717|748|765|781|784) 项",
         tests, "测试数"),
        # 兜底：**三位数**的 `N 项` 出现在「测试」附近时，必须等于实测总数。
        #
        # 为什么需要它：白名单只认「曾经出现过的数字」，所以把现值打错一位
        # （424 → 420）会**一个字都匹配不上**，检查照样报"一致 ✓"。实测过。
        # 为什么用"三位数"当判据：实测过全部五份文档，模块分项测试数最大是 **42**
        # （`vpy.py` 17、`conflicts.py` 28、`test_dlcenter.py` 23…），
        # 而总数一直是三位数。所以三位数 ≈ 总数，这个界限不会误伤分项。
        # 若哪天某个模块的分项测试数破百，这条会开始误报 —— 那时再改判据。
        (r"(?<![\d])(\d{3})(?=\s*项)[^\n]{0,12}?测试", tests, "测试数（按上下文）"),
        (r"测试[^\n]{0,12}?(?<![\d])(\d{3})(?=\s*项)", tests, "测试数（按上下文）"),
        (r"(?<![\d])(20|21|23|29|31|32|37|39|42) 个(?:JSON )?接口", routes, "接口数"),
        (r"（(16|19|20|23|24|25) 个(?:逻辑)?模块）", modules, "模块数"),
        # ⚠ 下面两条是"按说法兜底"，理由和测试数那条一样：白名单只认出现过的数字，
        # 写错的（`19 个核心模块` 而实际 24）永远匹配不上，等于没人守。
        # 实测过：路线图里「19 个核心模块 / 8 个界面页面」和「页面共 8 个」
        # 三处都过期了，而 check_docs 一路报"一致 ✓"。
        (r"(?<![\d])(\d+)\s*个核心模块", modules, "核心模块数"),
        (r"(?<![\d])(\d+)\s*个(?:界面)?页面", pages, "页面数（按说法）"),
        (r"页面共\s*(?<![\d])(\d+)\s*个", pages, "页面数（按说法）"),
        (r"\| 界面页面 \| (\d+) 个", pages, "页面数"),
        # 选项库条数：829 是数据文件里的原始条数（允许出现），813 是界面可用的
        (r"\*\*(\d+) 项全量选项库\*\*", n_options, "选项库条数"),
        (r"(\d+) 项可写进配置的选项", n_options, "选项库条数"),
    ]


    def baseline_span(text):
        """「### 结论摘要」整段是故意保留的历史基线，检查时跳过。"""
        m = re.search(r"^### 结论摘要.*?(?=^### )", text, re.S | re.M)
        return m.span() if m else None


    def line_span(text, pos):
        """`pos` 所在那一行的 [起, 止)。用来给匹配做上下文判断。"""
        a = text.rfind("\n", 0, pos) + 1
        b = text.find("\n", pos)
        return a, (len(text) if b < 0 else b)


    # 这一行是在讲"删掉了多少东西"时，里面的数字不是现状，跳过。
    # 实测踩过：X-4-7 那行写「顶栏逻辑在 4 个页面里各抄了一遍」，被判成"页面数写 4"。
    _HISTORICAL_MARKERS = ("已删", "已归档", "曾经", "删掉了", "归档而非删除")


    def main():
        print(f"实测: 接口 {routes} / 页面 {pages} / 模块 {modules} / "
              f"测试 {tests}（真的跑了一遍，失败 {failures} 项）")
        print(f"      选项库 {n_options} 项可写进配置（含中文说明 {n_zh} 条）\n")
        bad_total = 0
        # 2026-09-14 清理过一轮开发文档：已完成清单 / 问题清单 / 制作与发布文档都删了
        # （在 git 历史里）。这里只剩真正还在的文档，**加新文档记得同步这份列表**。
        for name in ("docs/README.zh-CN.md", "README.md", "docs/产品规划与路线图.md",
                     # ⚠ 2026-10-09 补齐：这三份以前**不在检查范围里**，
                     # 数字写错也没人拦（它们同样是用户与打包会读到的文档）。
                     "docs/入门指南.md", "docs/致谢与许可.md",
                     "docs/MPV_Shader搭配说明书.md"):
            p = ROOT / name
            if not p.is_file():
                continue
            t = p.read_text(encoding="utf-8")
            span = baseline_span(t)
            bad = []
            seen = set()
            for pat, want, what in CHECKS:
                for m in re.finditer(pat, t):
                    if span and span[0] <= m.start() < span[1]:
                        continue
                    a, b = line_span(t, m.start())
                    line_text = t[a:b]
                    # 「按上下文 / 按说法」那几条：只在讲现状的行上判定
                    if "按上下文" in what or "按说法" in what:
                        if any(k in line_text for k in _HISTORICAL_MARKERS):
                            continue
                    if "按上下文" in what and "测试" not in line_text:
                        continue
                    # ⚠ 还要排掉"数据条数"的说法：`726 项有说明` / `338 项有格式提示`
                    # 这类是**选项库的覆盖率**，不是测试数。它们所在的行里往往也带"测试"
                    # （表格的"验证方式"列就写着"测试"），只按"这一行有没有测试"判会误报
                    # —— 实测踩过：338 被当成测试数报了出来。
                    if "按上下文" in what and re.search(r"\d+\s*项有", line_text):
                        continue
                    line = t[:m.start()].count("\n") + 1
                    key = (line, want)
                    if key in seen:
                        continue          # 两条规则命中同一处，只报一次
                    seen.add(key)
                    got = int(re.search(r"\d+", m.group(0)).group())
                    if got != want:
                        bad.append(f"{what} 写 {got} 实际 {want} @{line}行")
            bad_total += len(bad)
            print(f"  {name:26} " + ("一致 ✓" if not bad else "；".join(bad)))
        print(f"\n不一致处: {bad_total}")
        return 1 if bad_total else 0
    sys.exit(main())

# ==========================================================================
# topnav（原 check_topnav.py）
# ==========================================================================
def cmd_topnav():
    """U-1 实机验证：9 个页面的顶栏是否都有「体检 / 快捷键 / 下载中心」常驻入口。

    为什么要真机跑：这个功能**完全是 JS 注入的**，静态看 HTML 一个入口都看不到。
    只有让真实浏览器把 api.js 跑一遍，才能知道注入有没有生效、有没有撞上页面自己的
    变量或 DOM 结构（下载中心的入参就叫 target，正是这类坑的高发区）。

    顺带验证「当前页」那一条是不可点的指示、其它两条是真链接。

    用法（会自己起一个临时后端，端口自动挑）：
        py -3 tools/verify.py topnav
    """
    import json
    import socket
    import subprocess
    import sys
    import time
    import urllib.request
    from pathlib import Path

    ROOT = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "tools"))

    from uidriver import Checker, connect, launch, stop, wait_for, wait_page   # noqa: E402

    SHOTS = ROOT / "_shots"
    PAGES = [
        ("index.html", "index"), ("basic.html", "basic"), ("advanced.html", "advanced"),
        ("expert.html", "expert"), ("analyze.html", "analyze"), ("keys.html", "keys"),
        ("downloads.html", "downloads"), ("guide.html", "guide"), ("hell.html", "hell"),
    ]
    WANT = [("analyze.html", "配置体检", "🩺"),
            ("keys.html", "快捷键", "⌨️"),
            ("downloads.html", "下载中心", "📦")]
    # 哪个页面是「导航页」——在这几页上必须有一条不可点的「当前页」指示
    NAV_PAGES = {"analyze": "analyze.html", "keys": "keys.html", "downloads": "downloads.html"}

    # 顶栏「就绪」条件：.topnav 存在且三个入口都已注入。
    # 为什么要它：顶栏是 JS 注入的，注入完成的时刻随机 —— 固定 sleep 在 CI 慢机上
    # 会不够（2026-10-09 实测：docs-only 提交在 CI 上间歇红过一次，就红在这）。
    # 所以导航后轮询这个条件，而不是猜一个时长。
    TOPNAV_READY = ("(function(){var n=document.querySelector('.topnav');"
                    "return n && n.children.length >= 3;})()")

    # 每页读一次顶栏：返回注入结果的原始结构，判定都放在 Python 里做
    PROBE = """
    (() => {
      const nav = document.querySelector('.topnav');
      if (!nav) return {found: false};
      const pill = el => ({
        tag: el.tagName.toLowerCase(),
        label: (el.querySelector('span:not(.topnav-ico):not(.topnav-dot)') || {}).textContent || '',
        href: el.getAttribute('href') || '',
        ico: (el.querySelector('.topnav-ico') || {}).textContent || '',
        clickable: el.tagName.toLowerCase() === 'a',
        current: el.getAttribute('aria-current') === 'page'
      });
      return {
        found: true,
        page: document.body.dataset.page || '',
        items: [...nav.children].map(pill),
        // 也看一眼页面本身有没有报错（注入代码抛异常的话这里会体现出来）
        hasTopbar: !!document.querySelector('.topbar')
      };
    })()
    """


    # 读「实际生效的样式」。为什么要这一项：
    # 第一版给导航项套了 class="btn small topnav-link"，然后在 CSS 里写
    # `.topnav-link{border:none;background:none}` —— 权重同为 (0,2,0) 但 `.btn.small`
    # 在后面，把导航项全变成了带框的按钮，当前页那条更是「按钮框 + 下划线」两套视觉打架。
    # 光看截图只会以为"样式没调好"，是读计算样式才定位到根因的。
    # 这条断言就是防止有人（包括我）再把按钮 class 加回来。
    STYLE_PROBE = """
    (() => {
      const pick = el => {
        const cs = getComputedStyle(el), a = getComputedStyle(el, '::after');
        return {cls: el.className, borderW: cs.borderTopWidth, bg: cs.backgroundColor,
                color: cs.color, weight: cs.fontWeight,
                afterBg: a.backgroundColor, afterH: a.height, afterContent: a.content};
      };
      const nav = document.querySelector('.topnav');
      return {
        links: [...nav.querySelectorAll('.topnav-link')].map(pick),
        cur: nav.querySelector('.topnav-cur') ? pick(nav.querySelector('.topnav-cur')) : null
      };
    })()
    """

    ACCENT_RGB = "rgb(106, 168, 255)"
    TRANSPARENT = "rgba(0, 0, 0, 0)"


    def free_port():
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        p = s.getsockname()[1]
        s.close()
        return p


    def start_server(port):
        proc = subprocess.Popen(
            [sys.executable, "-X", "utf8", str(ROOT / "webui" / "server.py"),
             "--port", str(port), "--no-window"],
            cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=1) as f:
                    json.load(f)
                return proc
            except Exception:
                if proc.poll() is not None:
                    sys.exit("后端启动失败（进程已退出）")
                time.sleep(0.4)
        proc.kill()
        sys.exit("后端 30 秒内没起来")


    def main():
        port, cdp_port = free_port(), free_port()
        srv = browser = None
        c = Checker()
        try:
            srv = start_server(port)
            print(f"后端已起：http://127.0.0.1:{port}\n")
            browser = launch(cdp_port)
            cdp = connect(cdp_port)
            SHOTS.mkdir(exist_ok=True)

            base = f"http://127.0.0.1:{port}/"
            for name, page in PAGES:
                wait_page(cdp, base + name, wait_s=2.2)
                # 等「顶栏注入完成」这个条件，而不是只靠上面的固定 sleep：
                # CI 慢机上固定 2.2s 可能不够，注入没完成探针就落空（间歇红）。
                wait_for(cdp, TOPNAV_READY, timeout_s=10)
                got = cdp.js(PROBE)
                print(f"—— {name} ——")
                if not c(f"{name}：顶栏注入了 .topnav", bool(got.get("found"))):
                    continue
                # 链接地址：**可点的那两条**必须地址正确；
                # 当前页那条是不可点的 span，本来就该没有 href（空串才是对的）
                items = got["items"]
                labels = [i["label"] for i in items]
                c(f"{name}：三个入口齐全，顺序一致",
                  labels == [w[1] for w in WANT], f"实际 {labels}")

                icons = {i["label"]: i["ico"] for i in items}
                c(f"{name}：图标正确",
                  all(icons.get(lbl) == ico for _, lbl, ico in WANT), f"实际 {icons}")

                bad_href = []
                for href, lbl, _ in WANT:
                    it = next((i for i in items if i["label"] == lbl), None)
                    if it is None:
                        bad_href.append(f"{lbl}=缺失")
                    elif it["current"]:
                        if it["href"]:
                            bad_href.append(f"{lbl}=当前页却带了地址 {it['href']!r}")
                    elif it["href"] != href:
                        bad_href.append(f"{lbl}={it['href']!r} 应为 {href!r}")
                c(f"{name}：链接地址正确（可点的对、当前页无地址）",
                  not bad_href, "；".join(bad_href))

                # 当前页那一条必须不可点，其它两条必须可点
                cur = [i for i in items if i["current"]]
                if page in NAV_PAGES:
                    c(f"{name}：当前页显示为不可点指示",
                      len(cur) == 1 and not cur[0]["clickable"],
                      f"current={[(i['label'], i['clickable']) for i in cur]}")
                    want_lbl = next(lbl for href, lbl, _ in WANT if href == NAV_PAGES[page])
                    c(f"{name}：当前页指示指向自己（{want_lbl}）",
                      len(cur) == 1 and cur[0]["label"] == want_lbl,
                      f"current={[i['label'] for i in cur]}")
                else:
                    c(f"{name}：不是导航页，不应有「当前页」标记", not cur,
                      f"current={[i['label'] for i in cur]}")
                    c(f"{name}：三个入口都可点",
                      all(i["clickable"] for i in items),
                      f"实际 {[(i['label'], i['clickable']) for i in items]}")
                c(f"{name}：页面保留了顶栏", got["hasTopbar"])

                # 样式：导航项必须是"文字"，不能带上按钮的边框底色
                st = cdp.js(STYLE_PROBE)
                bad = []
                for i, li in enumerate(st["links"]):
                    if li["borderW"] != "0px":
                        bad.append(f"第{i+1}项有边框 {li['borderW']}")
                    if li["bg"] != TRANSPARENT:
                        bad.append(f"第{i+1}项有底色 {li['bg']}")
                    if "btn" in li["cls"]:
                        bad.append(f"第{i+1}项还带着按钮 class: {li['cls']}")
                c(f"{name}：导航项没有按钮样式（无边框/无底色）", not bad, "；".join(bad))

                if st["cur"]:
                    cur_ok = (st["cur"]["color"] == ACCENT_RGB
                              and st["cur"]["afterBg"] == ACCENT_RGB
                              and st["cur"]["afterH"] == "2px"
                              and st["cur"]["afterContent"] != "none"
                              and st["cur"]["borderW"] == "0px"
                              and "btn" not in st["cur"]["cls"])
                    c(f"{name}：当前页是主色 + 2px 下划线，且不带按钮框", cur_ok,
                      f"color={st['cur']['color']} 下划线={st['cur']['afterBg']}/"
                      f"{st['cur']['afterH']} 边框={st['cur']['borderW']} cls={st['cur']['cls']}")
                cdp.shot(str(SHOTS / f"60_顶栏_{page}.png"))
            print()
            return c.done()
        finally:
            try:
                stop(browser)
            except Exception:
                pass
            if srv:
                srv.terminate()
                try:
                    srv.wait(timeout=10)
                except Exception:
                    srv.kill()
    sys.exit(main())

# ==========================================================================
# i18n（语言切换机制）
# ==========================================================================

def cmd_i18n():
    """i18n 机制实机验证：切过去真的变英文吗？两种语言的键对得上吗？

    为什么要真机跑：语言切换是**运行时替换 DOM 文本**，
    静态看 index.html 只能看到中文硬编码。只有真让浏览器跑一遍，才能确认
    「点了按钮文字真的变了」「刷新后偏好还在」「译文里没有漏填的 {占位符}」。

    分两半，判定依据不同：

    * **静态半（不需要浏览器）**：两张语言表的键集合必须完全一致
      （不一致 = 切过去有一片还是中文）；译文里出现的每个 `{占位符}`
      都必须能在 VARS 里找到（找不到 = 界面上会直接显示 `{optsTotal}`）。
    * **动态半（需要 Edge/Chrome）**：真点一下切换按钮，比对前后文本。

    用法（会自己起一个临时后端，端口自动挑）：
        py -3 tools/verify.py i18n
    """
    import json
    import re
    import socket
    import subprocess
    import sys
    import time
    import urllib.request
    from pathlib import Path

    ROOT = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "tools"))

    from uidriver import Checker, connect, launch, stop, wait_page   # noqa: PLC0415

    c = Checker()

    # ---------- 静态半：键集合与占位符，纯 Python 判定 ----------
    src = (ROOT / "webui" / "static" / "i18n.js").read_text(encoding="utf-8")
    html = (ROOT / "webui" / "static" / "index.html").read_text(encoding="utf-8")

    try:
        i_zh = src.index("'zh-CN': {")
        i_en = src.index("'en': {")
        i_end = src.index("var current")
    except ValueError:
        c("i18n.js 里能定位到两张语言表", False,
          "找不到 'zh-CN' / 'en' / 'var current' 这三处标记（改动结构后要同步这里）")
        return c.done()

    KEY = re.compile(r"^\s*'([A-Za-z0-9_.]+)':\s", re.M)
    zh_src = src[i_zh + len("'zh-CN': {"):i_en]
    en_src = src[i_en + len("'en': {"):i_end]
    zh_keys = set(KEY.findall(zh_src))
    en_keys = set(KEY.findall(en_src))

    c("两张语言表都非空", bool(zh_keys) and bool(en_keys),
      f"zh={len(zh_keys)} 条 / en={len(en_keys)} 条")

    only_zh = sorted(zh_keys - en_keys)
    only_en = sorted(en_keys - zh_keys)
    c("两种语言的键集合完全一致", not only_zh and not only_en,
      f"只在中文有：{only_zh}；只在英文有：{only_en}")

    m = re.search(r"var VARS = \{(.*?)\};", src, re.S)
    var_keys = set(re.findall(r"(\w+):", m.group(1))) if m else set()
    # 运行时才填的占位名（值由调用方传 t(key, {changes: 3})）—— 也要认得，
    # 否则会误报成"漏填"。见 i18n.js 里 RUNTIME_VARS 的注释。
    m2 = re.search(r"var RUNTIME_VARS = \[(.*?)\]", src, re.S)
    if m2:
        var_keys |= set(re.findall(r"'(\w+)'", m2.group(1)))
    holes = set(re.findall(r"\{(\w+)\}", zh_src + en_src)) - var_keys
    c("译文里的占位符都能在 VARS 里找到（没有漏填的数字）", not holes,
      f"找不到值的占位符：{sorted(holes)}")

    used = set(re.findall(r'data-i18n(?:-html|-title|-ph)?="([^"]+)"', html))
    used |= set(re.findall(r"I18N\.t\('([^']+)'\)", html))
    missing = sorted(k for k in used if k not in zh_keys or k not in en_keys)
    c("index.html 用到的键两种语言都有", not missing, f"缺：{missing}")

    # ---------- 动态半：真浏览器点一下 ----------
    PROBE = """
    (() => {
      const btn = document.querySelector('[data-lang-toggle]');
      return {
        h1: (document.querySelector('h1') || {}).textContent || '',
        lang: document.documentElement.lang,
        btn: btn ? btn.textContent : '',
        hasBtn: !!btn,
        braces: document.body.innerText.match(/\\{[A-Za-z]\\w*\\}/g) || []
      };
    })()
    """
    CLICK = ("(() => { const b = document.querySelector('[data-lang-toggle]');"
             " if (b) { b.click(); return true; } return false; })()")


    def free_port():
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        p = s.getsockname()[1]
        s.close()
        return p


    def start_server(port):
        proc = subprocess.Popen(
            [sys.executable, "-X", "utf8", str(ROOT / "webui" / "server.py"),
             "--port", str(port), "--no-window"],
            cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=1) as f:
                    json.load(f)
                return proc
            except Exception:
                if proc.poll() is not None:
                    sys.exit("后端启动失败（进程已退出）")
                time.sleep(0.4)
        proc.kill()
        sys.exit("后端 30 秒内没起来")


    def main():
        port, cdp_port = free_port(), free_port()
        srv = browser = None
        try:
            return _run(port, cdp_port)
        except BaseException:
            # CI 上 subprocess 的 stdout 是块缓冲——崩在这里时上面的进度全靠
            # 退出时 flush；但 traceback 只进 stderr，包装器旧版看不到。
            # 现在：栈直接打到 stdout + 无缓冲运行，双保险。
            import traceback
            traceback.print_exc()
            sys.stdout.flush()
            print("❌ motion 子进程异常退出（栈见上）")
            return 1

    def _run(port, cdp_port):
        srv = browser = None
        try:
            srv = start_server(port)
            print(f"后端已起：http://127.0.0.1:{port}\n")
            browser = launch(cdp_port)
            cdp = connect(cdp_port)

            base = f"http://127.0.0.1:{port}/"
            wait_page(cdp, base + "index.html", wait_s=2.2)
            a = cdp.js(PROBE)
            print("—— 切换前 ——")
            c("页面上有语言切换按钮", bool(a.get("hasBtn")))
            c("默认语言是 zh-CN", a.get("lang") == "zh-CN", f"lang={a.get('lang')!r}")
            c("默认显示中文标题", a.get("h1") == "选择使用模式", f"h1={a.get('h1')!r}")
            c("中文下没有未替换的占位符", not a.get("braces"), f"{a.get('braces')}")

            cdp.js(CLICK)
            time.sleep(0.4)
            b = cdp.js(PROBE)
            print("\n—— 切换后 ——")
            c("点一下之后语言变成 en", b.get("lang") == "en", f"lang={b.get('lang')!r}")
            c("标题真的换成了英文", b.get("h1") == "Choose a mode", f"h1={b.get('h1')!r}")
            c("英文下没有未替换的占位符", not b.get("braces"), f"{b.get('braces')}")
            c("按钮自身文案跟着变", "English" in (b.get("btn") or ""), f"btn={b.get('btn')!r}")

            # 换个查询串强制重新载入，验证 localStorage 里的偏好还在
            wait_page(cdp, base + "index.html?reload=1", wait_s=2.2)
            d = cdp.js(PROBE)
            print("\n—— 刷新后 ——")
            c("刷新后语言偏好还在（localStorage）", d.get("lang") == "en",
              f"lang={d.get('lang')!r}")
            c("刷新后标题仍是英文", d.get("h1") == "Choose a mode", f"h1={d.get('h1')!r}")

            # ---------- 9 个页面：切换入口都在吗？切过去顶栏还剩中文吗？ ----------
            # 判定分两档，别混为一谈：
            #   * 顶栏（.topbar）**必须**一个汉字都不剩 —— 这是全站共用的一层，
            #     翻不干净说明词条表有洞，是缺陷。
            #     标了 data-no-i18n 的不算：那是文件名、键名这类标识符，
            #     本来就不该翻（guide 顶栏显示的 `入门指南.md` 就是这种）。
            #   * 整页剩余中文只**测量不判定** —— 726 条选项说明按设计不翻译
            #     （取 mpv 官方英文原文，那是另一件事，见 DECISIONS.md 2026-09-14），
            #     硬判「一个汉字都不许剩」只会逼人去关门禁。把数字打出来，剩余工作量才可见。
            PAGES = ["index.html", "basic.html", "advanced.html", "expert.html",
                     "analyze.html", "keys.html", "downloads.html", "guide.html",
                     "hell.html"]
            RESET = "(function(){ try { localStorage.removeItem('mpvcb-lang'); } catch(e){} return 1; })()"
            HAN = (r"(function(){"
                   r" var RE=/[\u4e00-\u9fff]/g;"
                   r" var count=function(root,skip){"
                   r"   var tw=document.createTreeWalker(root,NodeFilter.SHOW_TEXT,null);"
                   r"   var n=0,x,m;"
                   r"   while((x=tw.nextNode())){"
                   r"     var p=x.parentNode; if(!p) continue;"
                   r"     if(p.nodeName==='SCRIPT'||p.nodeName==='STYLE') continue;"
                   r"     if(skip&&p.closest&&p.closest(skip)) continue;"
                   r"     m=String(x.nodeValue||'').match(RE); if(m) n+=m.length;"
                   r"   } return n;};"
                   r" var b=document.querySelector('.topbar');"
                   r" return {body:count(document.body,null),"
                   r"         topbar:b?count(b,'[data-no-i18n]'):0,"
                   r"         hasTopbar:!!b,"
                   r"         hasBtn:!!document.querySelector('[data-lang-toggle]'),"
                   r"         lang:document.documentElement.lang};})()")

            print("\n—— 9 个页面 ——")
            left_total = base_total = 0
            for name in PAGES:
                wait_page(cdp, base + name, wait_s=2.2)
                cdp.js(RESET)
                wait_page(cdp, base + name + "?i18n=1", wait_s=2.2)
                before = cdp.js(HAN)
                cdp.js(CLICK)
                time.sleep(0.5)
                after = cdp.js(HAN)
                base_total += before.get("body", 0)
                left_total += after.get("body", 0)
                c(f"{name}：有语言切换按钮", bool(after.get("hasBtn")))
                c(f"{name}：切过去后顶栏没有中文", after.get("topbar") == 0,
                  f"顶栏还剩 {after.get('topbar')} 个汉字")
                c(f"{name}：切过去后中文确实减少了",
                  after.get("body", 0) < before.get("body", 0),
                  f"切前 {before.get('body')} → 切后 {after.get('body')}")
                print(f"    {name}：切前 {before.get('body')} 汉字 → 切后 {after.get('body')} 汉字")

            if base_total:
                print(f"\n    合计：切前 {base_total} → 切后 {left_total}"
                      f"（剩余 {left_total * 100 // base_total}%，"
                      f"主要是按设计不翻译的选项说明与未收录词条）")
            print()
            return c.done()
        finally:
            try:
                stop(browser)
            except Exception:
                pass
            if srv:
                srv.terminate()
                try:
                    srv.wait(timeout=10)
                except Exception:
                    srv.kill()
    sys.exit(main())


# ==========================================================================
# status（状态栏 / 后端离线提示 / 请求进度）
# ==========================================================================

def cmd_status():
    """界面打磨第一批的实机验证：状态栏在吗？后端挂了会说话吗？

    为什么要真机跑：这三样全是 JS 注入的 DOM，静态看 HTML 一样都看不到；
    「后端离线横幅会不会弹出来」更是只有真跑一遍才知道。

    ⚠ 测离线**不能靠杀后端进程**：服务没了，页面根本加载不出来，没法测。
    所以这里把 `API.status` 换成抛错的桩，再调 `APP.ping()` —— 确定性高、也不用等心跳。

    用法（会自己起一个临时后端，端口自动挑）：
        py -3 tools/verify.py status
    """
    import json
    import socket
    import subprocess
    import sys
    import time
    import urllib.request
    from pathlib import Path

    ROOT = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "tools"))

    from uidriver import Checker, connect, launch, stop, wait_page   # noqa: PLC0415

    c = Checker()

    PROBE = """
    (() => {
      const bar = document.querySelector('.statusbar');
      const ob  = document.querySelector('.offline-banner');
      const q = (r, s) => (r && r.querySelector(s)) ? (r.querySelector(s).textContent || '') : '';
      return {
        hasBar: !!bar,
        on: bar ? bar.classList.contains('is-on') : false,
        off: bar ? bar.classList.contains('is-off') : false,
        target: q(bar, '.sb-target'),
        backend: q(bar, '.sb-backend .sb-text'),
        changes: q(bar, '.sb-changes'),
        hasBanner: !!ob,
        hasBusy: !!document.querySelector('.busy-bar'),
        bodyPad: getComputedStyle(document.body).paddingBottom
      };
    })()
    """
    # 把 status 换成抛错的桩，模拟后端没了。
    # ⚠ 写 `API.status`，不要写 `window.API.status` —— api.js 里 API 是顶层 const，
    #   不是 window 的属性（这是它防污染的手段），写成 window.API 会直接 TypeError。
    STUB = ("(() => { API.status = () => Promise.reject(new Error('boom'));"
            " return true; })()")


    def free_port():
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        p = s.getsockname()[1]
        s.close()
        return p


    def start_server(port):
        proc = subprocess.Popen(
            [sys.executable, "-X", "utf8", str(ROOT / "webui" / "server.py"),
             "--port", str(port), "--no-window"],
            cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=1) as f:
                    json.load(f)
                return proc
            except Exception:
                if proc.poll() is not None:
                    sys.exit("后端启动失败（进程已退出）")
                time.sleep(0.4)
        proc.kill()
        sys.exit("后端 30 秒内没起来")


    def main():
        port, cdp_port = free_port(), free_port()
        srv = browser = None
        try:
            return _run(port, cdp_port)
        except BaseException:
            # CI 上 subprocess 的 stdout 是块缓冲——崩在这里时上面的进度全靠
            # 退出时 flush；但 traceback 只进 stderr，包装器旧版看不到。
            # 现在：栈直接打到 stdout + 无缓冲运行，双保险。
            import traceback
            traceback.print_exc()
            sys.stdout.flush()
            print("❌ motion 子进程异常退出（栈见上）")
            return 1

    def _run(port, cdp_port):
        srv = browser = None
        try:
            srv = start_server(port)
            print(f"后端已起：http://127.0.0.1:{port}\n")
            browser = launch(cdp_port)
            cdp = connect(cdp_port)
            base = f"http://127.0.0.1:{port}/"

            wait_page(cdp, base + "index.html", wait_s=2.5)
            time.sleep(1.2)                      # 等第一次 ping 回来
            a = cdp.js(PROBE)
            print("—— 后端在线 ——")
            c("状态栏注入了", bool(a.get("hasBar")))
            c("有请求进度条元素", bool(a.get("hasBusy")))
            c("后端在线时状态栏标记为 is-on", a.get("on") is True,
              f"on={a.get('on')} off={a.get('off')}")
            tgt = (a.get("target") or "").strip()
            if not tgt or "未选择" in tgt:
                # 机器上没有 mpv 配置目录时，状态栏本来就没有东西可显示 ——
                # 这是**环境缺件**，不是状态栏坏了。按本项目的约定：缺件跳过，不算失败。
                # 2026-10-09：CI 上没有 mpv，这一项被判成失败，属误报。
                c("状态栏读到了目标配置路径", True,
                  f"跳过（本机没有 mpv 配置目录，target={tgt!r}）")
            else:
                c("状态栏读到了目标配置路径", "mpv" in tgt.lower(),
                  f"target={tgt!r}")
            c("给了 body 底部留白（状态栏不盖内容）",
              a.get("bodyPad") not in (None, "0px"), f"padding-bottom={a.get('bodyPad')}")
            print(f"    后端状态文字：{a.get('backend')!r}")

            # 改动数：页面用 MPVCB.setChanges 告诉状态栏
            cdp.js("(() => { window.MPVCB.setChanges(3); return true; })()")
            b = cdp.js(PROBE)
            print("\n—— 改动数 ——")
            c("APP.setChanges 能刷进状态栏", "3" in (b.get("changes") or ""),
              f"changes={b.get('changes')!r}")

            # 后端"没了"：换成抛错的桩再 ping 一次
            cdp.js(STUB)
            cdp.js("(() => window.MPVCB.ping())()")
            time.sleep(0.8)
            d = cdp.js(PROBE)
            print("\n—— 后端离线（桩） ——")
            c("后端离线时状态栏标记为 is-off", d.get("off") is True,
              f"on={d.get('on')} off={d.get('off')}")
            c("弹出了离线横幅（不再白屏）", bool(d.get("hasBanner")))

            # 恢复：重新载入页面（桩随之消失），横幅应消失、状态回到在线
            wait_page(cdp, base + "index.html?back=1", wait_s=2.5)
            time.sleep(1.2)
            e = cdp.js(PROBE)
            print("\n—— 后端恢复 ——")
            c("后端恢复后横幅消失", not e.get("hasBanner"))
            c("后端恢复后状态栏回到 is-on", e.get("on") is True,
              f"on={e.get('on')} off={e.get('off')}")
            print()
            return c.done()
        finally:
            try:
                stop(browser)
            except Exception:
                pass
            if srv:
                srv.terminate()
                try:
                    srv.wait(timeout=10)
                except Exception:
                    srv.kill()
    sys.exit(main())


# ==========================================================================
# ctxmenu（右键菜单）
# ==========================================================================

def cmd_ctxmenu():
    """右键菜单的实机验证：能弹吗？动作真的做了吗？Esc 能关吗？

    为什么要真机跑：菜单是 JS 注入的；「恢复默认」走的是**模拟点击页面自己的
    勾选框**——有没有真的把状态改回去，只有跑了才知道。
    剪贴板没法直接读，所以把 `navigator.clipboard.writeText` 换成记录的桩。

    用法（会自己起一个临时后端，端口自动挑）：
        py -3 tools/verify.py ctxmenu
    """
    import json
    import socket
    import subprocess
    import sys
    import time
    import urllib.request
    from pathlib import Path

    ROOT = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "tools"))

    from uidriver import Checker, connect, launch, stop, wait_page   # noqa: PLC0415

    c = Checker()

    STUB_CLIP = ("(() => { window.__copied = null;"
                 " navigator.clipboard.writeText = t => { window.__copied = String(t);"
                 " return Promise.resolve(); }; return true; })()")
    PROBE = """
    (() => {
      const m = document.querySelector('.ctx-menu');
      const rows = Array.from(document.querySelectorAll('.opt.on'));
      return {
        menu: !!m,
        items: m ? Array.from(m.querySelectorAll('.ctx-item')).map(b => b.textContent) : [],
        checked: rows.length,
        firstKey: rows.length ? rows[0].dataset.key : ''
      };
    })()
    """
    OPEN = ("(() => { const r = document.querySelector('.opt.on');"
            " if (!r) return false;"
            " r.dispatchEvent(new MouseEvent('contextmenu',"
            " {bubbles:true, cancelable:true, clientX:40, clientY:60}));"
            " return r.dataset.key; })()")
    ESC = "(() => { document.dispatchEvent(new KeyboardEvent('keydown', {key:'Escape', bubbles:true})); return true; })()"
    RESET = ("(() => { const it = Array.from(document.querySelectorAll('.ctx-item'))"
             "   .find(b => b.dataset.act === 'reset');"
             " if (!it) return false; it.click(); return true; })()")
    COPYKEY = ("(() => { const it = Array.from(document.querySelectorAll('.ctx-item'))"
               "   .find(b => b.dataset.act === 'copykey');"
               " if (!it) return false; it.click(); return true; })()")
    ELSEWHERE = ("(() => { document.body.dispatchEvent(new MouseEvent('contextmenu',"
                 " {bubbles:true, cancelable:true, clientX:5, clientY:5})); return true; })()")


    def free_port():
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        p = s.getsockname()[1]
        s.close()
        return p


    def start_server(port):
        proc = subprocess.Popen(
            [sys.executable, "-X", "utf8", str(ROOT / "webui" / "server.py"),
             "--port", str(port), "--no-window"],
            cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=1) as f:
                    json.load(f)
                return proc
            except Exception:
                if proc.poll() is not None:
                    sys.exit("后端启动失败（进程已退出）")
                time.sleep(0.4)
        proc.kill()
        sys.exit("后端 30 秒内没起来")


    def main():
        port, cdp_port = free_port(), free_port()
        srv = browser = None
        try:
            return _run(port, cdp_port)
        except BaseException:
            # CI 上 subprocess 的 stdout 是块缓冲——崩在这里时上面的进度全靠
            # 退出时 flush；但 traceback 只进 stderr，包装器旧版看不到。
            # 现在：栈直接打到 stdout + 无缓冲运行，双保险。
            import traceback
            traceback.print_exc()
            sys.stdout.flush()
            print("❌ motion 子进程异常退出（栈见上）")
            return 1

    def _run(port, cdp_port):
        srv = browser = None
        try:
            srv = start_server(port)
            print(f"后端已起：http://127.0.0.1:{port}\n")
            browser = launch(cdp_port)
            cdp = connect(cdp_port)
            base = f"http://127.0.0.1:{port}/"

            # ⚠ 不用 expert 页自己的选项行：expert 是「本地配置」视图，
            #   靠 localStorage 里上一次会话的状态（loadLocal）才有内容，
            #   全新浏览器里它就是空的 —— 这是既有行为，不是本功能的缺陷。
            #   所以注入一行合成的 .opt，测的正是 api.js 里那套委托逻辑。
            SEED = (
                "(function(){"
                " document.getElementById('panes').innerHTML ="
                "  '<div class=\"opt on\" data-key=\"--test-key\"><div class=\"opt-head\">'"
                "  + '<input type=\"checkbox\" data-role=\"check\" checked>'"
                "  + '<label data-role=\"label\">测试项</label>'"
                "  + '<div class=\"right\"><button class=\"icon-btn\" data-role=\"info\">i</button></div>'"
                "  + '</div></div>';"
                " APP.values['--test-key'] = 'yes';"
                " window.__infoClicked = 0;"
                " document.querySelector('.opt [data-role=info]')"
                "   .addEventListener('click', function(){ window.__infoClicked++; });"
                " return true; })()"
            )

            wait_page(cdp, base + "expert.html", wait_s=2.5)
            cdp.js(SEED)
            cdp.js(STUB_CLIP)
            time.sleep(0.3)

            cdp.js(OPEN)
            time.sleep(0.3)
            a = cdp.js(PROBE)
            print("—— 弹出 ——")
            c("右键 .opt 弹出了菜单", a.get("menu") is True)
            c("菜单里有：复制名 / 复制值 / 恢复默认 / 完整说明",
              len(a.get("items") or []) == 4, f"items={a.get('items')}")

            key = a.get("firstKey") or ""
            cdp.js(COPYKEY)
            time.sleep(0.3)
            b = cdp.js("(() => ({copied: window.__copied, menu: !!document.querySelector('.ctx-menu')}))()")
            print("\n—— 复制选项名 ——")
            c("复制的内容就是这一行的 key", b.get("copied") == key,
              f"copied={b.get('copied')!r} 期望={key!r}")
            c("点完菜单自己关掉", b.get("menu") is False)

            cdp.js(OPEN)
            time.sleep(0.3)
            cdp.js(ESC)
            time.sleep(0.2)
            d = cdp.js("(() => !!document.querySelector('.ctx-menu'))()")
            print("\n—— Esc ——")
            c("Esc 能关掉菜单", d is False)

            cdp.js(OPEN)
            time.sleep(0.3)
            cdp.js(RESET)
            time.sleep(0.5)
            e = cdp.js("(() => ({menu: !!document.querySelector('.ctx-menu'),"
                       " checked: (document.querySelector('.opt input[data-role=check]')||{}).checked}))()")
            print("\n—— 恢复默认 ——")
            c("恢复默认后勾选框真的被取消了", e.get("checked") is False,
              f"checked={e.get('checked')}")

            cdp.js(OPEN)
            time.sleep(0.3)
            cdp.js("(() => { const it = Array.from(document.querySelectorAll('.ctx-item'))"
                   "   .find(b => b.dataset.act === 'info'); if (it) it.click(); return true; })()")
            time.sleep(0.3)
            g = cdp.js("(() => window.__infoClicked)()")
            print("\n—— 完整说明 ——")
            c("完整说明走的是页面自己的 info 通道", g == 1, f"__infoClicked={g}")

            cdp.js(ELSEWHERE)
            time.sleep(0.2)
            f = cdp.js("(() => !!document.querySelector('.ctx-menu'))()")
            print("\n—— 非选项区域 ——")
            c("右键别处不弹我们的菜单（保留浏览器默认）", f is False)
            print()
            return c.done()
        finally:
            try:
                stop(browser)
            except Exception:
                pass
            if srv:
                srv.terminate()
                try:
                    srv.wait(timeout=10)
                except Exception:
                    srv.kill()
    sys.exit(main())


# ==========================================================================
# hotkeys（键盘快捷键层）
# ==========================================================================

def cmd_hotkeys():
    """键盘快捷键层的实机验证（R-28）：按了真的有反应吗？打字会被劫持吗？

    为什么要真机跑：快捷键层是纯 JS 的 document keydown 监听，HTML 里一个字都
    看不到；「? 在搜索框里必须还是打字」「没有映射的页面不拦浏览器默认」
    这类边界行为，静态检查一个都判不了。

    ⚠⚠ 检查会真的触发主操作按钮 —— 所以写配置的接口必须先换成桩
    （API.basicApply / API.keysSave 返回 ok=false 的 Promise）。
    本机有 mpv-lazy 时 basic 页 boot() 会自动把 target 填上，
    不打桩的话一次 Ctrl+S 就真写了一份 mpv.conf。这是实机检查自己的坑，
    与 status 检查 stub API.status 是同一个手法。

    判六件事：
      1. ? 开帮助面板、Esc 关（index）
      2. 面板只列本页真实生效的条目（index 2 条 / 注入选项行后的 advanced 6 条）
         —— 帮助面板不许吹不存在的能力
      3. Ctrl+S 触发主操作且拦截浏览器默认（basic）
      4. 没有映射的页面（index）Ctrl+S 不拦浏览器默认
      5. 焦点在搜索框里时 ? 不劫持，但 Ctrl+S 照常保存（keys）
      6. 选项行 ↓/↑ 移动焦点、Enter 展开该行说明（advanced，注入合成行测委托）

    用法（会自己起一个临时后端，端口自动挑）：
        python tools/verify.py hotkeys
    """
    import json
    import socket
    import subprocess
    import sys
    import time
    import urllib.request
    from pathlib import Path

    ROOT = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "tools"))

    from uidriver import Checker, connect, launch, stop, wait_page   # noqa: PLC0415

    c = Checker()

    # window 层的气泡监听在 document 的监听之后跑，读到的 defaultPrevented
    # 就是快捷键层处理完之后的最终值 —— 这是「拦没拦浏览器默认」的判据
    WATCH = ("(() => { window.__hkPrev = null;"
             " window.addEventListener('keydown', e => { window.__hkPrev = e.defaultPrevented; });"
             " return true; })()")
    QMARK = ("(() => { document.dispatchEvent(new KeyboardEvent('keydown',"
             " {key:'?', bubbles:true, cancelable:true})); return true; })()")
    ESC = ("(() => { document.dispatchEvent(new KeyboardEvent('keydown',"
           " {key:'Escape', bubbles:true, cancelable:true})); return true; })()")
    CTRL_S = ("(() => { document.dispatchEvent(new KeyboardEvent('keydown',"
              " {key:'s', ctrlKey:true, bubbles:true, cancelable:true})); return true; })()")
    PROBE_HELP = """
    (() => {
      const p = document.querySelector('.hotkey-help');
      return {
        open: !!p,
        rows: p ? p.querySelectorAll('.hk-row').length : 0,
        title: p && p.querySelector('.hk-title') ? p.querySelector('.hk-title').textContent : ''
      };
    })()
    """
    SPY_BTN = ("(sel => { const b = document.querySelector(sel); if (!b) return false;"
               " window.__prim = 0;"
               " b.addEventListener('click', () => { window.__prim++; }); return true; })({sel})")
    STUB_WRITES = ("(() => { API.basicApply = () => Promise.resolve({ok:false, detail:'stub'});"
                   " API.keysSave = () => Promise.resolve({ok:false, detail:'stub'});"
                   " return true; })()")
    # 注入两行合成的 .opt（同 ctxmenu 的判据：测的是 api.js 里的委托逻辑，
    # 不依赖页面真数据）。第二行 info 按钮挂计数器。
    SEED_ROWS = (
        "(function(){"
        " document.getElementById('panes').innerHTML ="
        "  '<div class=\"opt on\" data-key=\"--test-a\"><div class=\"opt-head\">'"
        "  + '<input type=\"checkbox\" data-role=\"check\" checked>'"
        "  + '<label data-role=\"label\">测试 A</label>'"
        "  + '<div class=\"right\"><button class=\"icon-btn\" data-role=\"info\">i</button></div></div></div>'"
        "  + '<div class=\"opt\" data-key=\"--test-b\"><div class=\"opt-head\">'"
        "  + '<input type=\"checkbox\" data-role=\"check\">'"
        "  + '<label data-role=\"label\">测试 B</label>'"
        "  + '<div class=\"right\"><button class=\"icon-btn\" data-role=\"info\">i</button></div></div></div>';"
        " window.__infoA = 0;"
        " document.querySelectorAll('.opt')[0].querySelector('[data-role=info]')"
        "   .addEventListener('click', function(){ window.__infoA++; });"
        " return true; })()"
    )
    FOCUS_ROW = ("(i => { const b = document.querySelectorAll('.opt input[data-role=check]')[i];"
                 " if (!b) return false; b.focus(); return true; })({i})")
    ARROW = ("(k => { document.activeElement.dispatchEvent(new KeyboardEvent('keydown',"
             " {key:k, bubbles:true, cancelable:true}));"
             " return document.activeElement.closest('.opt')"
             "   ? document.activeElement.closest('.opt').dataset.key : ''; })({k})")
    ENTER = ("(() => { document.activeElement.dispatchEvent(new KeyboardEvent('keydown',"
             " {key:'Enter', bubbles:true, cancelable:true})); return true; })()")

    def free_port():
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        p = s.getsockname()[1]
        s.close()
        return p

    def start_server(port):
        proc = subprocess.Popen(
            [sys.executable, "-X", "utf8", str(ROOT / "webui" / "server.py"),
             "--port", str(port), "--no-window"],
            cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=1) as f:
                    json.load(f)
                return proc
            except Exception:
                if proc.poll() is not None:
                    sys.exit("后端启动失败（进程已退出）")
                time.sleep(0.4)
        proc.kill()
        sys.exit("后端 30 秒内没起来")

    def main():
        port, cdp_port = free_port(), free_port()
        srv = browser = None
        try:
            return _run(port, cdp_port)
        except BaseException:
            # CI 上 subprocess 的 stdout 是块缓冲——崩在这里时上面的进度全靠
            # 退出时 flush；但 traceback 只进 stderr，包装器旧版看不到。
            # 现在：栈直接打到 stdout + 无缓冲运行，双保险。
            import traceback
            traceback.print_exc()
            sys.stdout.flush()
            print("❌ motion 子进程异常退出（栈见上）")
            return 1

    def _run(port, cdp_port):
        srv = browser = None
        try:
            srv = start_server(port)
            print(f"后端已起：http://127.0.0.1:{port}\n")
            browser = launch(cdp_port)
            cdp = connect(cdp_port)
            base = f"http://127.0.0.1:{port}/"

            # ---- index：面板开关 / 无映射页不拦 / 状态栏入口 ----
            wait_page(cdp, base + "index.html", wait_s=2.5)
            cdp.js(WATCH)
            time.sleep(0.8)
            a = cdp.js(PROBE_HELP)
            print("—— 帮助面板（index） ——")
            c("初始状态没有面板", a.get("open") is False)
            cdp.js(QMARK)
            time.sleep(0.3)
            a = cdp.js(PROBE_HELP)
            c("按 ? 弹出了帮助面板", a.get("open") is True, f"probe={a}")
            c("index 没有主操作与选项行，面板只列 2 条", a.get("rows") == 2,
              f"rows={a.get('rows')}")
            cdp.js(ESC)
            time.sleep(0.3)
            c("Esc 关掉了面板", cdp.js(PROBE_HELP).get("open") is False)

            cdp.js(CTRL_S)
            time.sleep(0.3)
            print("\n—— Ctrl+S（无映射页） ——")
            c("index 没有映射，Ctrl+S 不拦浏览器默认",
              cdp.js("(() => window.__hkPrev)()") is False,
              f"defaultPrevented={cdp.js('(() => window.__hkPrev)()')}")

            cdp.js("(() => { const k = document.querySelector('.sb-keys');"
                   " if (!k) return false; k.click(); return true; })()")
            time.sleep(0.3)
            print("\n—— 状态栏入口 ——")
            c("状态栏的「? 快捷键」按钮能开面板", cdp.js(PROBE_HELP).get("open") is True)
            cdp.js(ESC)

            # ---- basic：Ctrl+S 触发主操作（写接口已打桩） ----
            wait_page(cdp, base + "basic.html", wait_s=2.5)
            cdp.js(WATCH)
            cdp.js(STUB_WRITES)
            has = cdp.js(SPY_BTN.replace("{sel}", "'#applyBtn'"))
            time.sleep(0.8)
            print("\n—— Ctrl+S（basic） ——")
            c("basic 的主操作按钮存在", has is True)
            cdp.js(CTRL_S)
            time.sleep(0.4)
            prim = cdp.js("(() => window.__prim)()")
            c("Ctrl+S 触发了「生成配置」按钮", prim == 1, f"__prim={prim}")
            c("浏览器默认保存行为被拦下",
              cdp.js("(() => window.__hkPrev)()") is True)
            cdp.js(QMARK)
            time.sleep(0.3)
            b = cdp.js(PROBE_HELP)
            c("basic 的面板列出主操作（3 条）", b.get("rows") == 3, f"rows={b.get('rows')}")

            # ---- keys：打字优先 ----
            wait_page(cdp, base + "keys.html", wait_s=2.5)
            cdp.js(WATCH)
            cdp.js(STUB_WRITES)
            has = cdp.js(SPY_BTN.replace("{sel}", "'#saveBtn'"))
            time.sleep(0.8)
            print("\n—— 搜索框里打字（keys） ——")
            c("keys 的保存按钮存在", has is True)
            inq = ("(() => { const q = document.querySelector('#q'); if (!q) return false;"
                   " q.focus(); q.dispatchEvent(new KeyboardEvent('keydown',"
                   " {key:'?', bubbles:true, cancelable:true})); return true; })()")
            c("搜索框存在", cdp.js(inq) is True)
            time.sleep(0.3)
            c("搜索框里按 ? 还是打字（面板没被劫持弹出）",
              cdp.js(PROBE_HELP).get("open") is False)
            ins = ("(() => { const q = document.querySelector('#q'); q.focus();"
                   " q.dispatchEvent(new KeyboardEvent('keydown',"
                   " {key:'s', ctrlKey:true, bubbles:true, cancelable:true})); return true; })()")
            cdp.js(ins)
            time.sleep(0.4)
            prim = cdp.js("(() => window.__prim)()")
            print("\n—— 输入框里的 Ctrl+S（keys） ——")
            c("输入框里 Ctrl+S 照常触发保存", prim == 1, f"__prim={prim}")

            # ---- advanced：选项行导航（合成行测委托） ----
            wait_page(cdp, base + "advanced.html", wait_s=2.5)
            cdp.js(SEED_ROWS)
            time.sleep(0.3)
            cdp.js(FOCUS_ROW.replace("{i}", "0"))
            print("\n—— 选项行导航（advanced） ——")
            k1 = cdp.js(ARROW.replace("{k}", "'ArrowDown'"))
            c("↓ 把焦点移到第二行", k1 == "--test-b", f"焦点在 {k1!r}")
            k2 = cdp.js(ARROW.replace("{k}", "'ArrowUp'"))
            c("↑ 把焦点移回第一行", k2 == "--test-a", f"焦点在 {k2!r}")
            cdp.js(ENTER)
            time.sleep(0.3)
            info = cdp.js("(() => window.__infoA)()")
            c("Enter 展开的是当前行的完整说明", info == 1, f"__infoA={info}")
            cdp.js(QMARK)
            time.sleep(0.3)
            d = cdp.js(PROBE_HELP)
            c("有选项行 + 有主操作的页面列 6 条", d.get("rows") == 6,
              f"rows={d.get('rows')}")
            print()
            return c.done()
        finally:
            try:
                stop(browser)
            except Exception:
                pass
            if srv:
                srv.terminate()
                try:
                    srv.wait(timeout=10)
                except Exception:
                    srv.kill()
    sys.exit(main())


# ==========================================================================
# motion（界面动效）
# ==========================================================================

def cmd_motion():
    """界面动效的实机验证（R-27 执行轮）：动效在吗？reduced-motion 会归零吗？

    为什么要真机跑：动效全是 CSS（transition/animation），静态检查只能证明
    "样式表里有这几行"，证明不了「真的挂在对应的元素上」「展开收起真的平滑」
    「reduced-motion 用户拿到的是无动画版本」。后者用 CDP 的
    Emulation.setEmulatedMedia 模拟 prefers-reduced-motion 实测，不靠 grep。

    判七件事：
      1. body 有 page-in 入场动画（切模式页不再白屏硬切）
      2. 选项行展开走 grid-rows 过渡：点 label 高度 0→>0，再点回 0
      3. 侧栏切分区后内容区挂上 pane-in 淡入
      4. 保存回执：成功路径后按钮挂 ack-ok，✓ 覆盖层动画存在，620ms 后自清
         ——写接口先换成桩，与 hotkeys/status 检查同一手法（不真写 mpv.conf）
      5. applyTop 绑定回归：顶栏「生成配置」点击真的触发 applyConfig
         （2026-11-08 发现它从未绑定，此检查防它再死）
      6. 模拟 prefers-reduced-motion: reduce 后 body/page-in 归零、
         .expand 过渡归零——模拟撤除后恢复
      7. 注入合成行测的是 api.js/state.js 的委托逻辑，不依赖页面真数据（同 ctxmenu）

    用法（会自己起一个临时后端，端口自动挑）：
        python tools/verify.py motion
    """
    import json
    import socket
    import subprocess
    import sys
    import time
    import urllib.request
    from pathlib import Path

    ROOT = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "tools"))

    from uidriver import Checker, connect, launch, stop, wait_page   # noqa: PLC0415

    c = Checker()

    STUB_WRITES = ("(() => { API.basicApply = () =>"
                   " Promise.resolve({ok:true, detail:'stub'}); return true; })()")
    BODY_ANIM = "(() => getComputedStyle(document.body).animationName)()"
    REDUCE_ON = ("(() => { matchMedia('(prefers-reduced-motion: reduce)'); return true; })()")
    SEED_ROWS = (
        "(function(){"
        " document.getElementById('panes').innerHTML ="
        "  '<div class=\"opt\" data-key=\"--test-a\"><div class=\"opt-head\">'"
        "  + '<input type=\"checkbox\" data-role=\"check\">'"
        "  + '<label data-role=\"label\">测试 A</label></div>'"
        "  + '<div class=\"expand\" data-role=\"expand\"><div><div class=\"expand-body\">说明文本</div></div></div></div>';"
        " document.getElementById('panes').onclick = onOptEvent;"
        " return true; })()"
    )
    CLICK_LABEL = ("(() => { const l = document.querySelector('.opt [data-role=\"label\"]');"
                   " if (!l) return false; l.click(); return true; })()")
    EXPAND_PROBE = """
    (() => {
      const ex = document.querySelector('.opt .expand');
      if (!ex) return { none: true };
      const body = ex.querySelector('.expand-body');
      return {
        h: ex.offsetHeight,
        bh: body ? body.offsetHeight : -1,
        tp: getComputedStyle(ex).transitionProperty,
        td: getComputedStyle(ex).transitionDuration,
        open: ex.classList.contains('open')
      };
    })()
    """
    # ⚠ CI 机器没有 mpv 配置目录，target 输入框是空的——doApply 会在调
    # basicApply 之前早退（"请先填目标配置目录"），ack 永远不会挂上。
    # 所以点击前先填一个目标（basicApply 已换桩，不会真写）。
    ACK_TEST = ("(() => { const b = document.getElementById('applyBtn'); if (!b) return false;"
                " const t = document.getElementById('target');"
                " if (t && !t.value) t.value = 'C:/mpv-config-demo';"
                " b.click(); return true; })()")
    ACK_STATE = """
    (() => {
      const b = document.getElementById('applyBtn');
      return { cls: b.classList.contains('ack-ok'),
               anim: getComputedStyle(b, '::after').animationName };
    })()
    """
    TOP_SPY = ("(() => { const t = document.getElementById('applyTop'); if (!t) return -1;"
               " window.__top = 0; t.addEventListener('click', () => { window.__top++; });"
               " t.click(); return window.__top; })()")
    PANE_TEST = ("(() => { const items = document.querySelectorAll('.side-item');"
                 " if (items.length < 2) return false; items[1].click(); return true; })()")
    PANE_PROBE = ("(() => { const p = document.getElementById('panes');"
                  " return p ? p.classList.contains('pane-in') : false; })()")

    def free_port():
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        p = s.getsockname()[1]
        s.close()
        return p

    def start_server(port):
        proc = subprocess.Popen(
            [sys.executable, "-X", "utf8", str(ROOT / "webui" / "server.py"),
             "--port", str(port), "--no-window"],
            cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=1) as f:
                    json.load(f)
                return proc
            except Exception:
                if proc.poll() is not None:
                    sys.exit("后端启动失败（进程已退出）")
                time.sleep(0.4)
        proc.kill()
        sys.exit("后端 30 秒内没起来")

    def main():
        port, cdp_port = free_port(), free_port()
        srv = browser = None
        try:
            return _run(port, cdp_port)
        except BaseException:
            # CI 上 subprocess 的 stdout 是块缓冲——崩在这里时上面的进度全靠
            # 退出时 flush；但 traceback 只进 stderr，包装器旧版看不到。
            # 现在：栈直接打到 stdout + 无缓冲运行，双保险。
            import traceback
            traceback.print_exc()
            sys.stdout.flush()
            print("❌ motion 子进程异常退出（栈见上）")
            return 1

    def _run(port, cdp_port):
        srv = browser = None
        try:
            srv = start_server(port)
            print(f"后端已起：http://127.0.0.1:{port}\n")
            browser = launch(cdp_port)
            cdp = connect(cdp_port)
            base = f"http://127.0.0.1:{port}/"

            # ---- index：页面入场 + reduced-motion 模拟 ----
            wait_page(cdp, base + "index.html", wait_s=2.5)
            time.sleep(0.8)
            # ⚠ CI runner 的 Windows 系统级 prefers-reduced-motion 就是 reduce
            #（2026-11-08 实测：所有动画断言在"非模拟段"天然全灭，而 reduce
            # 段全过——环境本身就是 reduce）。所以非模拟断言前先把模拟态
            # **显式固定为 no-preference**，让它们跑在确定的环境里。
            cdp.call("Emulation.setEmulatedMedia",
                     features=[{"name": "prefers-reduced-motion", "value": "no-preference"}])
            time.sleep(0.3)
            print("—— 页面入场动画 ——")
            c("body 挂着 page-in 入场动画", cdp.js(BODY_ANIM) == "page-in",
              f"animationName={cdp.js(BODY_ANIM)!r}")

            cdp.call("Emulation.setEmulatedMedia",
                     features=[{"name": "prefers-reduced-motion", "value": "reduce"}])
            time.sleep(0.3)
            reduced = cdp.js("(() => matchMedia('(prefers-reduced-motion: reduce)').matches)()")
            anim = cdp.js(BODY_ANIM)
            print("\n—— prefers-reduced-motion: reduce（模拟） ——")
            c("模拟已生效", reduced is True)
            c("reduce 下 page-in 归零", anim == "none", f"animationName={anim!r}")
            cdp.call("Emulation.setEmulatedMedia",
                     features=[{"name": "prefers-reduced-motion", "value": "no-preference"}])
            time.sleep(0.3)
            c("撤除模拟后动画恢复", cdp.js(BODY_ANIM) == "page-in")

            # ---- basic：保存回执（写接口已换成桩，点击成功路径安全） ----
            wait_page(cdp, base + "basic.html", wait_s=2.5)
            cdp.js(STUB_WRITES)
            time.sleep(0.8)
            print("\n—— 保存回执（basic） ——")
            c("basic 主按钮存在", cdp.js(ACK_TEST) is True)
            time.sleep(0.25)
            a = cdp.js(ACK_STATE)
            c("成功路径后按钮挂上 ack-ok", a.get("cls") is True, f"state={a}")
            c("✓ 覆盖层走 ack-ok 动画", a.get("anim") == "ack-ok",
              f"::after animation={a.get('anim')!r}")
            time.sleep(0.75)
            c("620ms 后回执自清", cdp.js(ACK_STATE).get("cls") is False)

            # ---- advanced：展开过渡 / 侧栏淡入 / applyTop 绑定 / reduce 下的过渡 ----
            wait_page(cdp, base + "advanced.html", wait_s=2.5)
            time.sleep(1.2)
            cdp.js(SEED_ROWS)
            time.sleep(0.3)
            print("\n—— 选项行展开（grid-rows） ——")
            c("展开容器有 grid-rows 过渡",
              "grid-template-rows" in (cdp.js(EXPAND_PROBE).get("tp") or ""))
            cdp.js(CLICK_LABEL)
            time.sleep(0.25)
            e1 = cdp.js(EXPAND_PROBE)
            c("点 label 后展开（高度 > 0）", (e1.get("h") or 0) > 0 and e1.get("open") is True,
              f"h={e1.get('h')} open={e1.get('open')}")
            cdp.js(CLICK_LABEL)
            time.sleep(0.25)
            e2 = cdp.js(EXPAND_PROBE)
            c("再点后收起（高度归 0）", e2.get("h") == 0 and e2.get("open") is False,
              f"h={e2.get('h')} open={e2.get('open')}")

            print("\n—— 侧栏切分区淡入 ——")
            c("点了第二个分区", cdp.js(PANE_TEST) is True)
            time.sleep(0.2)
            c("内容区挂上 pane-in", cdp.js(PANE_PROBE) is True)

            print("\n—— applyTop 绑定回归 ——")
            c("顶栏「生成配置」点击触发了 applyConfig", cdp.js(TOP_SPY) == 1)

            cdp.call("Emulation.setEmulatedMedia",
                     features=[{"name": "prefers-reduced-motion", "value": "reduce"}])
            time.sleep(0.3)
            e3 = cdp.js(EXPAND_PROBE)
            print("\n—— reduce 下的展开过渡 ——")
            c("reduce 下 .expand 过渡归零", e3.get("td") in ("0s", "0s, 0s"),
              f"transitionDuration={e3.get('td')!r}")
            cdp.call("Emulation.setEmulatedMedia",
                     features=[{"name": "prefers-reduced-motion", "value": "no-preference"}])
            print()
            return c.done()
        finally:
            try:
                stop(browser)
            except Exception:
                pass
            if srv:
                srv.terminate()
                try:
                    srv.wait(timeout=10)
                except Exception:
                    srv.kill()
    sys.exit(main())


# ==========================================================================
# stdio（原 check_stdio_ui.py）
# ==========================================================================
def cmd_stdio():
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

    用法：py -3 tools/verify.py stdio
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
        而**这套头在真实外壳里根本不存在**（Tauri 那边的页面是资源协议 + 管道）。
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
    raise SystemExit(main())

# ==========================================================================
# presets（原 check_presets.py）
# ==========================================================================
def cmd_presets():
    r"""实机验证「我自己的预设」（advanced.html 的「快速预设」分区）。

    跑法（仓库根目录）：
        py -3 webui\server.py --port 8765 --no-window     # 另开一个窗口
        py -3 tools\verify.py presets

    为什么值得单独验：预设这套东西前后端各一半 —— 后端有 40 多项单元测试，
    但"点按钮到底有没有反应、存完列表刷不刷新、导出的文件能不能再导回来"
    只有真跑才知道。

    ⚠ 它会往**用户数据目录**写文件（W-2 之后是
    `%LOCALAPPDATA%\MPVConfigBuilder\presets`，**不是仓库根的 `presets/`**），
    所以脚本**先问运行中的服务**那个目录在哪、确认是空的才继续，跑完再清掉。
    """
    import json
    import shutil
    import sys
    import time
    import urllib.request
    from pathlib import Path

    ROOT = Path(__file__).resolve().parent.parent      # 仓库根（本文件在 tools/ 下）
    sys.path.insert(0, str(Path(__file__).resolve().parent))

    from uidriver import launch, connect, wait_page, stop, Checker   # noqa: E402

    SHOTS = ROOT / "_shots"
    PORT = 9225
    BASE = "http://127.0.0.1:8765"
    URL = BASE + "/advanced.html#preset"


    def preset_dir_from_server():
        """问运行中的服务：预设目录到底在哪。

        不自己拼路径 —— W-2 之后它是 `%LOCALAPPDATA%\\MPVConfigBuilder\\presets`，
        而这是**服务端**根据 `core.paths.user_data_dir()` 决定的（还受
        `DSH_MPV_DATA_DIR` 影响）。脚本再猜一遍迟早对不上。
        """
        try:
            with urllib.request.urlopen(f"{BASE}/api/userpresets", timeout=10) as r:
                d = json.loads(r.read().decode("utf-8"))
            p = d.get("dir")
            return Path(p) if p else None
        except Exception:
            return None


    def main():
        # ⚠ 预设目录在 W-2 之后是**用户数据目录**（`%LOCALAPPDATA%\MPVConfigBuilder\presets`），
        # **不是仓库根的 `presets/`** —— 那是重构前的旧位置。
        # 所以这里要问**运行中的服务**它到底用哪个目录，不能自己猜。
        reg = preset_dir_from_server()
        if reg is None:
            sys.exit("⚠ 读不到预设目录（服务没起来？先按文件头那两行起服务）")
        # ⚠ 空目录不算 —— 打开预设卡片本身就会建出 `presets/`（list_presets 会 mkdir），
        # 所以"目录存在"根本不代表"里面有你的预设"。只看有没有文件。
        if reg.exists() and any(reg.iterdir()):
            sys.exit(f"⚠ {reg} 里已经有东西了 —— 先挪开再跑，"
                     "免得把测试预设和你自己的混在一起")
        check = Checker()
        proc = launch(PORT)
        try:
            c = connect(PORT)
            wait_page(c, URL)

            def shot(name):
                c.shot(SHOTS / name)

            print("== 卡片渲染 ==")
            check("「我自己的预设」卡片在", c.js("!!document.getElementById('myPresetCard')"))
            check("按钮和文件框都在", c.js("""(() => ['myPresetName','myPresetSave',
                'myPresetExport','myPresetImport','myPresetFile','myPresetBtns']
                .every(i => !!document.getElementById(i)))()"""))
            check("接线成功（onclick / onchange 都挂上了）", c.js("""(() => {
                const b = document.getElementById('myPresetSave');
                const f = document.getElementById('myPresetFile');
                return typeof b.onclick === 'function' && typeof f.onchange === 'function';
            })()"""))
            empty_hint = c.js("document.getElementById('myPresetBtns').textContent") or ""
            check("空列表时给了说明（不是一片空白）", "还没有存过预设" in empty_hint,
                  empty_hint[:50])
            shot("40_我的预设_空.png")

            print("== 存一套 ==")
            c.js("""(() => {
              setOption('vo', 'gpu-next');
              setOption('scale', 'ewa_lanczossharp');
              APP.shaders = ['~~/shaders/Anime4K/Anime4K_Upscale_GAN_x2_M.glsl'];
              changed();
            })()""")
            time.sleep(0.4)
            check("当前状态里有 3 项要存",
                  c.js("countPresetItems(currentPresetState())") == 3)
            c.js("document.getElementById('myPresetName').value = '看番那套'")
            c.js("document.getElementById('myPresetSave').click()")
            time.sleep(1.2)
            lst = c.js("""(() => {
              const box = document.getElementById('myPresetBtns');
              return {text: box.textContent, n: box.querySelectorAll('button').length};
            })()""")
            check("列表里出现了新预设", lst["n"] == 1 and "看番那套" in lst["text"],
                  json.dumps(lst, ensure_ascii=False)[:100])
            check("名字框被清空", c.js("document.getElementById('myPresetName').value") == "")
            check("磁盘上真有这个文件", (reg / "看番那套.json").is_file())
            saved = json.loads((reg / "看番那套.json").read_text(encoding="utf-8"))
            check("文件内容对得上",
                  saved["state"]["values"].get("vo") == "gpu-next"
                  and len(saved["state"]["shaders"]) == 1,
                  json.dumps(saved["state"], ensure_ascii=False)[:110])
            shot("41_我的预设_存好了.png")

            print("== 同名再存要问一句 ==")
            c.js("window.confirm = () => true")
            c.js("setOption('vo', 'gpu')")
            time.sleep(0.3)
            c.js("document.getElementById('myPresetName').value = '看番那套'")
            c.js("document.getElementById('myPresetSave').click()")
            time.sleep(1.2)
            again = json.loads((reg / "看番那套.json").read_text(encoding="utf-8"))
            check("确认后覆盖成功", again["state"]["values"].get("vo") == "gpu",
                  str(again["state"]["values"].get("vo")))
            check("还是只有一个预设", c.js(
                "document.getElementById('myPresetBtns').querySelectorAll('button').length") == 1)

            c.js("window.confirm = () => false")
            c.js("document.getElementById('myPresetName').value = '看番那套'")
            c.js("document.getElementById('myPresetSave').click()")
            time.sleep(1.0)
            still = json.loads((reg / "看番那套.json").read_text(encoding="utf-8"))
            check("点取消就不覆盖", still["state"]["values"].get("vo") == "gpu")

            print("== 套用回当前状态 ==")
            c.js("window.confirm = () => true")
            c.js("clearAll()")
            time.sleep(0.6)
            before = c.js("""(() => ({vo: APP.values['vo'] || null,
                n: Object.keys(APP.values).length}))()""")
            # ⚠ 预设卡片在页面靠下，按钮可能落在视口外 —— 不滚过去的话
            # CDP 派发的真实鼠标事件打在视口外，等于没点（踩过：y=1182 > 900 视口）。
            c.js("document.getElementById('myPresetBtns').scrollIntoView({block:'center'})")
            time.sleep(0.5)
            box = c.js("""(() => { const b = document.querySelector('#myPresetBtns button');
                if (!b) return null; const r = b.getBoundingClientRect();
                return {x: Math.round(r.left + r.width/2),
                        y: Math.round(r.top + r.height/2),
                        w: Math.round(r.width), h: Math.round(r.height)}; })()""")
            check("预设按钮在视口内（真实鼠标点得到）",
                  bool(box) and 0 < box["y"] < 900 and box["w"] > 0,
                  json.dumps(box, ensure_ascii=False))
            if box and box["w"] > 0:
                c.click(box["x"], box["y"])
            time.sleep(1.2)
            after = c.js("""(() => ({vo: APP.values['vo'] || null,
                shaders: APP.shaders.length}))()""")
            check("真实鼠标点一下就套上了", after["vo"] == "gpu" and after["shaders"] == 1,
                  f"之前 {json.dumps(before, ensure_ascii=False)}"
                  f" 之后 {json.dumps(after, ensure_ascii=False)}")

            # 事件路径之外，再直接验一次"套用"本身 —— 上面那条万一被重渲染的
            # 时序影响（卡片是异步渲染出来的），这条能明确区分"功能坏了"还是"点空了"
            c.js("clearAll()")
            time.sleep(0.5)
            direct = c.js("""(() => {
              const r = {ok: true};
              try { applyMyPreset({id: '看番那套', name: '看番那套',
                state: {values: {vo: 'gpu-next', scale: 'ewa'}, shaders: [], memc: '', disable: []}}); }
              catch (e) { r.ok = false; r.err = String(e); }
              return {ok: r.ok, err: r.err || '', vo: APP.values['vo'] || null};
            })()""")
            check("applyMyPreset 本身工作正常", direct["ok"] and direct["vo"] == "gpu-next",
                  json.dumps(direct, ensure_ascii=False))

            print("== 导出 ==")
            c.js("""(() => {
              window._dl = null;
              const orig = HTMLAnchorElement.prototype.click;
              HTMLAnchorElement.prototype.click = function () {
                if (this.download) { window._dl = this.download; return; }
                return orig.apply(this, arguments);
              };
            })()""")
            # ⚠ 导出的入口在**列表项**上（每个预设各有一个 ⬇️），不是卡片底下那个按钮 ——
            # 底下那个导的是"当前状态"。同样要先滚进视口再点。
            c.js("""(() => { const b = document.querySelector('#myPresetBtns [data-op="export"]');
                if (b) b.scrollIntoView({block: 'center'}); })()""")
            time.sleep(0.5)
            eb = c.js("""(() => { const b = document.querySelector('#myPresetBtns [data-op="export"]');
                if (!b) return null; const r = b.getBoundingClientRect();
                return {x: Math.round(r.left + r.width/2),
                        y: Math.round(r.top + r.height/2),
                        w: Math.round(r.width), h: Math.round(r.height)}; })()""")
            check("导出按钮在视口内", bool(eb) and 0 < eb["y"] < 900 and eb["w"] > 0,
                  json.dumps(eb, ensure_ascii=False))
            if eb and eb["w"] > 0:
                c.click(eb["x"], eb["y"])
            time.sleep(1.2)
            check("触发下载且文件名跟预设名一致", c.js("window._dl") == "看番那套.json",
                  str(c.js("window._dl")))

            print("== 导出当前状态（卡片底下的按钮）==")
            # ⚠ 这一条必须在**状态非空**时跑：clearAll() 之后就"没东西可导"，
            # 后端会正当地拒绝（"一个选项都没勾"），那是设计不是 bug。
            # 顺序写反过一次，白排查了一轮。
            c.js("""(() => { setOption('vo', 'gpu-next');
                setOption('scale', 'ewa_lanczossharp'); changed(); })()""")
            time.sleep(0.5)
            c.js("window._dl = null")
            c.js("document.getElementById('myPresetExport').click()")
            time.sleep(1.2)
            dl2 = c.js("window._dl")
            check("卡片底下的按钮导的是当前状态",
                  isinstance(dl2, str) and dl2.endswith(".json"), str(dl2))

            c.js("clearAll()")
            time.sleep(0.4)
            c.js("window._dl = null")
            c.js("document.getElementById('myPresetExport').click()")
            time.sleep(1.0)
            check("清空后导出被正当拒绝（不是导出个空文件）",
                  c.js("window._dl") is None, str(c.js("window._dl")))

            print("== 导入（走 /api/presets/load 的 text 分支）==")
            good = {"kind": "mpv-config-builder-preset", "version": 1, "name": "别人给的",
                    "state": {"values": {"vo": "gpu-next", "hwdec": "nvdec"},
                              "shaders": [], "memc": "", "disable": []}}
            r = c.js("(async () => await API.userPresetLoad({text: %s}))()"
                     % json.dumps(json.dumps(good, ensure_ascii=False)))
            check("合法内容能导入", r and r.get("ok"),
                  json.dumps(r, ensure_ascii=False)[:120])
            bad = {"name": "别人的配置", "vo": "gpu"}
            r2 = c.js("(async () => await API.userPresetLoad({text: %s}))()"
                      % json.dumps(json.dumps(bad, ensure_ascii=False)))
            check("别的 json 被明确拒绝", r2 and not r2.get("ok"))
            check("拒绝理由说得清",
                  "不是 MPV Config Builder" in ((r2 or {}).get("detail") or ""),
                  ((r2 or {}).get("detail") or "")[:70])
            r3 = c.js("(async () => await API.userPresetLoad({text: '{ not json'}))()")
            check("坏 JSON 也被拦住而不是崩掉", r3 and not r3.get("ok"))

            print("== 删除 ==")
            c.js("""(() => { const b = document.querySelector(
                '#myPresetBtns [data-op="del"]'); if (b) b.click(); })()""")
            time.sleep(1.2)
            check("删完列表空了", c.js(
                "document.getElementById('myPresetBtns').querySelectorAll('button').length") == 0)
            check("磁盘上的文件也没了", not (reg / "看番那套.json").exists())

            return check.done()
        finally:
            stop(proc)
            if reg.exists():
                shutil.rmtree(reg, ignore_errors=True)
                print(f"（已清理测试用的 {reg}）")
    sys.exit(main())

# ==========================================================================
# ui（原 check_ui.py）
# ==========================================================================
def cmd_ui():
    """自绘候选下拉的实机验证（CDP，零依赖）。

    跑法（仓库根目录）：
        py -3 webui\\server.py --port 8765 --no-window     # 另开一个窗口
        py -3 tools\\check_ui.py

    为什么非要真机跑一遍：
      · 白底大气泡之所以改不动，正因为它不在 DOM 里、截图工具也抓不到。
        换成自绘之后它就进了 DOM —— **"能截到"本身就是"已经脱离浏览器 UI 层"的证据**。
      · 光靠读代码会漏掉布局与事件顺序的问题。开发时漏过两次：
          ① 未勾选的行把 input 单独藏了、外壳还在，`getBoundingClientRect()` 全是 0，
             面板按 (0,0) 定位飘到页面左上角；
          ② 面板项的点击走冒泡、document 的委托走捕获，捕获先把面板关掉，
             项自己的 handler 拿不到 input，于是"点候选完全没反应"。
        两个都只有真跑才看得见（第一个还能靠截图，第二个连报错都没有）。

    **第 14 项 ①（地狱模式参数补全）**同理：面板位置靠 canvas 量前缀宽度推算、
    接受动作靠 `setRangeText` 只换 token —— 读代码都"看起来对"，
    只有真按一次 Tab 才知道文本到底有没有被替换、面板会不会先被 blur 关掉。

    ⚠ 需要本机有 Edge 或 Chrome。
    截图落在仓库根的 `_shots/`。
    """
    import base64
    import json
    import os
    import subprocess
    import sys
    import tempfile
    import time
    import urllib.request
    from pathlib import Path
    from urllib.parse import urlparse

    ROOT = Path(__file__).resolve().parent.parent      # 仓库根（本文件在 tools/ 下）
    SHOTS = ROOT / "_shots"

    def free_port():
        """挑一个空着的本机端口给 CDP。

        为什么不能写死 9222（实测 2026-11-16）：本机 Edge 的后台进程会占着它，
        `/json/list` 回 **404** —— 新起的无头浏览器绑不上端口，检查直接报
        "浏览器没起来"，而浏览器其实好好的。端口是环境资源，不该由脚本假定。
        """
        import socket
        s = socket.socket()
        try:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]
        finally:
            s.close()

    PORT = free_port()
    URL = "http://127.0.0.1:8765/advanced.html#g:字幕样式"


    def find_browser():
        for c in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                  r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                  r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                  r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"):
            if os.path.exists(c):
                return c
        sys.exit("没找到 Edge / Chrome")


    class CDP:
        """极简 WebSocket 客户端（只够用 CDP：文本帧、无分片、服务端帧不掩码）。"""

        def __init__(self, ws_url):
            import socket
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


    def center(c, sel, idx=None):
        expr = (f"(() => {{ const els = document.querySelectorAll({sel!r});"
                f" const el = els[{idx if idx is not None else 0}];"
                " if (!el) return null; const r = el.getBoundingClientRect();"
                " return {x: Math.round(r.left + r.width/2),"
                "         y: Math.round(r.top + r.height/2),"
                "         w: Math.round(r.width), h: Math.round(r.height)}; })()")
        return c.js(expr)


    def panel(c):
        return c.js("""(() => {
          const p = document.querySelector('.combo-pop');
          if (!p) return {open:false};
          const cs = getComputedStyle(p), r = p.getBoundingClientRect();
          return {open:true, items: p.querySelectorAll('.combo-item').length,
                  text: [...p.querySelectorAll('.combo-item')].map(x=>x.textContent),
                  bg: cs.backgroundColor, color: cs.color, z: cs.zIndex,
                  rect: [Math.round(r.left), Math.round(r.top),
                         Math.round(r.width), Math.round(r.height)]};
        })()""")


    def main():
        SHOTS.mkdir(exist_ok=True)
        profile = tempfile.mkdtemp(prefix="dsh-cdp-")
        proc = subprocess.Popen([
            find_browser(), "--headless=new", f"--remote-debugging-port={PORT}",
            f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check",
            "--window-size=1440,900", "--hide-scrollbars",
            "--force-device-scale-factor=1", "about:blank",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        fails = []

        def check(label, cond, detail=""):
            print(("  ✅ " if cond else "  ❌ ") + label + (f"  {detail}" if detail else ""))
            if not cond:
                fails.append(label)

        try:
            ws = None
            for _ in range(60):
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list", timeout=1) as f:
                        tabs = json.load(f)
                    page = next((t for t in tabs if t["type"] == "page"), None)
                    if page:
                        ws = page["webSocketDebuggerUrl"]
                        break
                except Exception:
                    pass
                time.sleep(0.5)
            if not ws:
                sys.exit("浏览器没起来")

            c = CDP(ws)
            c.call("Page.enable")
            c.call("Runtime.enable")
            c.call("Page.navigate", url=URL)
            time.sleep(4.0)

            def shot(name):
                r = c.call("Page.captureScreenshot", format="png")
                (SHOTS / name).write_bytes(base64.b64decode(r["data"]))

            print("== 结构 ==")
            check("选项区渲染出来了", c.js("!!document.querySelector('.opt')"))
            check("监听已绑定（document._comboWired）", c.js("!!document._comboWired"))
            check("主题是深色", c.js("getComputedStyle(document.documentElement).colorScheme") == "dark")
            info = c.js("""(() => {
              const row = [...document.querySelectorAll('.opt')].find(r => r.dataset.key === 'sub-font');
              const input = row.querySelector('[data-role="value"]');
              return {tag: input.tagName, hasList: input.hasAttribute('list'),
                      opts: (input._options || []).length,
                      arrow: !!row.querySelector('[data-role="combo-toggle"]'),
                      noDatalist: !document.querySelector('datalist')};
            })()""")
            check("sub-font 用 input 而不是 select", info["tag"] == "INPUT")
            check("没有 list= 属性（白气泡的来源）", not info["hasList"])
            check("页面里没有 <datalist> 元素", info["noDatalist"])
            check("候选值已经进了 JS 属性", info["opts"] == 3, f"opts={info['opts']}")
            check("有下拉箭头按钮", info["arrow"])

            print("== 未勾选的行：控件理应整体隐藏（外壳不能留） ==")
            hid = c.js("""(() => {
              const row = document.querySelector('.opt[data-key="sub-font"]');
              const combo = row.querySelector('.combo');
              const arrow = row.querySelector('[data-role="combo-toggle"]');
              const ar = arrow ? arrow.getBoundingClientRect() : null;
              return {on: row.classList.contains('on'),
                      comboHidden: getComputedStyle(combo).display === 'none',
                      arrowW: ar ? Math.round(ar.width) : null};
            })()""")
            check("未勾选时整行没有值控件", (not hid["on"]) and hid["comboHidden"],
                  json.dumps(hid, ensure_ascii=False))
            check("外壳一起隐藏，箭头也没有几何（否则面板会飘到 0,0）",
                  hid["arrowW"] == 0, f"arrowW={hid['arrowW']}")

            print("== 【未勾选】直接点候选：应当自动勾选并写进配置 ==")
            # 控件是隐藏的，用程序勾选是不行的 —— 要模拟"用户展开后点了一项"。
            # 这条正是最初那个死胡同：选了却没生效，用户完全不知道为什么。
            c.js("""(() => { const row = document.querySelector('.opt[data-key="sub-font"]');
              openCombo(row.querySelector('[data-role="value"]')); })()""")
            time.sleep(0.4)
            dbg = c.js("""(() => {
              const p = document.querySelector('.combo-pop');
              if (!p) return {open:false};
              const els = [...p.querySelectorAll('.combo-item')];
              const r = p.getBoundingClientRect();
              const hit = els.map(e => { const q = e.getBoundingClientRect();
                return {t:e.textContent, box:[Math.round(q.left),Math.round(q.top),
                  Math.round(q.width),Math.round(q.height)],
                  pe: getComputedStyle(e).pointerEvents, vis: getComputedStyle(e).visibility}; });
              const el = document.elementFromPoint(Math.round(r.left+20), Math.round(r.top+30));
              return {open:true, popRect:[Math.round(r.left),Math.round(r.top),
                        Math.round(r.width),Math.round(r.height)],
                      items:hit, topMost: el ? (el.className || el.tagName) : null};
            })()""")
            print("     诊断:", json.dumps(dbg, ensure_ascii=False))
            shot("26_未勾选_下拉.png")
            # 把事件顺序记下来：到底是没触发 click，还是触发了但 comboPick 没跑
            c.js("""(() => {
              window._evlog = [];
              const it = document.querySelectorAll('.combo-item')[1];
              ['mousedown','mouseup','click','pointerdown','pointerup'].forEach(t =>
                it.addEventListener(t, e => window._evlog.push(t + '@' + e.target.textContent), true));
              const oc = window.comboPick;
              window.comboPick = function (v) { window._evlog.push('comboPick(' + v + ')'); return oc.apply(this, arguments); };
              return true;
            })()""")
            it0 = center(c, '.combo-item', 1)
            want0 = c.js("document.querySelectorAll('.combo-item')[1].textContent")
            c.click(it0["x"], it0["y"])
            time.sleep(0.6)
            print("     事件顺序:", c.js("JSON.stringify(window._evlog)"))
            auto = c.js("""(() => { const row = document.querySelector('.opt[data-key="sub-font"]');
              return {value: row.querySelector('[data-role="value"]').value,
                      checked: row.querySelector('[data-role="check"]').checked,
                      rowOn: row.classList.contains('on'),
                      inValues: APP.values['sub-font'] === undefined ? null : APP.values['sub-font']}; })()""")
            check("点候选项会自动勾选（不是死胡同）", auto["checked"], json.dumps(auto, ensure_ascii=False))
            check("值进了输入框", auto["value"] == want0, f"{auto['value']} vs {want0}")
            check("值进了 APP.values（会写进配置）", auto["inValues"] == want0, str(auto["inValues"]))
            shot("22_组合框_选中.png")

            # 复位成未勾选，继续测"已勾选"那条路（下拉默认是藏着的）
            c.js("""(() => { const row = document.querySelector('.opt[data-key="sub-font"]');
              const b = row.querySelector('[data-role="check"]');
              b.checked = false; b.dispatchEvent(new Event('change', {bubbles:true}));
              closeCombo(); })()""")
            time.sleep(0.4)

            print("== 勾选后才显示控件（一屏多看一倍选项的设计） ==")
            c.js("""(() => { const row = document.querySelector('.opt[data-key="sub-font"]');
              const b = row.querySelector('[data-role="check"]');
              b.checked = true; b.dispatchEvent(new Event('change', {bubbles:true})); })()""")
            time.sleep(0.5)
            shown = c.js("""(() => {
              const row = document.querySelector('.opt[data-key="sub-font"]');
              const combo = row.querySelector('.combo');
              const input = row.querySelector('[data-role="value"]');
              const r = input.getBoundingClientRect();
              return {on: row.classList.contains('on'),
                      comboShown: getComputedStyle(combo).display !== 'none',
                      rect: [Math.round(r.left), Math.round(r.top),
                             Math.round(r.width), Math.round(r.height)]};
            })()""")
            check("勾选后控件出现", shown["on"] and shown["comboShown"],
                  json.dumps(shown, ensure_ascii=False))
            check("输入框有真实几何（不是 0×0）",
                  shown["rect"][2] > 0 and shown["rect"][3] > 0, str(shown["rect"]))

            print("== 打开下拉：点箭头 ==")
            ab = center(c, '.opt[data-key="sub-font"] [data-role="combo-toggle"]')
            check("箭头按钮有几何尺寸", ab and ab["w"] > 0 and ab["h"] > 0, str(ab))
            c.click(ab["x"], ab["y"])
            time.sleep(0.5)
            p = panel(c)
            check("面板打开了", p.get("open"), json.dumps(p, ensure_ascii=False))
            if p.get("open"):
                check("候选值都在", p["items"] == 3, str(p.get("text")))
                check("面板是深色（不是白气泡）", p["bg"] == "rgb(23, 28, 38)", p["bg"])
                check("文字是浅色", p["color"] == "rgb(232, 235, 242)", p["color"])
                # 关键：面板要贴在这个输入框旁边，不能飘到 (0,0)
                inp = shown["rect"]
                near = abs(p["rect"][0] - inp[0]) <= 12 and abs(p["rect"][1] - (inp[1] + inp[3])) <= 12
                check("面板贴在输入框下方（没飘到左上角）", near,
                      f"面板{p['rect']} vs 输入框{inp}")
                check("面板宽度不小于输入框", p["rect"][2] >= inp[2],
                      f"{p['rect'][2]} vs {inp[2]}")

            print("== 过滤 ==")
            c.js("""(() => { const i = document.querySelector('.opt[data-key="sub-font"] [data-role="value"]');
                      i.value='Micro'; i.dispatchEvent(new Event('input', {bubbles:true})); })()""")
            time.sleep(0.4)
            fl = c.js("""(() => { const p = document.querySelector('.combo-pop');
              return {n: p.querySelectorAll('.combo-item').length,
                      empty: !!p.querySelector('.combo-empty'),
                      emptyText: (p.querySelector('.combo-empty')||{}).textContent || ''}; })()""")
            check("过滤没结果时给提示而不是空白", fl["n"] == 0 and fl["empty"], str(fl))
            shot("20_组合框_过滤无结果.png")

            c.js("""(() => { const i = document.querySelector('.opt[data-key="sub-font"] [data-role="value"]');
                      i.value='Wen'; i.dispatchEvent(new Event('input', {bubbles:true})); })()""")
            time.sleep(0.4)
            fl2 = c.js("""[...document.querySelectorAll('.combo-item')].map(x=>x.textContent)""")
            check("过滤 'Wen' 命中 LXGW", fl2 == ["LXGW WenKai Lite"], str(fl2))

            c.js("""(() => { const i = document.querySelector('.opt[data-key="sub-font"] [data-role="value"]');
                      i.value=''; i.dispatchEvent(new Event('input', {bubbles:true})); })()""")
            time.sleep(0.4)
            shot("21_组合框_展开.png")

            print("== 点击选择（已勾选的行） ==")
            it = center(c, '.combo-item', 2)
            picked_text = c.js("document.querySelectorAll('.combo-item')[2].textContent")
            c.click(it["x"], it["y"])
            time.sleep(0.6)
            res = c.js("""(() => ({
              value: document.querySelector('.opt[data-key="sub-font"] [data-role="value"]').value,
              popOpen: !!document.querySelector('.combo-pop'),
              checked: document.querySelector('.opt[data-key="sub-font"] [data-role="check"]').checked,
              rowOn: document.querySelector('.opt[data-key="sub-font"]').classList.contains('on'),
              inValues: APP.values['sub-font'] === undefined ? null : APP.values['sub-font']
            }))()""")
            check("值填进了输入框", res["value"] == picked_text, f"{res['value']} vs {picked_text}")
            check("选完就收起面板", not res["popOpen"])
            check("复选框保持勾选", res["checked"])
            check("rows 标记为已选", res["rowOn"])
            check("值真的进了 APP.values（会写进配置）",
                  res["inValues"] == picked_text, str(res["inValues"]))
            shot("22b_组合框_点击选中.png")

            print("== 键盘 ==")
            c.js("document.querySelector('.opt[data-key=\"sub-font\"] [data-role=\"value\"]').click()")
            time.sleep(0.3)
            if not c.js("!!document.querySelector('.combo-pop')"):
                c.js("openCombo(document.querySelector('.opt[data-key=\"sub-font\"] [data-role=\"value\"]'))")
            time.sleep(0.3)
            check("面板已开（键盘测试前置）", c.js("!!document.querySelector('.combo-pop')"))
            if c.js("!!document.querySelector('.combo-pop')"):
                c.key("ArrowDown", 40)
                k1 = c.js("(() => { const a=document.querySelector('.combo-item.active');"
                          " return a ? a.textContent : null; })()")
                c.key("ArrowDown", 40)
                k2 = c.js("(() => { const a=document.querySelector('.combo-item.active');"
                          " return a ? a.textContent : null; })()")
                check("ArrowDown 能逐项往下走", k1 is not None and k2 is not None and k1 != k2,
                      f"{k1} → {k2}")
                c.key("ArrowUp", 38)
                k3 = c.js("(() => { const a=document.querySelector('.combo-item.active');"
                          " return a ? a.textContent : null; })()")
                check("ArrowUp 能往回走", k3 == k1, f"{k3} vs {k1}")
                shot("23_组合框_键盘高亮.png")

                print("== Esc：关下拉，但不能顺手也关抽屉 ==")
                c.js("openDrawer({key:'sub-font', label:'字幕字体', desc:'键盘测试'})")
                time.sleep(0.4)
                drawer_before = c.js("document.getElementById('drawer').classList.contains('open')")
                c.key("Escape", 27)
                time.sleep(0.4)
                check("Esc 关掉了下拉", not c.js("!!document.querySelector('.combo-pop')"))
                check("Esc 之后抽屉还开着（没被误关）",
                      c.js("document.getElementById('drawer').classList.contains('open')"),
                      f"之前={drawer_before}")
                c.js("closeDrawer()")

            print("== 点别处收起 ==")
            c.js("openCombo(document.querySelector('.opt[data-key=\"sub-font\"] [data-role=\"value\"]'))")
            time.sleep(0.3)
            was = c.js("!!document.querySelector('.combo-pop')")
            c.js("document.getElementById('secTitle').click()")
            time.sleep(0.3)
            check("点白处后面板收起",
                  was and not c.js("!!document.querySelector('.combo-pop')"))

            print("== 浅色主题 ==")
            c.js("document.documentElement.dataset.theme='light'")
            c.js("openCombo(document.querySelector('.opt[data-key=\"sub-font\"] [data-role=\"value\"]'))")
            time.sleep(0.5)
            lp = panel(c)
            check("浅色主题下面板跟着变浅", lp.get("open") and lp["bg"] == "rgb(255, 255, 255)",
                  str(lp.get("bg")))
            shot("24_组合框_浅色.png")
            c.js("document.documentElement.dataset.theme='dark'")
            c.js("closeCombo()")

            print("== 完全体页面（原生层）也要能用 ==")
            c.call("Page.navigate", url="http://127.0.0.1:8765/expert.html")
            time.sleep(4.0)
            # 完全体默认只渲染一个分组（每屏几十项），搜索框只挂在「全部选项」那一屏。
            c.js("""(() => {
              const chip = document.querySelector('[data-sec="dbsearch"], [data-id="dbsearch"]');
              if (chip) chip.click();
            })()""")
            time.sleep(1.0)
            found = c.js("""(() => {
              const inp = document.getElementById('q');
              if (!inp) return false;
              inp.value = 'dither';
              inp.dispatchEvent(new Event('input', {bubbles:true}));
              return true;
            })()""")
            if not found:
                c.js("""(async () => { DB.q = 'dither'; await loadDb(true); })()""")
            time.sleep(3.0)
            e1 = c.js("""(() => {
              const rows = [...document.querySelectorAll('.opt')];
              const withOpts = [...document.querySelectorAll('.opt input[data-options]')];
              const withSel = [...document.querySelectorAll('.opt select[data-role="value"]')];
              const nonEmpty = withOpts.filter(i => (i._options||[]).length);
              return {keys: rows.map(r => r.dataset.key),
                      opts: withOpts.length, sels: withSel.length,
                      nonEmpty: nonEmpty.length,
                      empty: withOpts.length - nonEmpty.length,
                      sample: nonEmpty.slice(0,3).map(i => ({k: i.closest('.opt').dataset.key,
                        n: (i._options||[]).length}))};
            })()""")
            check("完全体渲染出来了", len(e1["keys"]) > 0, json.dumps(e1["keys"], ensure_ascii=False))
            check("封闭枚举走原生 select", e1["sels"] > 0, str(e1["sels"]))
            check("自由填的项走组合框（input）", e1["opts"] > 0, str(e1["opts"]))

            # 完全体这里没有任何"带候选值的组合框" —— 这不是 bug，是数据决定的：
            # mpv 的类型系统里 Choice/Flag 一律自带取值表（=> 封闭，走 select），
            # String/Float/Integer 一律没有（=> 自由填，候选只能来自精选层的建议值）。
            # 而完全体暴露的是 813 条原始库条目，**没有精选层建议**，所以 options 全空。
            # 直接把这条不变量钉住：哪天有人往完全体里硬塞建议值，这里会红。
            check("完全体没有'带候选值的组合框'（符合 mpv 类型模型，不是缺陷）",
                  e1["nonEmpty"] == 0 and e1["empty"] == e1["opts"],
                  f"nonEmpty={e1['nonEmpty']} empty={e1['empty']} opts={e1['opts']}")

            # 0 候选的下拉仍应能打开并给出"没有候选值"的说明（不能是空白）
            first = c.js("""(() => {
              const i = document.querySelector('.opt input[data-options]');
              if (!i) return null;
              const row = i.closest('.opt');
              row.querySelector('[data-role="check"]').checked = true;
              row.classList.add('on');
              const combo = row.querySelector('.combo');
              if (combo) combo.classList.add('show');
              const r = i.getBoundingClientRect();
              return {key: row.dataset.key, x: Math.round(r.left + r.width/2),
                      y: Math.round(r.top + r.height/2)};
            })()""")
            time.sleep(0.4)
            c.click(first["x"], first["y"])
            time.sleep(0.5)
            ep = panel(c)
            check(f"完全体 {first['key']} 的下拉能打开", ep.get("open"),
                  json.dumps(ep, ensure_ascii=False)[:200])
            if ep.get("open"):
                check("完全体面板同样是深色（不是白气泡）",
                      ep["bg"] == "rgb(23, 28, 38)", ep["bg"])
                note = c.js("""(() => { const e = document.querySelector('.combo-empty');
                  return e ? e.textContent : null; })()""")
                check("没有候选值时给说明而不是空白", bool(note), str(note))
                shot("25_完全体_组合框.png")

            print("== 地狱模式：参数补全（第 14 项 ①） ==")
            # 为什么也要真机验：面板位置靠 canvas 量前缀宽度、键盘替换靠 setRangeText，
            # 这两件事读代码都"看起来对" —— 只有在真浏览器里按一次才知道有没有生效。
            c.call("Page.navigate", url="http://127.0.0.1:8765/hell.html")
            time.sleep(3.0)

            def acPanel():
                return c.js("""(() => {
                  const p = document.querySelector('.ac-pop');
                  if (!p) return {open:false};
                  const cs = getComputedStyle(p), r = p.getBoundingClientRect();
                  return {open:true,
                          items:[...p.querySelectorAll('.ac-item')].map(x => x.textContent),
                          bg: cs.backgroundColor, pos: cs.position,
                          rect:[Math.round(r.left), Math.round(r.top), Math.round(r.width)]};
                })()""")

            def acType(text):
                return c.js("""(() => { const b = document.getElementById('rawBox');
                  b.focus(); b.value = %s; b.setSelectionRange(b.value.length, b.value.length);
                  b.dispatchEvent(new Event('input', {bubbles:true})); return b.value; })()""" % json.dumps(text))

            def acKey(key):
                return c.js("""(() => { document.getElementById('rawBox').dispatchEvent(
                  new KeyboardEvent('keydown', {key:%s, bubbles:true})); return true; })()""" % json.dumps(key))

            acType("sca")
            time.sleep(1.5)
            ac = acPanel()
            check("键名位置弹出补全", ac.get("open"), json.dumps(ac, ensure_ascii=False)[:220])
            if ac.get("open"):
                check("前缀命中最前的是 scale",
                      (ac["items"] or [""])[0].startswith("scale"), str(ac["items"][:3]))
                check("面板在页面 DOM 里、跟着主题走（不是浏览器 UI 层）",
                      ac["bg"] == "rgb(23, 28, 38)", str(ac.get("bg")))
                check("面板是 fixed（贴光标，不撑开布局）", ac["pos"] == "fixed", str(ac.get("pos")))
                shot("27_地狱模式_补全_键名.png")
                acKey("ArrowDown")
                time.sleep(0.2)
                acKey("Tab")
                time.sleep(0.4)
                after = c.js("document.getElementById('rawBox').value")
                check("Tab 接受：文本被替换成候选", after == "scale", repr(after))
                check("接受后面板收起", not c.js("!!document.querySelector('.ac-pop')"))

            acType("scale=ewa")
            time.sleep(1.5)
            vac = acPanel()
            check("`key=` 之后弹出取值补全", vac.get("open"),
                  json.dumps(vac, ensure_ascii=False)[:220])
            if vac.get("open"):
                items = vac["items"] or []
                check("候选全按前缀过滤（ewa）",
                      bool(items) and all(str(i).lower().startswith("ewa") for i in items),
                      str(items[:3]))
                check("候选里有 ewa_lanczos4sharpest",
                      any(str(i).startswith("ewa_lanczos4sharpest") for i in items), str(items[:3]))
                shot("28_地狱模式_补全_取值.png")
                # 鼠标路径：点第一项也要能接受 —— `.ac-pop` 上拦 mousedown 默认
                # 就是为了"点候选时文本框别先失焦"，失去焦面板会当场消失。
                first = center(c, ".ac-item", 0)
                want = c.js("document.querySelector('.ac-item code').textContent")
                c.click(first["x"], first["y"])
                time.sleep(0.5)
                got = c.js("document.getElementById('rawBox').value")
                check("点候选也能接受（不是只有键盘能选）",
                      got == "scale=" + want, f"{got} vs scale={want}")

                acType("scale=ew")
                time.sleep(1.5)
                check("重新弹出补全（点击后没有残留状态）", (acPanel() or {}).get("open"))
                acKey("Escape")
                time.sleep(0.3)
                check("Esc 关掉面板", not c.js("!!document.querySelector('.ac-pop')"))

            acType("# sca")
            time.sleep(1.0)
            check("注释行不弹补全（误弹比不弹更烦）",
                  not c.js("!!document.querySelector('.ac-pop')"))

            print()
            if fails:
                print(f"❌ {len(fails)} 项没过：")
                for f in fails:
                    print("   - " + f)
                sys.exit(1)
            print("✅ 全部通过")
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except Exception:
                proc.kill()
    main()

# ==========================================================================
# tauri（预览外壳，2026-11-16，待做 §〇 第 15 项）
# ==========================================================================
def cmd_tauri():
    """Tauri 预览外壳的验证。

    ## 分两层：先验「配置与源码承诺的事」，再验「窗口真能跑」

    静态那层守的是几条**出问题也不会报错**的约定：

      · `frontendDist` 必须指回 `webui/static` —— 一旦有人在 `tauri/` 下复制一份前端，
        副本就会漂移，然后「测试全绿、窗口里跑的是另一套页面」（已移除的
        `electron/renderer/` 正是这么坏掉的，当年靠同步脚本兜着）；
      · **不开端口**：`main.rs` 里不许出现 `127.0.0.1` / `http://` 之类地址。
        图省事让窗口加载本地 HTTP 会一步丢掉「不开端口」和 CSP 同源兜底；
      · 退出路径必须是「关 stdin → 等 → 还不退才 kill」。只留 kill 会打断正在写的
        `mpv.conf`，留半截文件。

    动态那层的判据只有一条：**页面必须显示出后端给的数据**。
    Tauri 里没有 HTTP，所以能显示出来就证明
    「页面 → 注入的 `__MPVCB_INVOKE__` → Rust 命令 → 后端 stdio」这条链是通的。

    另外单验一件事：**关窗之后有没有孤儿后端**。这里的关窗走 WM_CLOSE（等于用户点 ×），
    验的是我们写的优雅退出，不是 `TerminateProcess`。

    用法：
        cd tauri/src-tauri && cargo build      # 或 cd tauri && npm run dev
        py tools/verify.py tauri
    """
    import json
    import socket
    import subprocess
    import time
    import urllib.request
    from pathlib import Path

    ROOT = Path(__file__).resolve().parent.parent
    TAURI = ROOT / "tauri"
    SRC = TAURI / "src-tauri"
    CONF = SRC / "tauri.conf.json"
    CARGO = SRC / "Cargo.toml"
    MAINRS = SRC / "src" / "main.rs"
    CAPS = SRC / "capabilities" / "default.json"
    EXE = SRC / "target" / "debug" / "mpv-config-builder.exe"

    PASS, FAIL = [], []


    def ck(label, cond, detail=""):
        print(("  ✅ " if cond else "  ❌ ") + label + (f"  {detail}" if detail else ""))
        (PASS if cond else FAIL).append(label)
        return bool(cond)


    def report():
        print()
        if FAIL:
            print(f"❌ {len(FAIL)} 项没过：")
            for x in FAIL:
                print("   - " + x)
            return 1
        print(f"✅ 全部通过（{len(PASS)} 项）")
        return 0


    def free_port():
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        p = s.getsockname()[1]
        s.close()
        return p


    def find_ws(port, timeout=60):
        """等 WebView2 的调试端口起来，拿页面的 WebSocket 地址。"""
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
            time.sleep(0.5)
        print(f"  （等调试端口超时：{last}）")
        return ""


    def stdio_backend_pids():
        """后端是 `python webui/server.py --stdio` —— 只能按命令行认，按进程名会误伤。"""
        ps = ("Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
              "Where-Object { $_.CommandLine -like '*webui\\\\server.py*' -and "
              "$_.CommandLine -like '*--stdio*' } | ForEach-Object { $_.ProcessId }")
        try:
            r = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=60)
        except Exception:
            return []
        return [int(x) for x in (r.stdout or "").split() if x.strip().isdigit()]


    def request_close(pid):
        """给该进程的**主窗口**发 WM_CLOSE —— 等于用户点右上角 ×，走应用自己的退出路径。

        ⚠ 不能对所有顶层窗口发：WebView2 进程里有几个隐藏的辅助窗口，对它们发
        WM_CLOSE 不会关掉应用（实测会误报「点 × 之后没退出」）。判据取
        「可见 + 有标题」，那才是用户看到的那个窗口。
        """
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        found = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def _cb(hwnd, _lparam):
            p = wintypes.DWORD(0)
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
            if p.value == pid and user32.IsWindowVisible(hwnd) \
                    and user32.GetWindowTextLengthW(hwnd) > 0:
                found.append(hwnd)
            return True

        user32.EnumWindows(_cb, 0)
        for h in found:
            user32.PostMessageW(h, 0x0010, 0, 0)          # WM_CLOSE
        return len(found)


    def main():
        print("=" * 58)
        print("Tauri 预览外壳验证")
        print("=" * 58)

        # ---- 1. 静态：它会跑起来吗、跑起来的是不是我们以为的那套 ----
        if not ck("tauri/src-tauri 脚手架在", CONF.is_file() and CARGO.is_file() and MAINRS.is_file(),
                  str(SRC)):
            return report()

        conf = json.loads(CONF.read_text(encoding="utf-8"))
        ck("tauri.conf.json 是合法 JSON", True, conf.get("productName", ""))

        dist = str(conf.get("build", {}).get("frontendDist", "")).replace("\\", "/")
        ck("frontendDist 直指 webui/static（前端只有一份，不在 tauri/ 下复制）",
           dist.endswith("webui/static")
           and (ROOT / "webui" / "static" / "index.html").is_file(), dist)

        bundle = conf.get("bundle", {})
        ck("安装包产线已开（bundle.active = true，后端目录打进资源）",
           bundle.get("active") is True and "backend" in (bundle.get("resources") or []),
           f"active={bundle.get('active')} resources={bundle.get('resources')}")

        ident = str(conf.get("identifier", ""))
        ck("identifier 填了、不是脚手架默认值", bool(ident) and "com.tauri" not in ident, ident)

        cargo = CARGO.read_text(encoding="utf-8")
        m = re.search(r'tauri = \{ version = "(\d+\.\d+\.\d+(?:-[a-z]+\.\d+)?)"', cargo)
        ck("Cargo.toml 钉死 tauri 版本（alpha 线也钉，不写成 \"3\"）",
           bool(m) and m.group(1) == "3.0.0-alpha.6", m.group(1) if m else "没找到")

        caps = json.loads(CAPS.read_text(encoding="utf-8"))
        ck("capabilities 只开 core:default，且窗口名对得上",
           caps.get("permissions") == ["core:default"]
           and caps.get("windows") == ["main"],
           f"windows={caps.get('windows')} permissions={caps.get('permissions')}")

        src = MAINRS.read_text(encoding="utf-8")
        # 注释里专门写着「别把窗口改成加载本机 HTTP 端口」，那句必然带违规字面量 ——
        # 判据落在代码上，不落在注释上。
        code = "\n".join(ln for ln in src.splitlines() if not ln.strip().startswith("//"))

        ck("后端走 stdio（不开端口：代码里没有 127.0.0.1 / http://）",
           "--stdio" in code and "server.py" in code
           and "127.0.0.1" not in code and "http://" not in code
           and "WebviewUrl::External" not in code)
        ck("注入了 __MPVCB_INVOKE__ 桥 + 同名命令",
           "__MPVCB_INVOKE__" in src and "fn mpvcb_invoke" in src)
        # v3 把运行时拆包了：不写 .runtime(Wry) 就直接 RuntimeNotConfigured（实测）
        ck("显式选了 wry 运行时（v3 不再默认带）",
           "tauri-runtime-wry" in cargo and "tauri_runtime_wry::Wry::default()" in code)
        ck("退出是「关 stdin → 等 → 才 kill」而不是立刻杀",
           "fn shutdown_backend" in src and "SHUTDOWN_GRACE" in src
           and "try_wait" in src and "child.kill()" in src)
        ck("没有写死的机器路径（盘符 / 用户名）",
           not any(s in src for s in ("C:\\Users", "D:\\Projects", "Janlhin")))

        api_js = (ROOT / "webui" / "static" / "api.js").read_text(encoding="utf-8")
        ck("无边框窗口 + 自绘标题栏（前端注入窗口按钮，浏览器版不受影响）",
           ".decorations(false)" in code and "win-controls" in api_js
           and "__TAURI_INTERNALS__" in api_js)
        ck("原生菜单：标题栏 ☰ 弹出（不是网页自绘菜单）",
           "fn mpvcb_menu" in src and "popup_menu" in src and "MenuBuilder" in src)
        ck("单实例锁：拿不到锁就退出并保留已有窗口",
           "acquire_instance_lock" in src and "try_lock" in src
           and "INSTANCE_LOCK" in src)

        copied = [str(p.relative_to(TAURI)) for p in TAURI.rglob("*")
                  if p.is_file() and p.suffix.lower() in (".html", ".css", ".js")
                  and "target" not in p.parts and "node_modules" not in p.parts
                  and "gen" not in p.parts and "backend" not in p.parts]
        ck("tauri/ 下没有第二份前端副本", not copied, "；".join(copied[:5]))

        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8", errors="replace")
        ck("编译产物不入库（.gitignore 盖住 target/）",
           "tauri/src-tauri/target/" in ignore)

        # ---- 2. 动态：窗口真跑起来了吗 ----
        if not EXE.is_file():
            print("  ⏭  跳过实机（没有 exe）：先跑 cd tauri/src-tauri && cargo build")
            return report()

        port = free_port()
        env = dict(**__import__("os").environ)
        # WebView2 的调试端口只能靠这个环境变量开，且只绑 127.0.0.1
        env["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = f"--remote-debugging-port={port}"
        before = set(stdio_backend_pids())
        proc = subprocess.Popen([str(EXE)], cwd=str(SRC), env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        cdp = None
        try:
            ws = find_ws(port)
            if not ck("窗口起来了（WebView2 调试端口可用）", bool(ws), f"port={port}"):
                return report()

            sys.path.insert(0, str(ROOT / "tools"))
            from uidriver import CDP                      # noqa: PLC0415
            cdp = CDP(ws)
            cdp.call("Page.enable")
            cdp.call("Runtime.enable")
            time.sleep(3.0)          # 等页面 boot() 把 status 拉完

            got = cdp.js("""(() => ({
              href: location.href,
              title: document.title,
              text: document.body.innerText.slice(0, 600),
              invoke: typeof window.__MPVCB_INVOKE__,
              topbar: !!document.querySelector('.topbar')
            }))()""")
            ck("页面从 Tauri 资源协议加载（不是空白页）",
               bool(got.get("href")) and len((got.get("text") or "").strip()) > 80,
               f"{got.get('href')} · 前 40 字 {(got.get('text') or '')[:40]!r}")
            ck("注入桥在（window.__MPVCB_INVOKE__ 是函数）",
               got.get("invoke") == "function", str(got.get("invoke")))
            ck("顶栏渲染出来了", got.get("topbar") is True)
            chrome = cdp.js("""(() => {
              const bar = document.querySelector('.topbar');
              return {n: document.querySelectorAll('.win-btn').length,
                      drag: !!(bar && bar.hasAttribute('data-tauri-drag-region'))};
            })()""")
            ck("自绘标题栏：4 个窗口按钮都在（菜单/最小化/最大化/关闭）",
               chrome.get("n") == 4, str(chrome.get("n")))
            ck("顶栏是拖拽区（无边框窗口还能拖动）", chrome.get("drag") is True)

            # 这条是全文的核心：页面 → 桥 → Rust 命令 → Python stdio
            call = cdp.js("""(async () => {
              const r = await window.__MPVCB_INVOKE__({path: 'status', method: 'GET', query: {}});
              return {ok: r.ok, version: (r.data && r.data.version) || null,
                      target: (r.data && r.data.target) || '',
                      lazy_pc: (r.data && r.data.lazy_pc) || '',
                      dirs: ((r.data && r.data.candidate_details) || []).length};
            })()""")
            ck("stdio 桥打通：直调 status 拿到后端版本",
               call.get("ok") is True and call.get("version") == "0.1.0",
               json.dumps(call, ensure_ascii=False))
            # 目标路径在顶栏是按 shortPath 缩过的（前 14 + … + 后 24），
            # 这里照着算一遍，页面要是写死了别的目录就对不上。
            lp = call.get("lazy_pc") or ""
            shown = lp if len(lp) <= 39 else lp[:14] + "…" + lp[-24:]
            ck("页面显示的目录来自后端探测（不是写死的）",
               bool(shown) and shown in (got.get("text") or ""),
               f"target={call.get('target')!r} shown={shown!r}")

            bad = cdp.js("""(async () => {
              const r = await window.__MPVCB_INVOKE__({path: '根本没有这个接口'});
              return {ok: r.ok, error: r.error};
            })()""")
            ck("不存在的接口返回 ok=false + error（不是抛异常）",
               bad.get("ok") is False and bool(bad.get("error")),
               json.dumps(bad, ensure_ascii=False))

            # 9 个页面都要能从打包进 exe 的同一份 static 里打开
            pages = ["index.html", "basic.html", "advanced.html", "expert.html",
                     "analyze.html", "keys.html", "downloads.html", "guide.html",
                     "hell.html"]
            base = got.get("href", "").rsplit("/", 1)[0]
            page_bad, nav_err = [], ""
            if not base.startswith("http"):
                nav_err = f"拿不到页面基址：{got.get('href')!r}"
                page_bad = pages
            else:
                for name in pages:
                    cdp.call("Page.navigate", url=f"{base}/{name}")
                    time.sleep(1.2)
                    r = cdp.js("""(() => ({
                      len: document.body.innerText.trim().length,
                      topbar: !!document.querySelector('.topbar')
                    }))()""")
                    if r.get("len", 0) < 40 or not r.get("topbar"):
                        page_bad.append(f"{name}(len={r.get('len')}, topbar={r.get('topbar')})")
            ck("9 个页面在 Tauri 里都能打开且有内容", not page_bad,
               nav_err or "；".join(page_bad))
        finally:
            if cdp is not None:
                try:
                    cdp.sock.close()
                except Exception:
                    pass

            # ---- 3. 关窗：走 WM_CLOSE（优雅退出），不是 terminate ----
            hit = request_close(proc.pid)
            deadline = time.time() + 12
            while time.time() < deadline and proc.poll() is None:
                time.sleep(0.3)
            ck("关窗请求送达（WM_CLOSE 发到了窗口）", hit > 0, f"命中 {hit} 个窗口")
            ck("应用自己退出了（不是被强杀）", proc.poll() is not None,
               f"exit={proc.poll()}")

            # 后端必须跟着走：stdin 关了它会读到 EOF 自己退
            left = []
            deadline = time.time() + 15
            while time.time() < deadline:
                left = [p for p in stdio_backend_pids() if p not in before]
                if not left:
                    break
                time.sleep(0.4)
            ck("退出后没有孤儿后端进程", not left, f"还剩 {left}")

            if proc.poll() is None:           # 兜底，别把测试进程留在机器上
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except Exception:
                    proc.kill()

        return report()


    sys.exit(main())


# ==========================================================================
# pack（原 check_pack.py）
# ==========================================================================
def cmd_pack():
    """对**打包产物**做端到端验证。

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
        py tools/verify.py pack
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
                    "LICENSE", "docs/NOTICE.txt", "docs/入门指南.md"):
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
    if not EXE.is_file():
        sys.exit(f"没找到产物：{EXE}\n先跑：py -m PyInstaller packaging/backend.spec")
    sys.exit(main())

# ==========================================================================
# conflicts（原 compare_conflicts.py）
# ==========================================================================
def cmd_conflicts():
    """C-1 等价性证明：新规则表 vs 旧 if 长链，逐字段比对。

    为什么不能只靠 tests/data/conflicts_golden.json：
    那份基准是 55 个**我挑的**用例。挑漏的搭配 = 漏掉的差异。
    所以这里换成**系统枚举**：
      A. 每个会被读到的选项 × 每种取值，单独设一次（看单条规则）；
      B. 选项两两组合（看规则之间的相互影响，尤其是 keys 的动态部分）；
      C. shader 列表：单条、两两、三三，覆盖各家族 + 锐化误伤样本；
      D. memc 路径：各种前缀、各种斜杠、大小写、空串；
      E. A~D 的交叉（两两选项 + shader + memc）。

    每个用例都同时喂给两个实现，要求：
      * 返回的 dict 列表**逐字段完全相等**（id/level/title/detail/fix/keys，含顺序）；
      * keys 顺序也算 —— 虽然界面用 set 消费，但顺序变了说明实现偷改了构造方式。

    用法：py -3 tools/verify.py conflicts
    """
    import itertools
    import json
    import sys
    from pathlib import Path

    ROOT = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(ROOT))

    from core.conflicts import (                 # noqa: E402
        GPU_NEXT_ONLY, GPU_ONLY, _legacy_detect_conflicts, detect_conflicts,
    )

    # 会被 detect_conflicts 读到的选项，以及各自有代表性的取值。
    # 取值里故意混入大小写、带空格、非数字、空串、缺省 —— 这些是判定的边界。
    VALUES = {
        "vo": ["", "gpu", "GPU", "gpu-next", "GPU-NEXT", "direct3d", " Gpu "],
        "sigmoid-upscaling": ["", "yes", "no", "YES", "auto", "true", "1", "0", "on"],
        "linear-upscaling": ["", "yes", "no", "auto", "1", "off"],
        "interpolation": ["", "yes", "no", "auto", "1", "YES"],
        "video-sync": ["", "audio", "display-resample", "display-resample-vdrop",
                       "display-vdrop", "DISPLAY-RESAMPLE", "desync"],
        "tscale": ["", "mitchell", "catmull_rom", "oversample", "linear"],
        "deband": ["", "yes", "no", "auto", "1"],
        "deband-iterations": ["", "0", "1", "2", "3", "4", "5", "6", "-1", "abc", "2.5"],
        "deband-range": ["", "0", "15", "16", "31", "32", "33", "64", "abc"],
        "icc-profile": ["", "C:/icc/srgb.icc", "~~/icc/x.icc"],
        "icc-profile-auto": ["", "yes", "no", "auto", "1"],
        "target-prim": ["", "bt.709", "auto"],
        "target-trc": ["", "srgb", "auto"],
        "target-gamut": ["", "bt.709", "auto"],
        "tone-mapping": ["", "hable", "Hable", "HABLE", "spline", "bt.2390", "clip"],
        "hdr-compute-peak": ["", "yes", "no", "auto"],
        "cache": ["", "yes", "no", "auto", "1", "0"],
        "demuxer-max-bytes": ["", "512MiB", "0"],
        "gamut-mapping-mode": ["", "clip", "auto"],
        "corner-rounding": ["", "10"],
        "sharpen": ["", "0.5"],
        "tone-mapping-max-boost": ["", "2"],
    }
    # 只设一次就够、不值得全取的「大集合」选项：随便挑几个代表
    EXTRA_SINGLE = [
        "lut", "image-lut", "icc-use-luma", "sdr-adjust-gamma", "hdr-reference-white",
        "treat-srgb-as-power22", "target-colorspace-hint-mode", "inverse-tone-mapping",
        "sub-hdr-peak", "border-background", "allow-delayed-peak-detect",
        "hdr-contrast-recovery", "hdr-peak-percentile", "target-contrast", "target-lut",
        "image-subs-hdr-peak", "tone-mapping-visualize", "target-colorspace-hint-strict",
    ]

    SHADER_SETS = [
        [],
        [""],
        ["   "],
        ["", "  ", ""],
        ["~~/shaders/FSRCNNX_x2_8-0-4-1.glsl"],
        ["~~/shaders/FSRCNNX_x2_16-0-4-1.glsl"],
        ["~~/shaders/FSRCNNX_x2_8-0-4-1.glsl", "~~/shaders/FSRCNNX_x2_16-0-4-1.glsl"],
        ["~~/shaders/RAVU_Zoom_R3.glsl"],
        ["~~/shaders/Anime4K_Upscale_CNN_x2_M.glsl"],
        ["~~/shaders/Anime4K_Upscale_CNN_x2_M.glsl", "~~/shaders/Anime4K_Upscale_CNN_x2_L.glsl"],
        ["~~/shaders/ArtCNN_C4F32.glsl"],
        ["~~/shaders/ESRGAN_x2.glsl"],
        ["~~/shaders/NNEDI3_nns256_win8x6.glsl"],
        ["~~/shaders/Ani4Kv2_ArtCNN_C4F32.glsl"],
        ["~~/shaders/AMD_CAS.glsl"],
        ["~~/shaders/Adaptive_sharpen.glsl"],
        ["~~/shaders/QCOM_SGEDS.glsl"],
        ["~~/shaders/amd_cas.glsl"],
        # 锐化误伤样本：文件名含 cas 子串但不是锐化
        ["~~/shaders/Cascade_Sharpen.glsl"],
        ["~~/shaders/casual_upscale.glsl"],
        ["~~/shaders/Lumiere_CAS_4.glsl", "~~/shaders/FSRCNNX_x2_8-0-4-1.glsl"],
        # 多家族
        ["~~/shaders/FSRCNNX_x2_8-0-4-1.glsl", "~~/shaders/RAVU_Zoom_R3.glsl",
         "~~/shaders/Anime4K_Upscale_CNN_x2_M.glsl"],
        # 锐化不在链尾 / 在链尾 / 只有一条
        ["~~/shaders/AMD_CAS.glsl", "~~/shaders/FSRCNNX_x2_8-0-4-1.glsl"],
        ["~~/shaders/FSRCNNX_x2_8-0-4-1.glsl", "~~/shaders/AMD_CAS.glsl"],
        ["~~/shaders/AMD_CAS.glsl", "~~/shaders/Adaptive_sharpen.glsl"],
        ["~~/shaders/AMD_CAS.glsl", "~~/shaders/FSRCNNX_x2_8-0-4-1.glsl",
         "~~/shaders/RAVU_Zoom_R3.glsl"],
        ["~~/shaders/FSRCNNX_x2_8-0-4-1.glsl", "~~/shaders/AMD_CAS.glsl",
         "~~/shaders/RAVU_Zoom_R3.glsl"],
        # 大小写 / 反斜杠路径
        ["~~\\shaders\\FSRCNNX_x2_8-0-4-1.GLSL"],
        ["C:\\mpv\\shaders\\Anime4K_Upscale_CNN_x2_M.glsl"],
    ]

    MEMC_SETS = [
        "",
        "~~/vs/MEMC_RIFE_NV.vpy",
        "~~/vs/memc_rife_nv.vpy",
        "~~\\vs\\MEMC_RIFE_NV.vpy",
        "C:\\portable_config\\vs\\MEMC_RIFE_NV.vpy",
        "~~/vs/SR_ESRGAN_x2.vpy",
        "~~/vs/sr_esrgan_x2.vpy",
        "~~/vs/MIX_UAI_ESRGAN.vpy",
        "~~/vs/MIX_anything.vpy",
        "~~/vs/SR.vpy",
        "MEMC_RIFE_NV.vpy",
        "SR_ESRGAN_x2.vpy",
        "   ",
    ]


    def call(fn, values, shaders, memc):
        return fn(values, shaders=shaders, memc=memc)


    def diff(old, new):
        """返回第一个不同之处，完全相同则 None。"""
        if old == new:
            return None
        if len(old) != len(new):
            return f"条数 {len(old)} != {len(new)}"
        for i, (a, b) in enumerate(zip(old, new)):
            if a != b:
                fa = {k: a[k] for k in a if a[k] != b.get(k)}
                fb = {k: b[k] for k in b if b[k] != a.get(k)}
                return f"第 {i} 条不同 旧={json.dumps(fa, ensure_ascii=False)} 新={json.dumps(fb, ensure_ascii=False)}"
        return "未知差异"


    def main():
        cases = []
        # A. 单选项全取值
        for key, vals in VALUES.items():
            for v in vals:
                cases.append(({key: v}, [], ""))
        # A2. 大集合选项各来一次
        for key in EXTRA_SINGLE:
            cases.append(({key: "x"}, [], ""))
            cases.append(({"vo": "gpu", key: "x"}, [], ""))
            cases.append(({"vo": "gpu-next", key: "x"}, [], ""))
        # B. 两两组合（只看同时非空的搭配，否则大部分是 A 的重复）
        keys = list(VALUES)
        for k1, k2 in itertools.combinations(keys, 2):
            for v1 in VALUES[k1]:
                for v2 in VALUES[k2]:
                    if v1 and v2:
                        cases.append(({k1: v1, k2: v2}, [], ""))
        # C/D. shader × memc
        for sh in SHADER_SETS:
            for mc in MEMC_SETS:
                cases.append(({}, sh, mc))
        # E. 交叉：A 的每个用例 × 若干 shader/memc 代表
        reps = [([], ""), (["~~/shaders/AMD_CAS.glsl"], ""),
                (["~~/shaders/FSRCNNX_x2_8-0-4-1.glsl",
                  "~~/shaders/Anime4K_Upscale_CNN_x2_M.glsl"], "~~/vs/MEMC_RIFE_NV.vpy"),
                (["~~/shaders/RAVU_Zoom_R3.glsl"], "~~/vs/SR_ESRGAN_x2.vpy")]
        base = [(v, [], "") for v in ({k: val} for k, vals in VALUES.items() for val in vals)]
        for values, _, _ in base:
            for sh, mc in reps:
                cases.append((values, sh, mc))

        n_old_hits = 0
        bad = []
        for i, (values, shaders, memc) in enumerate(cases):
            old = call(_legacy_detect_conflicts, values, shaders, memc)
            new = call(detect_conflicts, values, shaders, memc)
            if old:
                n_old_hits += 1
            d = diff(old, new)
            if d:
                bad.append((i, values, shaders, memc, d))

        print(f"用例总数 {len(cases)}（其中 {n_old_hits} 个有输出）")
        if bad:
            print(f"!!! 不一致 {len(bad)} 处：")
            for i, values, shaders, memc, d in bad[:10]:
                print(f"  #{i} values={json.dumps(values, ensure_ascii=False)} "
                      f"shaders={json.dumps(shaders, ensure_ascii=False)} memc={memc!r}")
                print(f"      {d}")
            if len(bad) > 10:
                print(f"  （只显示前 10 处）")
            return 1
        print("新旧实现逐字段完全一致 ✓")
        return 0
    raise SystemExit(main())


# ==========================================================================
# precommit（提交门禁，工程规则 L2 本地门禁层）
# ==========================================================================
def cmd_precommit():
    """提交门禁：快到每次提交都跑得起，严到脏提交进不了历史。

    为什么要有它：工程规则把「提交门禁」定为强制项（L2），而本仓库此前**完全没有** ——
    CI 又因为凭据缺 `workflow` scope 从未真正运行过（见 `TASKS.md` T1 / T2），
    于是 18 个提交是在没有任何门禁的情况下进的历史。在 CI 转绿之前，
    这条钩子是**唯一真的会跑**的校验通道。

    ⚠ 为什么这里**不**跑 `docs` 与全套单测：2026-10-09 实测 `verify.py docs`
    单独跑 16 分钟仍未结束（它在 `all` 里是正常通过的，原因待查 —— 已登记为
    `TASKS.md` 遗留项）。门禁一旦慢到几分钟，人就会用 `--no-verify` 绕过去，
    而**慢门禁比没门禁更糟**：它把「绕过」变成常态。所以这里只放秒级且确定性的
    三项，行为与文档的一致性仍由 `verify.py --offline` 在推送前把关。

    跑什么：
      1. 源码可编译 —— `core/` `webui/` `tools/` `tests/` 下所有 `.py`
      2. 暂存的文本文件行尾必须是 LF（`.bat` / `.cmd` / `.ps1` 除外，它们要 CRLF）
      3. 脚本基线：仓库无 `.bat`/`.cmd`；`.ps1` 必须 UTF-8 带 BOM + CRLF
         （规则见 `script_baseline_problems`，2026-10-14 起）
      4. 根目录白名单 + README 目录声明（`cmd_layout`，2026-11-17 起）
      5. 技术栈版本登记同源（`cmd_stack`，2026-11-17 起）

    用法（仓库根目录）：
        python tools/verify.py precommit
    退出码：0 = 可以提交；1 = 不许提交。

    ⚠ 第 2 项查的是**工作区文件**，不是索引内容：`.gitattributes` 会在 `git add`
    时把行尾归一化，索引里永远是 LF —— 查索引查不出问题。真正的风险是工作区里
    存着 CRLF（`AGENTS.md` §2.3），而 `verify.py docs` 逐字节读的正是工作区。
    """
    import subprocess as _sp

    bad = []

    # 1. 源码可编译（用内置 compile() 而不是 py_compile —— 后者会在源码旁边写 .pyc）
    sources = []
    for d in ("core", "webui", "tools", "tests"):
        sources += sorted((ROOT / d).rglob("*.py")) if (ROOT / d).is_dir() else []
    broken = []
    for f in sources:
        try:
            compile(f.read_text(encoding="utf-8"), str(f), "exec")
        except SyntaxError as e:
            broken.append(f"{f.relative_to(ROOT)}:{e.lineno} {e.msg}")
        except (UnicodeDecodeError, OSError) as e:
            broken.append(f"{f.relative_to(ROOT)}: {type(e).__name__}")
    if broken:
        print("  ❌ 源码可编译：" + "；".join(broken[:5]))
        bad.append("源码可编译")
    else:
        print(f"  ✅ 源码可编译（{len(sources)} 个 .py）")

    # 2. 行尾：暂存的文件里，文本文件必须 LF
    CRLF_EXTS = {".bat", ".cmd", ".ps1"}          # 这三类归第 3 项统一判
    TEXT_EXTS = {".py", ".md", ".txt", ".json", ".html", ".css", ".js",
                 ".yml", ".yaml", ".vpy", ".conf", ".ini", ".adoc"}
    staged = _sp.run(["git", "diff", "--cached", "--name-only",
                      "--diff-filter=ACM", "-z"],
                     capture_output=True, cwd=str(ROOT))
    names = [n for n in staged.stdout.decode("utf-8", "replace").split("\0") if n]
    eol_bad = []
    for n in names:
        f = ROOT / n
        if not f.is_file() or f.suffix.lower() in CRLF_EXTS:
            continue
        if f.suffix.lower() not in TEXT_EXTS:
            continue
        if b"\r\n" in f.read_bytes():
            eol_bad.append(n)
    if eol_bad:
        print("  ❌ 这些文件含 CRLF，必须 LF（AGENTS.md §2.3）：" + "、".join(eol_bad[:10]))
        bad.append("行尾")

    # 3. 脚本基线（规则与 cmd_all 的 check_script_baseline 共用，只有一份）
    sb_bad, sb_stat = script_baseline_problems()
    if sb_bad:
        print("  ❌ 脚本基线不过：" + "；".join(sb_bad))
        bad.append("脚本基线")
    else:
        print(f"  ✅ 脚本基线（无 .bat/.cmd，.ps1 带 BOM+CRLF）："
              f".ps1 {sb_stat['ps1']} 个")

    # 4. 根目录白名单（秒级：只读 git ls-files 与 README）
    if cmd_layout() != 0:
        bad.append("根目录布局")

    # 5. 技术栈版本登记（秒级：读三个文本文件）
    if cmd_stack() != 0:
        bad.append("版本登记")

    if bad:
        print(f"\n❌ 不许提交：{'、'.join(bad)} 没过。"
              f"（用 --no-verify 绕过去不算通过，那是把门禁关掉）")
        return 1
    print("\n✅ 提交门禁通过")
    return 0


# ==========================================================================
# layout（根目录白名单 + README 目录声明）
# ==========================================================================
#: 允许出现在仓库根的散文类文档（只有这五份）
ROOT_DOCS = ("README.md", "AGENTS.md", "DECISIONS.md", "TASKS.md", "MANIFEST.md")
#: 允许出现在仓库根的单个文件（点文件 / 许可证 / 运行时版本文件）
ROOT_FILES = {".gitattributes", ".gitignore", ".python-version", "LICENSE"}
#: 允许出现在仓库根的目录（代码、数据、文档、协作平台配置）
ROOT_DIRS = {
    "core", "data", "docs", "packaging", "scripts", "tauri", "tests", "tools",
    "webui", ".github", ".githooks",
}


def cmd_layout():
    """根目录白名单：`git ls-files` 的顶层条目必须都在声明范围内。

    为什么要有它：规则要求「除五个文档外，根目录不放任何散文类文件」，
    新增条目要先询问。靠人记是记不住的 —— 2026-11-17 一次搬迁前，
    根目录同时躺着 4 份界面文档、NOTICE、中文 README、跳转页、原始数据、
    启动器共 9 个白名单外条目。这里把它变成可机器比对的一步。

    判两件事：
      1. 顶层条目 ⊆（五文档 + 允许的单文件 + 允许的目录）
      2. README 的「## Layout」段确实声明了每个允许的目录
         （声明是校验的数据源；目录不在 README 里 = 文档与代码不一致）

    用法（仓库根目录）：
        python tools/verify.py layout
    """
    bad = []
    # -z + NUL 分隔：路径里的中文不会被 core.quotepath 转义成 `"docs/...`
    p = subprocess.run(["git", "ls-files", "-z"], cwd=str(ROOT), capture_output=True)
    if p.returncode != 0:
        print("  ❌ 读不到 git ls-files（不在 git 仓库里？）")
        return 1
    tops = sorted({entry.split("/")[0]
                   for entry in p.stdout.decode("utf-8").split("\0") if entry.strip()})
    allowed = set(ROOT_DOCS) | ROOT_FILES | ROOT_DIRS
    unknown = [t for t in tops if t not in allowed]
    if unknown:
        bad.append("白名单外条目：" + "、".join(unknown))
    for t in unknown:
        print(f"  ❌ 根目录有白名单外条目：{t}（搬进子目录，或先在 DECISIONS 登记并获得批准）")

    # README 的目录声明（数据源）——每个允许的目录都必须被写出来
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    m = re.search(r"^## Layout\n(.*?)(?=^## )", readme, re.S | re.M)
    block = m.group(1) if m else ""
    missing = [d for d in sorted(ROOT_DIRS) if f"{d}/" not in block]
    if not block:
        bad.append("README 缺「## Layout」段")
    elif missing:
        bad.append("README 目录声明缺：" + "、".join(missing))
    for d in missing:
        print(f"  ❌ README「## Layout」没声明目录：{d}/")

    print(f"  顶层条目 {len(tops)} 个，白名单 {len(allowed)} 项")
    if bad:
        print("❌ 根目录布局不合规：" + "；".join(bad))
        return 1
    print("✅ 根目录布局通过（顶层条目全在白名单内，README 已声明每个目录）")
    return 0


# ==========================================================================
# stack（技术栈与运行时版本登记的一致性）
# ==========================================================================
def cmd_stack():
    """版本登记必须与代码/CI 同源，不能各写各的。

    规则要求运行时版本写进版本文件、CI 与本地同源，并在 README 登记
    「语言与版本 / 框架主版本 / 包管理器与锁 / 版本文件路径」。
    这里验三件事：
      1. `.python-version` 存在，且与 CI 里所有 `python-version:` 一致
      2. README 的「Stack and runtime versions」段写出版本文件路径与版本号
      3. `tauri/src-tauri/Cargo.toml` 里的 tauri 版本出现在 README（框架主版本登记）

    用法（仓库根目录）：
        python tools/verify.py stack
    """
    bad = []

    vf = ROOT / ".python-version"
    version = vf.read_text(encoding="utf-8").strip() if vf.is_file() else ""
    if not version:
        bad.append("缺 .python-version（运行时版本必须写进版本文件）")
    ci_versions = []
    for wf in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        for m in re.finditer(r"python-version:\s*'?([0-9.]+)'?", wf.read_text(encoding="utf-8")):
            ci_versions.append((wf.name, m.group(1)))
    for name, v in ci_versions:
        if v != version:
            bad.append(f"{name} 的 python-version={v} 与 .python-version={version} 不一致")
    if not ci_versions:
        bad.append("CI 里没声明 python-version（本地与 CI 必须同源）")

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    m = re.search(r"^## Stack and runtime versions\n(.*?)(?=^## )", readme, re.S | re.M)
    block = m.group(1) if m else ""
    if not block:
        bad.append("README 缺「Stack and runtime versions」段")
    else:
        if version and version not in block:
            bad.append(f"README 技术栈表没写 Python {version}")
        if ".python-version" not in block:
            bad.append("README 技术栈表没写版本文件路径 .python-version")

    cargo = (ROOT / "tauri" / "src-tauri" / "Cargo.toml").read_text(encoding="utf-8")
    tm = re.search(r'\ntauri\s*=\s*\{(.*?)\}', cargo, re.S)
    tauri_ver = ""
    if tm:
        vm = re.search(r'version\s*=\s*"([^"]+)"', tm.group(1))
        tauri_ver = vm.group(1) if vm else ""
    if tauri_ver and tauri_ver not in block:
        bad.append(f"README 技术栈表没写 Tauri {tauri_ver}（Cargo.toml 里的实际版本）")

    print(f"  Python {version or '（缺）'}；CI {len(ci_versions)} 处声明；"
          f"Tauri {tauri_ver or '（没解析到）'}")
    if bad:
        print("❌ 版本登记不一致：" + "；".join(bad))
        return 1
    print("✅ 技术栈与运行时版本登记一致（版本文件 / CI / README 同源）")
    return 0


# ==========================================================================
# commitmsg（提交信息门禁，.githooks/commit-msg 调它）
# ==========================================================================
#: Conventional Commits 允许的类型（本项目用得上的子集）
_COMMIT_TYPES = ("feat", "fix", "docs", "style", "refactor", "perf", "test",
                 "build", "ci", "chore", "revert")
_COMMIT_RE = re.compile(
    r"^(%s)(\([^()\s]+\))?!?: [^\s].*$" % "|".join(_COMMIT_TYPES))


def cmd_commitmsg():
    """提交信息门禁：Conventional Commits + 单提交体量提示。

    为什么放在**钩子**而不是 CI：Git 只在本地拦得住「随手写的提交信息」，
    CI 看到时已经进了历史；规则把提交门禁定为 L2 层，正是这个位置。

    判什么：
      1. 首行符合 `type(scope): 摘要`（`Merge`/`Revert` 放行）
      2. 暂存改动超过 400 行只**提示**不拦截（规则是「超限告警」，
         不是禁提交；拆不拆由人判断，别让门禁替人做决定）

    用法（由钩子调用）：
        python tools/verify.py commitmsg .git/COMMIT_EDITMSG
    """
    if not sys.argv[1:]:
        print("❌ 用法：python tools/verify.py commitmsg <提交信息文件>")
        return 2
    path = Path(sys.argv[1])
    if not path.is_file():
        print(f"❌ 读不到提交信息文件：{path}")
        return 2
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    subject = ""
    for line in lines:
        if line.startswith("#"):
            continue
        if line.strip():
            subject = line.strip()
            break

    if not subject:
        print("❌ 提交信息是空的（首行写 type(scope): 摘要）")
        return 1
    if subject.startswith(("Merge ", "Revert ", 'Revert "')):
        print(f"✅ 放行（合并/回滚提交）：{subject}")
        return 0
    if not _COMMIT_RE.match(subject):
        print("❌ 提交信息不符合 Conventional Commits：")
        print(f"   {subject}")
        print("   应写成：type(scope): 摘要 —— type ∈ "
              + " / ".join(_COMMIT_TYPES))
        print("   例：feat(webui): 地狱模式支持键名补全")
        return 1

    # 体量提示（不阻断）：暂存区 added+deleted 行数
    p = subprocess.run(["git", "diff", "--cached", "--numstat"],
                       cwd=str(ROOT), capture_output=True)
    total = 0
    if p.returncode == 0:
        for line in p.stdout.decode("utf-8", "replace").splitlines():
            parts = line.split("\t")
            if len(parts) >= 2:
                for n in parts[:2]:
                    total += int(n) if n.isdigit() else 0
    if total > 400:
        print(f"⚠ 本次暂存改动 {total} 行（规范建议单提交 ≤400 行）——"
              f"能拆就拆，拆不动请在提交信息正文里写清理由。")
    print(f"✅ 提交信息合规：{subject}")
    return 0


COMMANDS = {
    "all": cmd_all,
    "precommit": cmd_precommit,
    "commitmsg": cmd_commitmsg,
    "layout": cmd_layout,
    "stack": cmd_stack,
    "docs": cmd_docs,
    "topnav": cmd_topnav,
    "i18n": cmd_i18n,
    "status": cmd_status,
    "ctxmenu": cmd_ctxmenu,
    "hotkeys": cmd_hotkeys,
    "motion": cmd_motion,
    "stdio": cmd_stdio,
    "presets": cmd_presets,
    "ui": cmd_ui,
    "tauri": cmd_tauri,
    "pack": cmd_pack,
    "conflicts": cmd_conflicts,
}


def main(argv=None):
    if argv is None:
        argv = sys.argv
    name = argv[1] if len(argv) > 1 else "all"
    if name in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    if name.startswith("-"):
        # 参数直通 preflight（如 --offline），不重排 argv
        return cmd_all()
    if name not in COMMANDS:
        print(f"❌ 未知子命令：{name}\n")
        print(__doc__)
        return 2
    sys.argv = [argv[0], *argv[2:]]
    return COMMANDS[name]()


if __name__ == "__main__":
    raise SystemExit(main())

