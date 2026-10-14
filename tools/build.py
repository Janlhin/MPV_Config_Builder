# -*- coding: utf-8 -*-
"""构建 / 生成工具总入口：把「重新生成产物」的脚本收拢到一个命令。

原来的 tools/ 里这些脚本各自为政（build_options_db / build_keybindings /
make_icon / sync_version / fix_bat / gen_conflicts_golden），每个都重复一遍
「找仓库根 + 插 sys.path + main()」的样板。2026-10-09 合并到这里 ——
**只收拢，不改逻辑**，每个子命令都保留了原脚本自己的说明（见各函数 docstring）。

用法（仓库根目录）：

    py -3 tools/build.py <子命令> [参数]

子命令：

    options-db      重新生成 data/mpv_options_zh.json（mpv 升级后跑一次）
    keybindings     重新生成 data/mpv_keybindings.json + data/mpv_commands.json
    icon            生成 electron/assets/icon.ico + icon.png
    ps1             把仓库里的 .ps1 统一成 UTF-8 带 BOM + CRLF
    version         把 core/schema.py 的版本号同步到 electron/package.json
                    （--check 只检查不改，CI / 测试用）
    golden          重新生成 tests/data/conflicts_golden.json（冲突检测快照）
                    （--check 只比对不写盘）

其中 options-db / keybindings 需要本机有 mpv 或能联网，跑不动时脚本会自己说。
"""
import argparse
import json
import os
import re
import struct
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")


