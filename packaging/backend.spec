# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 配方：把 Python 后端打成独立 exe（B1-2 / specs/backend-packaging.md）。

用法（仓库根目录）：

    py -m PyInstaller packaging/backend.spec

产物：dist/MPVConfigBuilderBackend/MPVConfigBuilderBackend.exe（外加 _internal/）

⚠ 这个文件放在 `packaging/` 而不是 `build/`：`.gitignore` 忽略了整个 `build/`
（那是 PyInstaller 的工作目录），配方放进去会被一起忽略掉。
而**配方是源码，必须入库** —— 放在 packaging/ 就不用写例外规则。

## 为什么是 onedir 而不是 onefile

这是给 **Electron 当后端**用的，不是给人双击的绿色版：

1. **启动速度**：Electron 每次启动都要 spawn 它，onefile 每次都要解压到临时目录，
   多等 2–5 秒；onedir 直接跑，~0.2 秒。
2. **协议安全**：stdio 模式下 stdout 是 JSON 协议流，**一行杂音就让前端失联**。
   onefile 的 bootloader 要解压、可能打印进度；onedir 没这一步。
3. 产物是给 electron-builder 塞进安装包的，**用户看不到这些文件**，
   「单文件好看」在这里没价值。

## 为什么必须 console=True（不能加 --windowed）

`--windowed` 会把标准流换掉（Windows 下没有控制台），**stdio 协议直接废**。
这个后端跟 Electron 说话全靠 stdin/stdout，所以必须保留控制台。

## 目录结构（打包后）

    sys._MEIPASS/                 ← onedir 下就是 exe 同级的 _internal/
        data/                     3 个 JSON（选项库 / 键位 / 命令）
        webui/static/             9 个页面 + style.css + api.js + state.js
        *.md                      界面里「文档」页要实时渲染这些
        LICENSE / NOTICE.txt      许可证与第三方归属（分发合规）
        core/  webui/             Python 代码

⚠ 漏掉 data/ 或 webui/static/ 或 *.md，程序**照样能启动**，只是某个页面空白
—— 这种错只有把每个接口都打一遍才发现。所以有 tools/verify.py pack 专门验它。
"""
import sys
from pathlib import Path

# spec 是被 exec 执行的，没有 __file__ —— 用 SPECPATH（PyInstaller 注入的变量）
ROOT = Path(SPECPATH).resolve().parent          # noqa: F821  (SPECPATH 由 PyInstaller 提供)

# ---- 要一起打进去的数据 ----
# 每一项是 (源, 包内目标目录)
datas = [
    (str(ROOT / "data"), "data"),
    (str(ROOT / "webui" / "static"), "webui/static"),
    (str(ROOT / "LICENSE"), "."),
    (str(ROOT / "NOTICE.txt"), "."),
]

# 根目录的 md 全部带上（界面里的「文档」页是**实时渲染**它们的）。
# 为什么不写死那 4 份：guide 之外还有别的入口会读 md，漏一份就是某个页面空白，
# 而多带几份的代价只是几百 KB。不过要把「不参与运行」的排除掉：
MD_SKIP = {
    # 给开发者看的，不是界面文档（界面里点不到，带上是白占体积）
}
for md in sorted(ROOT.glob("*.md")):
    if md.name in MD_SKIP:
        continue
    datas.append((str(md), "."))

# ---- 确定要 import 的入口 ----
# 后端入口是 webui/server.py。它靠 `sys.path.insert(0, ROOT)` + `from core.xxx`
# 这种**顶层导入**工作，所以 core 与 webui 都在仓库根下、平级。
hiddenimports = [
    # server.py 里的分发层是「按属性名解析」的（webui/api.py 存字符串），
    # PyInstaller 的静态分析看不到这些名字 —— 但它们都在 server 模块里，
    # 只要 server 被 import 就都在。这里额外列出的是**间接按名字取**的东西。
    "webui.api",
    "webui.stdio",
]

# ---- 明确排除 ----
# 这些在开发机上被 import 过（或有间接依赖），但对本程序毫无用处。
#
# ⚠⚠ 血泪教训：**不要把 `email` 放进来**。
# 它看着跟本程序八竿子打不着（我们又不发邮件），但 **`http.server` 依赖它**
# —— 于是打包出来的 exe 一启动就 `ModuleNotFoundError: No module named 'email'`，
# 而且现象很有迷惑性：**exe 存在、体积正常、资源都在，就是退出码 1、一点输出都没有**
# （因为崩在 import 阶段，还没轮到 stdio 循环打印任何东西）。
# 是 `tools/verify.py pack` 抓出来的 —— 它要求 exe 真的把接口打一遍。
#
# 教训：**排除标准库要格外小心**，它们之间的依赖关系不看源码是猜不出来的。
# 下面这些是确认过安全的（第三方大库 + 纯开发工具）。
excludes = [
    "tkinter", "unittest", "pydoc", "doctest", "test", "distutils",
    "numpy", "PIL", "matplotlib", "pandas", "scipy", "setuptools", "pip",
    "xmlrpc", "pdb", "lib2to3",
]

block_cipher = None

a = Analysis(
    [str(ROOT / "webui" / "server.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MPVConfigBuilderBackend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                  # 杀软误报率高，官方文档里也记了这条
    console=True,               # ⚠ 必须是 True：--windowed 会干掉标准流，stdio 协议就废了
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="MPVConfigBuilderBackend",
)

# 让 spec 被直接 exec 时也能跑（PyInstaller 会忽略 __main__ 之外的东西）
if __name__ == "__main__":
    print(f"已收集 {len(datas)} 项数据文件（其中 md "
          f"{sum(1 for s, _ in datas if s.endswith('.md'))} 份）", file=sys.stderr)
