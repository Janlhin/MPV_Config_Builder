# -*- coding: utf-8 -*-
"""下载中心（R-8x · L1）：mpv 脚本与字幕字体的一键下载 / 安装 / 卸载。

**范围（L1）**：只做「单文件、放进明确目录」的东西 ——
  · mpv 脚本（`.lua` / `.js`）→ `<配置目录>/scripts/`
  · 字幕字体（`.ttf` / `.otf` / `.ttc`）→ `<配置目录>/fonts/`

**不在 L1 范围**（L2/L3 再说）：
  · archive 型（zip 里挑文件）——虽然 `installer.extract_archive` 已经能解压
  · VapourSynth 插件（`.dll`）——那要写到 mpv 配置目录**之外**，见路线图 §5.5

**三条设计原则**（和安全写配置一个道理）：
  1. **只从各项目官方地址下载**，不随程序分发任何第三方文件；
  2. **装过什么记在清单里**（`%LOCALAPPDATA%\\MPVConfigBuilder\\installed.json`）——
     没有清单就没有"已安装 / 可卸载"，用户过半年自己也忘了装过什么；
  3. **覆盖前必须备份**，卸载只删清单里记着的、且哈希对得上的文件
     （用户自己改过的文件不删，宁可报错让用户手动处理）。

清单里的 `sha256` 允许为空 —— 我们无法凭空知道上游文件的哈希。
为空时标成"未校验"，并且**把实际下载到的文件的哈希记进 manifest**，
这样至少能回答"我装完之后这个文件有没有被改过"。
"""
import json
import os
import shutil
from datetime import datetime
from pathlib import Path

from . import textio
from .installer import download_file, verify_sha256
from .net import build_url_candidates

MANIFEST_NAME = "installed.json"

# 适用分类：界面按这个分组
KINDS = [
    ("script", "mpv 脚本", "scripts"),
    ("font", "字幕字体", "fonts"),
]


def manifest_path():
    """安装清单放哪：`<user_data_dir()>/installed.json`。

    即 `%LOCALAPPDATA%\\MPVConfigBuilder\\installed.json` —— 属于用户数据，
    **不放 exe 旁边**（装到 `Program Files` 之后那里只读）。
    W-2 之后统一走 `core.paths.user_data_dir()`，不再自己拼那串路径。
    """
    from .paths import user_data_dir
    return Path(user_data_dir()) / MANIFEST_NAME


# ---------------------------------------------------------------- 清单（内置）