# --------------------------------------------------------------------------
# options-db
# --------------------------------------------------------------------------
def cmd_options_db():
    """重新生成 mpv 全量选项数据库 JSON。

    mpv 升级后重新导出 ``mpv.com --list-options > _mpv_options_raw.txt``，
    再跑一次本命令即可刷新 ``data/mpv_options_zh.json``。
    """
    from core.options_db import DB_PATH, build_db  # noqa: E402

    db = build_db()
    meta = db["meta"]

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DB_PATH, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(db, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    size_kb = DB_PATH.stat().st_size / 1024
    print(
        "顶层 %d 项 / 有中文 %d 项 / 分类 %d 个"
        % (meta["count"], meta["with_zh"], len(db["groups"]))
    )
    print("已写入 %s（%.1f KB）" % (DB_PATH, size_kb))
    print("分类：" + "、".join(db["groups"]))
    return 0


# --------------------------------------------------------------------------
# keybindings
# --------------------------------------------------------------------------
def cmd_keybindings():
    r"""生成按键绑定数据库（data/mpv_keybindings.json + data/mpv_commands.json）。

    数据不是抄来的，是**从你自己这份 mpv 里问出来的**：

        mpv --no-config --idle --vo=null --ao=null --script=_dump_bindings.lua

    lua 脚本读 `input-bindings` 属性（209 条内置绑定，带命令、注释、优先级、来源 section），
    命令表则来自 `mpv --input-cmdlist`（86 条，带参数签名与说明）。

    用法：py -3 tools/build.py keybindings ["C:\\Program Files\\mpv-lazy\\mpv.com"]

    mpv 升级、或者换了别的 mpv 构建之后重跑一次即可。
    """
    LUA = Path(__file__).resolve().parent / "_dump_bindings.lua"
    DATA = ROOT / "data"

    DEFAULT_MPV = r"C:\Program Files\mpv-lazy\mpv.com"
    CANDIDATES = [
        DEFAULT_MPV,
        r"C:\Program Files\mpv-lazy\mpv.exe",
        r"C:\Program Files\mpv\mpv.com",
        r"C:\Program Files\mpv\mpv.exe",
    ]

    def find_mpv(explicit=None):
        for p in ([explicit] if explicit else []) + CANDIDATES:
            if p and Path(p).is_file():
                return p
        return None

    def mpv_version(mpv):
        try:
            out = subprocess.run([mpv, "--version"], capture_output=True, text=True,
                                 timeout=20, encoding="utf-8", errors="replace")
            return (out.stdout or "").splitlines()[0].strip()
        except (OSError, subprocess.SubprocessError):
            return ""

    def dump_bindings(mpv, timeout=40):
        """跑一次 mpv，把 input-bindings 导出成 JSON。"""
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "bindings.json"
            env = dict(os.environ, MPV_KEYS_OUT=str(out))
            cmd = [mpv, "--no-config", "--idle", "--vo=null", "--ao=null",
                   "--msg-level=all=no", f"--script={LUA}"]
            try:
                subprocess.run(cmd, env=env, timeout=timeout,
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
            except subprocess.TimeoutExpired:
                print("mpv 没有在超时前退出（脚本没跑起来？）")
            except OSError as e:
                print(f"起不了 mpv：{e}")
                return {}
            if not out.is_file():
                print("mpv 没写出绑定文件")
                return {}
            return json.loads(out.read_text(encoding="utf-8"))

    CMD_LINE = re.compile(r"^(?P<name>[a-z0-9\-]+)\s+(?P<sig>.*?)\s{2,}(?P<desc>.*)$")

    def parse_cmdlist(mpv):
        """解析 `mpv --input-cmdlist`：命令名 / 参数签名 / 说明。"""
        try:
            out = subprocess.run([mpv, "--input-cmdlist"], capture_output=True, text=True,
                                 timeout=30, encoding="utf-8", errors="replace")
        except (OSError, subprocess.SubprocessError) as e:
            print(f"拿命令表失败：{e}")
            return []
        cmds = []
        for line in (out.stdout or "").splitlines():
            if not line.strip():
                continue
            m = CMD_LINE.match(line.rstrip())
            if m:
                cmds.append({"name": m.group("name"), "sig": m.group("sig").strip(),
                             "desc": m.group("desc").strip()})
            else:
                parts = line.split()
                if parts:
                    cmds.append({"name": parts[0], "sig": " ".join(parts[1:]).strip(), "desc": ""})
        # 去掉表头（如果有）
        return [c for c in cmds if c["name"] not in ("name", "命令")]

    SECTION_LABEL = {
        "default": "mpv 内置",
        "osc": "内置脚本 osc",
        "window-controls": "内置脚本 window-controls",
        "input": "输入区",
        "encode": "编码模式",
        "showhide": "显示/隐藏",
        "showhide_wc": "显示/隐藏",
    }

    mpv = find_mpv(sys.argv[1] if len(sys.argv) > 1 else None)
    if not mpv:
        print("找不到 mpv（可以传一个路径：py -3 tools/build.py keybindings <mpv 路径>）")
        return 1
    print("用的 mpv：", mpv)
    version = mpv_version(mpv)
    print("版本：", version)

    raw = dump_bindings(mpv)
    bindings = []
    for b in raw.get("bindings") or []:
        key = (b.get("key") or "").strip()
        if not key:
            continue
        section = b.get("section") or "default"
        bindings.append({
            "key": key,
            "cmd": (b.get("cmd") or "").strip(),
            "comment": (b.get("comment") or "").strip(),
            "section": section,
            "label": SECTION_LABEL.get(section, section),
            "priority": b.get("priority", 0),
            "weak": bool(b.get("is_weak")),
            "owned": bool(b.get("owner")),
        })
    bindings.sort(key=lambda x: (x["section"] != "default", x["label"], x["key"]))

    cmds = parse_cmdlist(mpv)
    DATA.mkdir(exist_ok=True)
    (DATA / "mpv_keybindings.json").write_text(json.dumps({
        "meta": {
            "source": "mpv --no-config --idle --script=_dump_bindings.lua（读 input-bindings 属性）",
            "mpv": version,
            "count": len(bindings),
            "sections": sorted({b["section"] for b in bindings}),
        },
        "bindings": bindings,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    (DATA / "mpv_commands.json").write_text(json.dumps({
        "meta": {"source": "mpv --input-cmdlist", "mpv": version, "count": len(cmds)},
        "commands": cmds,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"内置绑定 {len(bindings)} 条 / 命令 {len(cmds)} 条")
    print(f"已写入 {DATA / 'mpv_keybindings.json'}")
    print(f"已写入 {DATA / 'mpv_commands.json'}")
    return 0


# --------------------------------------------------------------------------
# icon
# --------------------------------------------------------------------------
def cmd_icon():
    """生成应用图标 electron/assets/icon.ico（多尺寸，零依赖手写 PNG + ICO 封装）。

    ## 为什么要自己画

    electron-builder 不给图标就用 Electron 默认图标，一眼看过去像"没做完的 Demo"。
    但要为这个去装 Pillow 又违背本项目的零依赖习惯（构建期也不想加）。
    所以这里手写：标准库 `zlib` + `struct` 就能产出合法 PNG，而 ICO 允许直接内嵌 PNG。

    ## 画的是什么

    深色圆角底 + 蓝紫渐变 + 中间的播放三角 —— 和界面的配色一致
    （界面主色 `--accent: #6aa8ff`）。
    小尺寸（16/24）下细节会糊，所以三角按尺寸等比缩放，不做像素级微调 ——
    16px 下能认出是"播放"就够了。

    产物：
        electron/assets/icon.ico    （多尺寸，给 electron-builder / 窗口图标）
        electron/assets/icon.png    （256px，给 README / 商店页）

    ⚠ 目录叫 `assets/` 而不是 `build/`：`.gitignore` 里的 `build/` 是**任意层级**匹配，
    会把 `electron/build/` 一起忽略掉 —— 图标是源材料，必须入库。
    （同一个坑在 packaging/backend.spec 上也踩过一次。）
    """
    OUT_DIR = ROOT / "electron" / "assets"

    # 界面主色（style.css 的 --accent / --accent-2）
    ACCENT = (106, 168, 255)
    ACCENT2 = (150, 120, 255)
    BG_TOP = (26, 31, 43)
    BG_BOT = (16, 19, 25)

    # 各尺寸都做一份：Windows 会在不同场合挑不同尺寸（任务栏 32、桌面 48、Alt+Tab 48…）
    SIZES = [16, 24, 32, 48, 64, 128, 256]

    def _lerp(a, b, t):
        return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))

    def _rounded_alpha(x, y, n, radius_ratio=0.22):
        """圆角矩形的覆盖率（0..1）。用简单的距离场做 1px 抗锯齿。

        Windows 11 的图标习惯是圆角，直角会显得很旧。
        """
        r = n * radius_ratio
        cx = min(max(x + 0.5, r), n - r)
        cy = min(max(y + 0.5, r), n - r)
        d = ((x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2) ** 0.5
        if (x + 0.5) > r and (x + 0.5) < n - r:
            d = abs(y + 0.5 - cy)
        elif (y + 0.5) > r and (y + 0.5) < n - r:
            d = abs(x + 0.5 - cx)
        return max(0.0, min(1.0, r - d + 0.5))

    def _play_triangle(x, y, n):
        """播放三角的覆盖率（0..1）。等腰、朝右、居中略偏右（视觉重心）。"""
        left = 0.34 * n
        right = 0.72 * n
        top = 0.27 * n
        bottom = 0.73 * n
        mid_y = (top + bottom) / 2
        if x < left or x > right:
            return 0.0
        t = (x - left) / (right - left)
        half = (bottom - top) / 2 * (1 - t)
        dy = abs(y + 0.5 - mid_y)
        return max(0.0, min(1.0, half - dy + 0.5))

    def render(n):
        """渲染一张 n×n 的 RGBA 像素表。"""
        rows = []
        for y in range(n):
            row = bytearray()
            for x in range(n):
                a_rect = _rounded_alpha(x, y, n)
                if a_rect <= 0:
                    row += bytes((0, 0, 0, 0))
                    continue
                bg = _lerp(BG_TOP, BG_BOT, y / max(1, n - 1))
                tri = _play_triangle(x, y, n)
                if tri > 0:
                    col = _lerp(ACCENT, ACCENT2, (x / max(1, n - 1)))
                    r = round(bg[0] * (1 - tri) + col[0] * tri)
                    g = round(bg[1] * (1 - tri) + col[1] * tri)
                    b = round(bg[2] * (1 - tri) + col[2] * tri)
                else:
                    r, g, b = bg
                row += bytes((r, g, b, round(255 * a_rect)))
            rows.append(bytes(row))
        return rows

    def png_bytes(n, rows):
        """把像素表编成 PNG（8 位 RGBA，无交错）。"""
        raw = b"".join(b"\x00" + r for r in rows)

        def chunk(typ, data):
            return (struct.pack(">I", len(data)) + typ + data
                    + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF))

        ihdr = struct.pack(">IIBBBBB", n, n, 8, 6, 0, 0, 0)
        return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
                + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))

    def ico_bytes(entries):
        """把若干 (尺寸, PNG 字节) 封成 ICO。

        ICO 格式允许每个条目直接内嵌 PNG（Vista 之后都支持），所以不用写 BMP 那套。

            头部  6 字节：reserved(0) type(1=icon) count
            目录  每项 16 字节：宽 高 调色板 保留 平面 位深 数据长度 数据偏移
                  宽高为 0 表示 256（一个字节存不下 256）
        """
        count = len(entries)
        header = struct.pack("<HHH", 0, 1, count)
        offset = 6 + 16 * count
        dir_entries, blobs = b"", b""
        for size, data in entries:
            dim = 0 if size >= 256 else size
            dir_entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32,
                                       len(data), offset)
            blobs += data
            offset += len(data)
        return header + dir_entries + blobs

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    entries = []
    for n in SIZES:
        data = png_bytes(n, render(n))
        entries.append((n, data))
        print(f"  {n:>3}px  {len(data):>6} 字节")

    ico = ico_bytes(entries)
    (OUT_DIR / "icon.ico").write_bytes(ico)
    (OUT_DIR / "icon.png").write_bytes(png_bytes(256, render(256)))
    print(f"\n已写出 {OUT_DIR / 'icon.ico'}（{len(ico)} 字节，{len(SIZES)} 个尺寸）")
    print(f"已写出 {OUT_DIR / 'icon.png'}（256px）")
    return 0


# --------------------------------------------------------------------------
# ps1
# --------------------------------------------------------------------------
def cmd_ps1():
    """把 .ps1 统一成 Windows PowerShell 该有的样子：**UTF-8 带 BOM + CRLF**。

    ⚠ 为什么 .ps1 要**带** BOM（和 2026-10-09 的 .bat 结论正好相反）：
      · Windows PowerShell 5.1 读 UTF-8 **无 BOM** 的脚本时按系统代码页
        （936）解码，中文一律乱码；Pwsh 7 默认 UTF-8，两种都认。
        带 BOM 是唯一让 5.1 / 7 都正确的写法。
      · CRLF 仍然必须：LF 的 .ps1 在部分老宿主上行为不可靠，
        `.gitattributes` 只管行尾、不管 BOM，所以两头都得由这里兜住。
      · 2026-10-14 启动.bat 转成 启动.ps1 时立下这条约定（AGENTS.md §2.4）。

    模型工具（write / edit）写出的是 LF、无 BOM 的 UTF-8，
    所以**每次用工具改过 .ps1 之后都要跑一遍这个**。
    """
    BOM = b"\xef\xbb\xbf"

    def fix(p):
        raw = p.read_bytes()
        # utf-8-sig 剥掉已有 BOM，下面按「有且只有一个」重新写
        text = raw.decode("utf-8-sig").lstrip("\ufeff")
        body = (BOM + text.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8"))
        p.write_bytes(body)
        b = p.read_bytes()
        lf = b.count(b"\n") - b.count(b"\r\n")
        return b[:3] == BOM, b.count(b"\r\n"), lf

    targets = sorted(ROOT.glob("*.ps1")) + sorted(ROOT.glob("*/*.ps1"))
    bad = []
    for p in targets:
        bom, crlf, lf = fix(p)
        ok = bom and lf == 0                # ⚠ BOM 必须为**有**，见上面 docstring
        rel = p.relative_to(ROOT)
        print(f"  {'✅' if ok else '❌'} {rel}  BOM={bom} CRLF={crlf} 裸LF={lf}")
        if not ok:
            bad.append(str(rel))
    if bad:
        print(f"\n❌ 还有 {len(bad)} 个没弄好")
        return 1
    print(f"\n✅ {len(targets)} 个 .ps1 都是 带BOM + CRLF")
    return 0


# --------------------------------------------------------------------------
# version
# --------------------------------------------------------------------------
def cmd_version():
    """把版本号从**唯一来源**刷到需要它的地方。

    ## 为什么要有它

    版本号原来写在两个地方，得手改：

        core/schema.py            VERSION = "0.1.0"     ← 软件里显示的
        electron/package.json     "version": "0.1.0"    ← 打包时用的（安装包文件名）

    只改一处的话，会出现「安装包叫 0.2.0-Setup.exe，但软件里显示 0.1.0」——
    **两边都看起来正常**，特别难发现。

    现在：`core/schema.py` 是唯一来源，改完跑这个命令，剩下的地方自动跟上。
    `tests/test_version.py` 有一条测试钉住两边相等，忘了跑会红。

    ## 用法

        py -3 tools/build.py version           # 同步
        py -3 tools/build.py version --check   # 只检查，不改（CI / 测试用）

    ## 版本号规则（2026-09-14 定）

        小更新（改文案、修 bug）  0.1.0 → 0.1.1 → 0.1.2
        大更新（加功能）          0.1.x → 0.2.0 → 0.3.0
        觉得能正式推荐给别人了     0.x   → 1.0.0
    """
    from core.schema import VERSION                                    # noqa: E402

    PKG = ROOT / "electron" / "package.json"

    def read_pkg_version():
        """读 package.json 里的 version —— 用正则而不是 json.loads。

        为什么不用 json.loads 再 dump 回去：那会把整个文件的缩进、键序、
        以及 npm 自己写进去的字段全部重排一遍，diff 会变成几十行噪音。
        我们只改一个字段，就只动那一行。
        """
        text = PKG.read_text(encoding="utf-8")
        m = re.search(r'^(\s*)"version"\s*:\s*"([^"]*)"', text, re.M)
        if not m:
            return None, None, text
        return m.group(2), m, text

    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只检查，不写盘")
    args = ap.parse_args()

    if not PKG.is_file():
        print(f"❌ 找不到 {PKG}")
        return 1

    cur, m, text = read_pkg_version()
    if cur is None:
        print(f"❌ {PKG} 里没有 version 字段")
        return 1

    print(f"  唯一来源 core/schema.py : {VERSION}")
    print(f"  electron/package.json   : {cur}")

    if cur == VERSION:
        print("\n✅ 已经一致，不用改")
        return 0

    if args.check:
        print(f"\n❌ 不一致（差了 {cur} → {VERSION}）")
        print("   跑一下：py tools/build.py version")
        return 1

    new_text = text[:m.start(2)] + VERSION + text[m.end(2):]
    PKG.write_text(new_text, encoding="utf-8", newline="")
    print(f"\n✅ 已同步 package.json：{cur} → {VERSION}")

    # 复核：真的写进去了吗
    again, _, _ = read_pkg_version()
    if again != VERSION:
        print(f"❌ 写进去了但读出来是 {again}，有问题")
        return 1
    print("   复核通过")
    return 0


# --------------------------------------------------------------------------
# golden
# --------------------------------------------------------------------------
def cmd_golden():
    """生成 tests/data/conflicts_golden.json —— 冲突检测的「行为快照」。

    为什么要有这个文件
    ------------------
    2026-09 决定把 core/conflicts.py 里 154 行的 if 长链改写成规则表（C-1）。
    改写是纯重构，任何一条规则的 id / 级别 / 文案 / 涉及选项都不许变。
    但 detect_conflicts() 的返回值是给前端直接渲染的，字段多、分支密，
    光靠 tests/test_conflicts.py 那 32 个 assertIn/assertEqual 挡不住细微漂移
    （比如某条规则的 detail 少了一个字、或者两条规则的输出顺序换了）。

    所以先用**当前实现**跑一遍固定用例，把逐字段的完整结果存成 JSON 当基准；
    重构之后 tests/test_conflicts_snapshot.py 会把结果和这份 JSON 逐字节比对。
    基准必须由重构前的代码生成 —— 用重构后的代码生成基准等于自己给自己判卷。

    用法
    ----
        py -3 tools/build.py golden           # 生成/覆盖基准
        py -3 tools/build.py golden --check   # 只比对，不写盘

    注意：这个命令会 import core.conflicts，所以重构前后跑出来的东西必须完全一样。
    """
    from core.conflicts import conflict_keys, conflicts_as_issues, detect_conflicts  # noqa: E402

    OUT = ROOT / "tests" / "data" / "conflicts_golden.json"

    # 固定用例表。设计原则：
    #   1. 17 条规则每条至少有一个用例能触发它（由下面的校验 + 测试共同保证）；
    #   2. 每条规则的「不该触发」的反面也尽量覆盖，防止重构时条件写反；
    #   3. 故意留几个多规则同时命中的用例，用来锁住 level 排序和并列时的 id 排序；
    #   4. 边界值（deband-iterations = 4 / 3 / range = 16 / 32）单独列，防止
    #      重构时把 >= 写成 >、把 and 写成 or。
    CASES = [
        {"name": "clean_default",
         "values": {"vo": "gpu-next", "scale": "spline36", "deband": "yes",
                    "deband-iterations": "2", "cache": "yes"}},
        {"name": "clean_empty", "values": {}},
        {"name": "sigmoid_and_linear",
         "values": {"sigmoid-upscaling": "yes", "linear-upscaling": "yes"}},
        {"name": "linear_alone", "values": {"linear-upscaling": "yes"}},
        {"name": "sigmoid_alone_ok", "values": {"sigmoid-upscaling": "yes"}},
        {"name": "linear_no_is_ok", "values": {"linear-upscaling": "no"}},
        {"name": "interp_without_display_sync",
         "values": {"interpolation": "yes", "video-sync": "audio", "tscale": "mitchell"}},
        {"name": "interp_no_video_sync_at_all",
         "values": {"interpolation": "yes", "tscale": "mitchell"}},
        {"name": "interp_display_sync_but_no_tscale",
         "values": {"interpolation": "yes", "video-sync": "display-resample"}},
        {"name": "interp_display_sync_with_tscale_ok",
         "values": {"interpolation": "yes", "video-sync": "display-resample",
                    "tscale": "mitchell"}},
        {"name": "interp_with_memc_script",
         "values": {"interpolation": "yes", "video-sync": "display-resample",
                    "tscale": "mitchell"},
         "memc": "~~/vs/MEMC_RIFE_NV.vpy"},
        {"name": "deband_off_ignores_iterations",
         "values": {"deband": "no", "deband-iterations": "0"}},
        {"name": "deband_without_iterations_ok", "values": {"deband": "yes"}},
        {"name": "deband_zero_iterations",
         "values": {"deband": "yes", "deband-iterations": "0"}},
        {"name": "deband_iterations_at_4_ok",
         "values": {"deband": "yes", "deband-iterations": "4", "deband-range": "16"}},
        {"name": "deband_iterations_above_4",
         "values": {"deband": "yes", "deband-iterations": "6"}},
        {"name": "deband_range_boundary_31_no",
         "values": {"deband": "yes", "deband-iterations": "4", "deband-range": "31"}},
        {"name": "deband_range_boundary_32_yes",
         "values": {"deband": "yes", "deband-iterations": "4", "deband-range": "32"}},
        {"name": "deband_range_high_but_iterations_low_ok",
         "values": {"deband": "yes", "deband-iterations": "2", "deband-range": "48"}},
        {"name": "deband_high_iterations_and_range",
         "values": {"deband": "yes", "deband-iterations": "5", "deband-range": "40"}},
        {"name": "deband_iterations_not_a_number",
         "values": {"deband": "yes", "deband-iterations": "abc"}},
        {"name": "icc_profile_with_target",
         "values": {"icc-profile": "C:/icc/srgb.icc", "target-prim": "bt.709"}},
        {"name": "icc_profile_with_two_targets",
         "values": {"icc-profile": "C:/icc/srgb.icc", "target-trc": "srgb",
                    "target-gamut": "bt.709"}},
        {"name": "icc_auto_without_profile_ok", "values": {"icc-profile-auto": "yes"}},
        {"name": "icc_auto_and_profile_and_target",
         "values": {"icc-profile-auto": "yes", "icc-profile": "C:/icc/srgb.icc",
                    "target-prim": "bt.709"}},
        {"name": "hable_without_peak", "values": {"tone-mapping": "hable"}},
        {"name": "hable_with_peak_ok",
         "values": {"tone-mapping": "hable", "hdr-compute-peak": "yes"}},
        {"name": "hable_uppercase_still_detected", "values": {"tone-mapping": "Hable"}},
        {"name": "spline_tone_mapping_ok", "values": {"tone-mapping": "spline"}},
        {"name": "gpu_with_gpunext_only_option",
         "values": {"vo": "gpu", "gamut-mapping-mode": "clip"}},
        {"name": "gpu_with_many_gpunext_only_options",
         "values": {"vo": "gpu", "gamut-mapping-mode": "clip", "target-gamut": "bt.709",
                    "lut": "C:/lut.cube", "image-lut": "C:/img.cube",
                    "icc-use-luma": "yes", "sdr-adjust-gamma": "yes",
                    "hdr-reference-white": "203", "treat-srgb-as-power22": "yes"}},
        {"name": "gpu_alone_ok", "values": {"vo": "gpu", "scale": "spline36"}},
        {"name": "gpunext_with_gpu_only_option",
         "values": {"vo": "gpu-next", "corner-rounding": "10"}},
        {"name": "gpunext_with_three_gpu_only_options",
         "values": {"vo": "gpu-next", "corner-rounding": "10", "sharpen": "0.5",
                    "tone-mapping-max-boost": "2"}},
        {"name": "gpunext_with_all_gpu_only_options",
         "values": {"vo": "gpu-next", "corner-rounding": "10", "sharpen": "0.5",
                    "tone-mapping-max-boost": "2", "gamut-mapping-mode": "clip"}},
        {"name": "vo_uppercase_is_normalised",
         "values": {"vo": "GPU", "gamut-mapping-mode": "clip"}},
        {"name": "single_shader_family_ok",
         "values": {}, "shaders": ["~~/shaders/FSRCNNX_x2_8-0-4-1.glsl"]},
        {"name": "two_shader_families",
         "values": {},
         "shaders": ["~~/shaders/FSRCNNX_x2_8-0-4-1.glsl",
                     "~~/shaders/Anime4K_Upscale_CNN_x2_M.glsl"]},
        {"name": "two_families_same_family_twice_ok",
         "values": {},
         "shaders": ["~~/shaders/FSRCNNX_x2_8-0-4-1.glsl",
                     "~~/shaders/FSRCNNX_x2_16-0-4-1.glsl"]},
        {"name": "empty_shader_entries_ignored",
         "values": {}, "shaders": ["", "   "]},
        {"name": "vpy_superres_with_shader_superres",
         "values": {}, "shaders": ["~~/shaders/FSRCNNX_x2_8-0-4-1.glsl"],
         "memc": "~~/vs/SR_ESRGAN_x2.vpy"},
        {"name": "vpy_superres_without_shader_ok",
         "values": {}, "memc": "~~/vs/SR_ESRGAN_x2.vpy"},
        {"name": "vpy_superres_with_only_sharpen_shader_ok",
         "values": {}, "shaders": ["~~/shaders/AMD_CAS.glsl"],
         "memc": "~~/vs/SR_ESRGAN_x2.vpy"},
        {"name": "vpy_mix_uai_counts_as_superres",
         "values": {}, "shaders": ["~~/shaders/RAVU_Zoom_R3.glsl"],
         "memc": "~~/vs/MIX_UAI_ESRGAN.vpy"},
        {"name": "memc_prefix_is_not_superres",
         "values": {}, "shaders": ["~~/shaders/RAVU_Zoom_R3.glsl"],
         "memc": "~~/vs/MEMC_RIFE_NV.vpy"},
        {"name": "sharpen_not_last",
         "values": {},
         "shaders": ["~~/shaders/AMD_CAS.glsl",
                     "~~/shaders/FSRCNNX_x2_8-0-4-1.glsl"]},
        {"name": "sharpen_at_last_ok",
         "values": {},
         "shaders": ["~~/shaders/FSRCNNX_x2_8-0-4-1.glsl",
                     "~~/shaders/AMD_CAS.glsl"]},
        {"name": "sharpen_only_one_shader_ok",
         "values": {}, "shaders": ["~~/shaders/AMD_CAS.glsl"]},
        {"name": "sharpen_substring_false_positive_guarded",
         "values": {},
         # 文件名里有 cascade，不该被当成锐化（历史上裸 "cas" 子串匹配踩过这个坑）
         "shaders": ["~~/shaders/Cascade_Sharpen.glsl",
                     "~~/shaders/FSRCNNX_x2_8-0-4-1.glsl"]},
        {"name": "cache_off_with_demuxer_buffer",
         "values": {"cache": "no", "demuxer-max-bytes": "512MiB"}},
        {"name": "cache_missing_with_demuxer_buffer",
         "values": {"demuxer-max-bytes": "512MiB"}},
        {"name": "cache_on_with_demuxer_buffer_ok",
         "values": {"cache": "yes", "demuxer-max-bytes": "512MiB"}},
        {"name": "cache_off_without_demuxer_buffer_ok", "values": {"cache": "no"}},
        {"name": "many_rules_sorted",
         "values": {
             "vo": "gpu",
             "sigmoid-upscaling": "yes", "linear-upscaling": "yes",
             "interpolation": "yes", "video-sync": "audio",
             "deband": "yes", "deband-iterations": "0",
             "icc-profile-auto": "yes", "icc-profile": "C:/icc/srgb.icc",
             "target-prim": "bt.709", "tone-mapping": "hable",
             "gamut-mapping-mode": "clip", "cache": "no",
             "demuxer-max-bytes": "512MiB"},
         "shaders": ["~~/shaders/AMD_CAS.glsl",
                     "~~/shaders/FSRCNNX_x2_8-0-4-1.glsl",
                     "~~/shaders/Anime4K_Upscale_CNN_x2_M.glsl"],
         "memc": "~~/vs/MEMC_RIFE_NV.vpy"},
        {"name": "error_outranks_warn",
         "values": {"interpolation": "yes", "sigmoid-upscaling": "yes",
                    "linear-upscaling": "yes", "video-sync": "audio"}},
    ]

    def run_case(case):
        conflicts = detect_conflicts(case["values"], shaders=case.get("shaders"),
                                     memc=case.get("memc", ""))
        return {
            # 入参也要存进基准：快照必须自带输入，否则测试没法「原样重放」
            "values": case["values"],
            "shaders": case.get("shaders", []),
            "memc": case.get("memc", ""),
            # 输出：三个对外函数的结果全存
            "conflicts": conflicts,
            "issues": [list(x) for x in conflicts_as_issues(conflicts)],
            "keys": sorted(conflict_keys(conflicts)),
        }

    def build():
        return {
            "note": "mpv 配置冲突检测的行为快照（C-1 重构基准）。"
                    "由 tools/build.py golden 生成，禁止手工编辑。",
            "count": len(CASES),
            "cases": [dict({"name": c["name"]}, **run_case(c)) for c in CASES],
        }

    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只比对，不写盘")
    args = ap.parse_args()

    data = build()
    text = json.dumps(data, ensure_ascii=False, indent=1, sort_keys=False) + "\n"

    if args.check:
        if not OUT.is_file():
            print(f"[缺失] {OUT}")
            return 1
        cur = OUT.read_text(encoding="utf-8")
        if cur == text:
            print(f"[一致] {len(data['cases'])} 个用例与基准完全相同")
            return 0
        print(f"[不一致] {OUT} 与当前实现不符 —— 重构改动了行为，请逐条核对")
        return 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8", newline="\n")
    n_ok = sum(1 for c in data["cases"] if c["conflicts"])
    print(f"[写入] {OUT}  ({len(text.encode('utf-8'))} 字节)")
    print(f"       {len(data['cases'])} 个用例，其中 {n_ok} 个命中至少一条规则")
    return 0


COMMANDS = {
    "options-db": cmd_options_db,
    "keybindings": cmd_keybindings,
    "icon": cmd_icon,
    "ps1": cmd_ps1,
    "version": cmd_version,
    "golden": cmd_golden,
}


def main(argv=None):
    if argv is None:
        argv = sys.argv
    if len(argv) < 2 or argv[1] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    name = argv[1]
    if name not in COMMANDS:
        print(f"❌ 未知子命令：{name}\n")
        print(__doc__)
        return 2
    # 把剩余参数交还给子命令：有的子命令自己再 parse（version/golden 的 --check），
    # 有的直接读 sys.argv[1]（keybindings 的 mpv 路径）。统一走 sys.argv，无需改子命令。
    sys.argv = [argv[0], *argv[2:]]
    return COMMANDS[name]()


if __name__ == "__main__":
    raise SystemExit(main())