# 注意：`url` 一律指向各项目的官方发布地址，且**每条都必须先用 check_links() 验过**。
# `sha256` 留空表示"不知道上游哈希"，界面会显示成未校验（不假装校验过）。
#
# ⚠ 关于 uosc：它现在只以 `uosc.zip` 的形式发布（仓库里没有单文件 dist），
#   属于 archive 型 = L2 的活。**故意不放进 L1 清单** —— 与其放一条必然 404 的
#   条目，不如等 L2 把「zip 里挑文件」做出来再收。用户现在可以从 mpv-lazy 拿。
CATALOG = [
    # ---------- mpv 脚本（全部为单文件 .lua，已逐条验证可下载） ----------
    {
        "id": "autoload",
        "name": "autoload",
        "kind": "script",
        "dest": "scripts/autoload.lua",
        "url": "https://raw.githubusercontent.com/mpv-player/mpv/master/TOOLS/lua/autoload.lua",
        "home": "https://github.com/mpv-player/mpv/blob/master/TOOLS/lua/autoload.lua",
        "author": "mpv 官方（TOOLS/lua）",
        "license": "mpv 项目许可（LGPL-2.1+ / 见项目）",
        "note": "自动把同目录的其它视频/音频加进播放列表。看番看剧最实用的一条。",
        "sha256": "",
    },
    {
        "id": "autodeint",
        "name": "autodeint",
        "kind": "script",
        "dest": "scripts/autodeint.lua",
        "url": "https://raw.githubusercontent.com/mpv-player/mpv/master/TOOLS/lua/autodeint.lua",
        "home": "https://github.com/mpv-player/mpv/blob/master/TOOLS/lua/autodeint.lua",
        "author": "mpv 官方（TOOLS/lua）",
        "license": "mpv 项目许可",
        "note": "识别到隔行源时自动加反交错，避免老片出现横纹。",
        "sha256": "",
    },
    {
        "id": "pause-when-minimize",
        "name": "pause-when-minimize",
        "kind": "script",
        "dest": "scripts/pause-when-minimize.lua",
        "url": ("https://raw.githubusercontent.com/mpv-player/mpv/master/"
                "TOOLS/lua/pause-when-minimize.lua"),
        "home": "https://github.com/mpv-player/mpv/blob/master/TOOLS/lua/pause-when-minimize.lua",
        "author": "mpv 官方（TOOLS/lua）",
        "license": "mpv 项目许可",
        "note": "最小化窗口时自动暂停，切出去干别的不浪费性能。",
        "sha256": "",
    },
    {
        "id": "cycle-deinterlace-pullup",
        "name": "cycle-deinterlace-pullup",
        "kind": "script",
        "dest": "scripts/cycle-deinterlace-pullup.lua",
        "url": ("https://raw.githubusercontent.com/mpv-player/mpv/master/"
                "TOOLS/lua/cycle-deinterlace-pullup.lua"),
        "home": ("https://github.com/mpv-player/mpv/blob/master/"
                 "TOOLS/lua/cycle-deinterlace-pullup.lua"),
        "author": "mpv 官方（TOOLS/lua）",
        "license": "mpv 项目许可",
        "note": "绑定到快捷键，循环切换反交错 / 还原逐行模式。",
        "sha256": "",
    },
    {
        "id": "autocrop",
        "name": "autocrop",
        "kind": "script",
        "dest": "scripts/autocrop.lua",
        "url": "https://raw.githubusercontent.com/mpv-player/mpv/master/TOOLS/lua/autocrop.lua",
        "home": "https://github.com/mpv-player/mpv/blob/master/TOOLS/lua/autocrop.lua",
        "author": "mpv 官方（TOOLS/lua）",
        "license": "mpv 项目许可",
        "note": "自动裁掉片源自带的黑边（默认按快捷键触发）。",
        "sha256": "",
    },
    {
        "id": "skip-logo",
        "name": "skip-logo",
        "kind": "script",
        "dest": "scripts/skip-logo.lua",
        "url": "https://raw.githubusercontent.com/mpv-player/mpv/master/TOOLS/lua/skip-logo.lua",
        "home": "https://github.com/mpv-player/mpv/blob/master/TOOLS/lua/skip-logo.lua",
        "author": "mpv 官方（TOOLS/lua）",
        "license": "mpv 项目许可",
        "note": "跳过片头静音/纯色片段（需要自己设定检测时长）。",
        "sha256": "",
    },
    {
        "id": "thumbfast",
        "name": "thumbfast",
        "kind": "script",
        "dest": "scripts/thumbfast.lua",
        "url": "https://raw.githubusercontent.com/po5/thumbfast/master/thumbfast.lua",
        "home": "https://github.com/po5/thumbfast",
        "author": "po5",
        "license": "MIT",
        "note": "进度条悬停缩略图预览。需要 uosc（或 osc）配合；单独放进去不会有反应。",
        "sha256": "",
        "needs": "uosc 或内置 osc",
    },
    # ---------- archive 型（L2：zip 里挑文件） ----------
    # uosc 就是当初决定"等 L2 再收"的那一条：它**只以 uosc.zip 发布**，
    # 仓库里没有单文件 dist。zip 解开就是 `fonts/` + `scripts/uosc/`，
    # 正好按 mpv 配置目录的结构摆好，所以这类的 `dest` 是空（= 直接铺在配置目录下）。
    {
        "id": "uosc",
        "name": "uosc",
        "kind": "script",
        "archive": True,
        "dest": "",
        "url": "https://github.com/tomasklaen/uosc/releases/latest/download/uosc.zip",
        "home": "https://github.com/tomasklaen/uosc",
        "author": "tomasklaen",
        "license": "MIT（含 ziggy 的许可见其仓库）",
        "note": "现在最流行的 mpv 界面（顶栏 + 底部控件 + 菜单）。"
                "18 MB 的包里 **11 MB 是 Linux/macOS 的二进制**，这里只装 Windows 那份。",
        # 只装这两棵；`skip` 优先于 keep
        "keep": ["fonts/*", "scripts/uosc/*"],
        "skip": ["scripts/uosc/bin/ziggy-darwin", "scripts/uosc/bin/ziggy-linux"],
        # ⚠ ziggy-windows.exe 是 uosc 自己要调的外部程序（缩略图/缩略图缓存）。
        # 默认规则会把 .exe 拒掉，这里显式放行 —— 是**明知故放**，不是漏了。
        "allow_ext": [".exe"],
        "sha256": "",
        "note_extra": "会写入 fonts/ 与 scripts/uosc/ 一整棵目录树；卸载时逐个文件校验后删。",
    },
    # ---------- 字幕字体 ----------
    {
        "id": "lxgw-wenkai-lite",
        "name": "LXGW WenKai Lite（霞鹜文楷 Lite）",
        "kind": "font",
        "dest": "fonts/LXGWWenKaiLite-Regular.ttf",
        "url": ("https://raw.githubusercontent.com/lxgw/LxgwWenKai-Lite/"
                "main/fonts/TTF/LXGWWenKaiLite-Regular.ttf"),
        "home": "https://github.com/lxgw/LxgwWenKai-Lite",
        "author": "lxgw",
        "license": "SIL OFL 1.1",
        "note": "中文正文字体，字幕缺字（豆腐块）时最常用。装完在 mpv.conf 里写 sub-font 才会用上。",
        "sha256": "",
        "suggest": {"sub-font": "LXGW WenKai Lite"},
    },
]


def by_id(item_id):
    for item in CATALOG:
        if item["id"] == item_id:
            return item
    return None


def catalog_for(kind=""):
    if not kind or kind in ("all", "全部"):
        return list(CATALOG)
    return [x for x in CATALOG if x["kind"] == kind]


# ---------------------------------------------------------------- archive 型（L2）
#
# L1 只装**单文件**（一个 .lua、一个 .ttf）。但社区里不少东西只以 zip 发布
# —— uosc 就是典型：仓库里没有单文件 dist，只有 `uosc.zip`，解压出来是
# `fonts/` + `scripts/uosc/` 一整棵。所以 L2 要会「从压缩包里挑文件」。
#
# 这一段的规矩，全部围绕「别让压缩包里的东西跑到它该在的地方之外」：

# 单条目最多解出多少个文件 / 总共多少字节
ARCHIVE_MAX_FILES = 3000
ARCHIVE_MAX_BYTES = 512 * 1024 * 1024
# 这些扩展名**默认不装**：压缩包里塞个 exe 是最经典的坑。
# （uosc 的 `ziggy-windows.exe` 是它自己要用的，靠条目的 `allow_ext` 显式放行。）
ARCHIVE_DENY_EXT = (".exe", ".dll", ".bat", ".cmd", ".ps1", ".vbs", ".scr",
                    ".msi", ".com", ".cpl", ".jar", ".lnk", ".reg", ".sh")


def _fnmatch_any(rel, patterns):
    import fnmatch
    return any(fnmatch.fnmatch(rel, p) for p in patterns)


def archive_members(names, item):
    """从压缩包的成员名里挑出要装的、以及明确跳过的。

    `item` 可带三个字段（都可选）：
      · `keep`  —— 白名单，只装匹配的（空 = 全都算）
      · `skip`  —— 黑名单，明确不装（优先于 keep）
      · `strip` —— 去掉开头的第几层目录（`uosc-x/scripts/...` → `scripts/...`）
      · `allow_ext` —— 额外允许的高危扩展名（要逐条写清楚理由）

    返回 (要装的 [(原名, 相对目标路径)], 跳过的 [(原名, 原因)])。
    """
    keep = list(item.get("keep") or [])
    skip = list(item.get("skip") or [])
    allow_ext = tuple(x.lower() for x in (item.get("allow_ext") or []))
    strip = int(item.get("strip") or 0)

    take, dropped = [], []
    for raw in names:
        name = str(raw).replace("\\", "/")
        if name.endswith("/") or not name.strip():
            continue                              # 目录项
        rel = name
        if strip:
            parts = name.split("/")
            if len(parts) <= strip:
                dropped.append((name, "去掉目录层级后就没有了"))
                continue
            rel = "/".join(parts[strip:])
        if rel.startswith("/") or ".." in rel.split("/"):
            dropped.append((name, "路径越界"))
            continue
        if keep and not _fnmatch_any(rel, keep):
            dropped.append((name, "不在白名单里"))
            continue
        if skip and _fnmatch_any(rel, skip):
            dropped.append((name, "在跳过名单里"))
            continue
        low = rel.lower()
        if low.endswith(ARCHIVE_DENY_EXT) and not low.endswith(allow_ext):
            dropped.append((name, f"可执行文件（{low.rsplit('.', 1)[-1]}）默认不装"))
            continue
        take.append((name, rel))
    return take, dropped


def install_archive(target, item, mirror_mode="自动（直连 → 镜像）",
                    overwrite=False, progress_cb=None, timeout=60):
    """装一个 archive 型条目：下载 → 校验 → **按白名单解压** → 逐个就位。

    安全要点（每一条都对应一种真实的坑）：
      · 先解到**暂存目录**，检查通过才搬进目标 —— 不在目标目录里直接解压；
      · 成员路径逐个查（`..`、绝对路径），zip slip 直接拒；
      · 默认拒绝可执行文件，要装得在条目里用 `allow_ext` 显式放行；
      · 文件数与总字节数设上限，防"压缩炸弹"；
      · 就位前**先备份**同名旧文件；
      · 每次落盘都记 sha256，卸载时用它判断"用户改过没有"。
    """
    import tempfile
    import zipfile

    target = Path(target)
    url = item["url"]
    dest_rel = item.get("dest") or ""
    take, dropped = ([], [])
    installed = []
    stage = Path(tempfile.mkdtemp(prefix="mpvcb-arc-"))
    zip_path = stage / (item.get("file") or (item["id"] + ".zip"))
    try:
        used = ""
        last_err = None
        for prefix in build_url_candidates(url, mirror_mode):
            full = (prefix + url) if prefix else url
            label = "直连" if not prefix else prefix.rstrip("/").replace("https://", "")
            try:
                download_file(full, zip_path, progress_cb=progress_cb, timeout=timeout)
                used = label
                break
            except Exception as e:                     # noqa: BLE001
                last_err = e
        else:
            return {"ok": False, "detail": f"所有线路都失败（最后：{last_err}）"}

        if not zip_path.is_file() or zip_path.stat().st_size == 0:
            return {"ok": False, "detail": "下载到的压缩包是空的"}

        expected = (item.get("sha256") or "").strip()
        verified = False
        actual = ""
        if expected:
            passed, actual = verify_sha256(zip_path, expected)
            if not passed:
                return {"ok": False,
                        "detail": f"sha256 校验失败：期望 {expected[:12]}…，"
                                  f"实际 {actual[:12]}…"}
            verified = True
        else:
            actual = _file_sha(zip_path)

        try:
            zf = zipfile.ZipFile(zip_path)
        except Exception as e:                         # noqa: BLE001
            return {"ok": False, "detail": f"这不是一个能读的 zip：{e}"}

        with zf:
            names = zf.namelist()
            take, dropped = archive_members(names, item)
            if not take:
                return {"ok": False,
                        "detail": "压缩包里没有符合白名单的文件 —— "
                                  "上游可能改了目录结构，去它的 release 页看看"}
            if len(take) > ARCHIVE_MAX_FILES:
                return {"ok": False,
                        "detail": f"压缩包里有 {len(take)} 个文件，超过上限 "
                                  f"{ARCHIVE_MAX_FILES}，拒绝解压"}
            total = sum(zf.getinfo(n).file_size for n, _rel in take)
            if total > ARCHIVE_MAX_BYTES:
                return {"ok": False,
                        "detail": f"解压后约 {total // (1 << 20)} MB，超过上限 "
                                  f"{ARCHIVE_MAX_BYTES // (1 << 20)} MB，拒绝解压"}
            for i, (name, rel) in enumerate(take, 1):
                out = stage / "x" / rel
                out.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(name) as src, open(out, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                if progress_cb and (i % 10 == 0 or i == len(take)):
                    progress_cb(i, len(take))

        # ---- 就位：逐个搬，先备份同名旧文件 ----
        base = target / dest_rel if dest_rel else target
        # ⚠ 先探一遍"有没有会覆盖的"，除非用户勾了覆盖，否则整批不动 ——
        # 装一半再停下来会留下一个半新半旧的状态，比不装还糟。
        if not overwrite:
            clash = [rel for _n, rel in take if (base / rel).exists()]
            if clash:
                return {"ok": False, "skipped": True,
                        "detail": f"目标里已经有 {len(clash)} 个同名文件"
                                  f"（例如 {clash[0]}），整批都没动 —— "
                                  "想换新版请勾选覆盖",
                        "clash": clash[:10]}
        backups = []
        for _name, rel in take:
            src = stage / "x" / rel
            dst = base / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.is_file():
                b = textio.backup(dst)
                if b:
                    backups.append(str(b))
            shutil.move(str(src), str(dst))
            installed.append({"rel": rel, "sha256": _file_sha(dst)})

        detail = (f"已安装 {item['name']}：{len(installed)} 个文件 → "
                  f"{dest_rel or '.'}（线路：{used}）")
        if dropped:
            detail += f"；按规则跳过 {len(dropped)} 个"
        if backups:
            detail += f"；覆盖了 {len(backups)} 个旧文件（已备份）"
        if not verified:
            detail += "；上游未提供 sha256，本次未做完整性校验"
        return {"ok": True, "detail": detail, "target": str(target),
                "dest": dest_rel, "files": installed,
                "skipped_members": [{"name": n, "why": w} for n, w in dropped[:40]],
                "skipped_count": len(dropped),
                "sha256": actual, "verified": verified, "backups": backups}
    finally:
        shutil.rmtree(stage, ignore_errors=True)


# ---------------------------------------------------------------- 安装清单

def load_manifest():
    p = manifest_path()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"version": 1, "items": {}}
    if not isinstance(data.get("items"), dict):
        data["items"] = {}
    return data


def save_manifest(data):
    p = manifest_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except OSError:
        return False


def record_install(item, dest, actual_sha="", verified=False, files=None):
    """把一次成功安装记进清单。

    `files` 是 archive 型安装的文件清单（每项 {rel, sha256}），单文件条目传 None。
    ⚠ `dest` 对 archive 型来说是**目录**（相对目标的），不要再写进 `path`
    —— 卸载时按 `installed_files` 走，否则会把目录当成文件去 unlink。
    """
    data = load_manifest()
    rec = {
        "id": item["id"], "name": item["name"], "kind": item["kind"],
        "url": item.get("url", ""),
        "catalog_sha256": item.get("sha256", ""),
        "install_kind": "archive" if files else "file",
        "installed_sha256": actual_sha,
        "verified": bool(verified),
        "installed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    if files:
        rec["dest"] = str(dest)
        rec["installed_files"] = list(files)
    else:
        rec["dest"] = str(dest)
        rec["path"] = str(dest)
    data["items"][item["id"]] = rec
    return save_manifest(data)


def forget_install(item_id):
    data = load_manifest()
    if item_id in data["items"]:
        data["items"].pop(item_id)
        return save_manifest(data)
    return True


def installed_map():
    return load_manifest().get("items") or {}


# ---------------------------------------------------------------- 查询状态

def _file_sha(path):
    passed, actual = verify_sha256(path, "")   # 空 digest → 只算哈希，不判通过
    return actual if actual else ""


def list_items(target, kind=""):
    """列出清单里的条目 + 它们在目标目录里的实际情况。

    每条返回的 `state` 取值：
        not_installed  没装
        installed      装了，且内容与安装时一致
        modified       装了，但文件被改过（用户自己编辑过？）
        missing        清单里记着装过，但文件没了
        broken         目标目录不可用
    """
    target = Path(target) if target else None
    installed = installed_map()
    out = []
    ok_dir = bool(target and target.is_dir())
    for item in catalog_for(kind):
        rec = installed.get(item["id"])
        dest = (Path(target) / item["dest"]) if target else None
        entry = dict(item)
        entry["dest_rel"] = item["dest"]
        entry["dest"] = str(dest) if dest else ""
        entry["installed"] = False
        entry["state"] = "broken" if not ok_dir else "not_installed"
        entry["installed_at"] = ""
        entry["verified"] = False
        entry["version_note"] = ""
        if not ok_dir:
            out.append(entry)
            continue

        # ---- archive 型：状态看的是"清单里记的那批文件还在不在、改没改" ----
        if item.get("archive"):
            files = (rec or {}).get("installed_files") or []
            base = (target / item["dest"]) if target else None
            if rec and files:
                entry["installed_at"] = rec.get("installed_at", "")
                entry["verified"] = bool(rec.get("verified"))
                entry["file_count"] = len(files)
                gone = [f["rel"] for f in files if not (base / f["rel"]).is_file()]
                changed = [f["rel"] for f in files
                           if (base / f["rel"]).is_file()
                           and f.get("sha256") and _file_sha(base / f["rel"]) != f["sha256"]]
                entry["files_missing"] = len(gone)
                entry["files_changed"] = len(changed)
                if gone and len(gone) == len(files):
                    entry["state"] = "missing"
                elif gone:
                    entry["state"] = "modified"      # 缺了一部分也算被改过
                elif changed:
                    entry["state"] = "modified"
                else:
                    entry["state"] = "installed"
                    entry["installed"] = True
            else:
                # 没记录时，判断"是不是已经有别人装的一棵"。
                # ⚠ uosc 这类 `dest=""`（铺在配置目录根）的条目**不能只看目录在不在** ——
                # 那个"目录"就是配置目录本身，永远存在，于是新装的配置也会被报成
                # "已存在（可能是自带的）"（实测踩过）。要看 `keep` 指向的文件在不在。
                hit = None
                for pat in (item.get("keep") or []):
                    if base and list(base.glob(pat)):
                        hit = pat
                        break
                if hit:
                    entry["state"] = "present_untracked"
                    entry["version_note"] = "目录已存在（可能是自带的），没有安装记录"
            out.append(entry)
            continue

        exists = bool(dest and dest.is_file())
        if rec:
            entry["installed_at"] = rec.get("installed_at", "")
            entry["verified"] = bool(rec.get("verified"))
            if not exists:
                entry["state"] = "missing"
            else:
                now = _file_sha(dest)
                entry["installed"] = True
                entry["current_sha256"] = now
                if rec.get("installed_sha256") and now != rec["installed_sha256"]:
                    entry["state"] = "modified"
                else:
                    entry["state"] = "installed"
        elif exists:
            # 文件在、但清单里没有：可能是 mpv-lazy 自带的，也可能是用户自己放的
            entry["state"] = "present_untracked"
        out.append(entry)
    return out


# ---------------------------------------------------------------- 下载安装

def install(target, item_id, mirror_mode="自动（直连 → 镜像）",
            overwrite=False, progress_cb=None, timeout=30):
    """下载并安装一个条目。返回 {ok, detail, ...}。

    规则：
      · 目标目录必须存在（不替用户猜路径）
      · 已存在且 overwrite=False → 直接报「已存在」并给出 state，不做覆盖
      · 覆盖前备份成 `<文件名>.bak-时间戳`
      · 有 sha256 就严格校验；没有就记实际哈希并标注未校验
    """
    item = by_id(item_id)
    if item is None:
        return {"ok": False, "detail": f"清单里没有这个条目：{item_id}"}
    target = Path(target) if target else None
    if not target or not target.is_dir():
        return {"ok": False, "detail": f"目标配置目录不存在：{target}"}

    # archive 型走另一条路（zip 里挑文件），逻辑差得远，分开写更清楚
    if item.get("archive"):
        res = install_archive(target, item, mirror_mode=mirror_mode,
                              overwrite=overwrite, progress_cb=progress_cb,
                              timeout=max(timeout, 60))
        if res.get("ok"):
            record_install(item, res["dest"], actual_sha=res["sha256"],
                           verified=res["verified"], files=res["files"])
        return res

    dest = target / item["dest"]
    dest.parent.mkdir(parents=True, exist_ok=True)
    existed = dest.is_file()
    if existed and not overwrite:
        return {"ok": False, "skipped": True,
                "detail": f"{dest.name} 已存在，没动它（想换新版请勾选覆盖）",
                "path": str(dest)}

    tmp = dest.with_name(dest.name + ".part")
    try:
        used = ""
        last_err = None
        for prefix in build_url_candidates(item["url"], mirror_mode):
            url = (prefix + item["url"]) if prefix else item["url"]
            label = "直连" if not prefix else prefix.rstrip("/").replace("https://", "")
            try:
                download_file(url, tmp, progress_cb=progress_cb, timeout=timeout)
                used = label
                break
            except Exception as e:                      # 换下一条线路
                last_err = e
        else:
            raise RuntimeError(f"所有线路都失败（最后：{last_err}）")

        if not tmp.is_file() or tmp.stat().st_size == 0:
            raise RuntimeError("下载到的文件是空的")

        expected = (item.get("sha256") or "").strip()
        verified = False
        actual = ""
        if expected:
            passed, actual = verify_sha256(tmp, expected)
            if not passed:
                raise RuntimeError(
                    f"sha256 校验失败：期望 {expected[:12]}…，实际 {actual[:12]}…")
            verified = True
        else:
            actual = _file_sha(tmp)

        backup = None
        if existed:
            backup = textio.backup(dest)
        shutil.move(str(tmp), str(dest))
    except Exception as e:
        try:
            tmp.unlink()
        except OSError:
            pass
        return {"ok": False, "detail": f"安装失败：{e}"}

    record_install(item, dest, actual_sha=actual, verified=verified)
    detail = f"已安装 {item['name']} → {item['dest']}"
    detail += f"（线路：{used}）"
    if not verified:
        detail += "；上游未提供 sha256，本次未做完整性校验"
    if backup:
        detail += f"；原文件已备份 {backup.name}"
    return {"ok": True, "detail": detail, "path": str(dest),
            "sha256": actual, "verified": verified,
            "backup": str(backup) if backup else ""}


def _uninstall_files(target, item_id, rec, files, force=False):
    """卸载 archive 型：按清单里记的每个文件删。

    规矩和单文件一样：**用户改过的不删**。改成"部分成功"也要说清楚 ——
    报一句"已卸载"然后偷偷留下三个文件，比直接报错还糟。
    """
    base = Path(rec.get("path") or target)
    if rec.get("dest"):
        base = Path(target) / rec["dest"]
    kept, removed, backups = [], [], []
    for f in files:
        rel = f.get("rel") or ""
        p = base / rel
        if not p.is_file():
            continue                              # 已经没了，算删掉了
        if not force:
            now = _file_sha(p)
            if f.get("sha256") and now != f["sha256"]:
                kept.append({"rel": rel, "path": str(p), "why": "装完之后被改过"})
                continue
        b = textio.backup(p)
        if b:
            backups.append(str(b))
        try:
            p.unlink()
            removed.append(rel)
        except OSError as e:
            kept.append({"rel": rel, "path": str(p), "why": f"删不掉：{e}"})

    # 顺手清理空目录（只删空的）
    # ⚠ 别指望它一定成功：删除前会给每个文件留 `.bak-时间戳` 备份，
    # 备份还在目录里，目录就**不是空的** —— 这是设计，不是 bug。
    # 想彻底清干净得让用户自己删备份。
    for d in sorted({(base / f["rel"]).parent for f in files if f.get("rel")},
                    key=lambda x: -len(x.parts)):
        try:
            if d.is_dir() and not any(d.iterdir()):
                d.rmdir()
        except OSError:
            pass

    if kept and not force:
        return {"ok": False, "modified": True, "kept": kept, "removed": removed,
                "detail": f"{len(kept)} 个文件装完之后被改过，我没有删它们"
                          f"（已删 {len(removed)} 个）。确认要删请勾选「强制删除」。"}
    if kept:
        return {"ok": False, "kept": kept, "removed": removed,
                "detail": f"删掉了 {len(removed)} 个，还有 {len(kept)} 个删不掉"}
    forget_install(item_id)
    detail = f"已卸载 {len(removed)} 个文件"
    if backups:
        detail += f"（删之前备份了 {len(backups)} 个）"
    return {"ok": True, "detail": detail, "removed": removed,
            "backups": backups, "path": str(base)}


def uninstall(target, item_id, force=False):
    """卸载：只删清单里记着、且和安装时哈希一致的文件。

    用户自己改过的文件默认**不删** —— 宁可报错让他手动处理，
    也不要手一滑把人家调了半天的脚本删了。force=True 才强删。
    """
    item = by_id(item_id)
    target = Path(target) if target else None
    if not target or not target.is_dir():
        return {"ok": False, "detail": f"目标配置目录不存在：{target}"}
    rec = installed_map().get(item_id)
    if item is None and rec is None:
        return {"ok": False, "detail": f"不认识这个条目：{item_id}"}

    # ---- archive 型：一个个文件地删，每个都要过"用户改过没有"这一关 ----
    files = (rec or {}).get("installed_files")
    if files:
        return _uninstall_files(target, item_id, rec, files, force=force)

    rel = (item or {}).get("dest") or ""
    path = Path(rec["path"]) if rec and rec.get("path") else (target / rel if rel else None)
    if path is None:
        return {"ok": False, "detail": "清单里没有这个条目的安装记录"}

    if not path.is_file():
        forget_install(item_id)
        return {"ok": True, "detail": f"{path.name} 已经不在了，只清掉了安装记录"}

    if not force:
        expected = (rec or {}).get("installed_sha256") or ""
        now = _file_sha(path)
        if expected and now != expected:
            return {"ok": False, "modified": True, "path": str(path),
                    "detail": f"{path.name} 装完之后被改过，我没有删它。"
                              f"确认要删请勾选「强制删除」。"}

    backup = textio.backup(path)
    try:
        path.unlink()
    except OSError as e:
        return {"ok": False, "detail": f"删不掉：{e}"}
    forget_install(item_id)
    detail = f"已卸载 {path.name}"
    if backup:
        detail += f"（删之前备份成 {backup.name}）"
    return {"ok": True, "detail": detail, "path": str(path),
            "backup": str(backup) if backup else ""}


def check_links(kind="", timeout=15):
    """把清单里的 URL 逐条 HEAD 一遍，报告哪些失效。

    这是**发布前的固定动作**（路线图 §5.5 要求的"校验链接"流程）：
    上游改路径 / 删文件是常态，清单不会自己知道。
    返回 [{id, name, ok, status, detail}]。
    """
    import urllib.error
    import urllib.request

    out = []
    for item in catalog_for(kind):
        entry = {"id": item["id"], "name": item["name"], "ok": False,
                 "status": 0, "detail": "", "url": item["url"]}
        try:
            req = urllib.request.Request(
                item["url"], method="HEAD",
                headers={"User-Agent": "MPVConfigBuilder/0.1"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                entry["status"] = resp.status
                entry["ok"] = 200 <= resp.status < 400
                size = resp.headers.get("Content-Length")
                entry["detail"] = f"{resp.status}" + (f" · {size} B" if size else "")
        except urllib.error.HTTPError as e:
            entry["status"] = e.code
            entry["detail"] = f"{e.code} {e.reason}"
        except Exception as e:
            entry["detail"] = f"{type(e).__name__}: {str(e)[:80]}"
        out.append(entry)
    return out


__all__ = [
    "CATALOG", "KINDS", "by_id", "catalog_for", "check_links",
    "manifest_path", "load_manifest", "save_manifest", "installed_map",
    "record_install", "forget_install", "list_items", "install", "uninstall",
]
