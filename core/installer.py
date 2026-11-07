# -*- coding: utf-8 -*-
"""mpv-lazy 一键安装：查最新版 → 下载 → 校验 → 解压 → 定位配置目录。

只提供官方 release 的下载，不重新打包分发。
解压优先级：zip（标准库）→ 7z.exe（若系统有）→ tar.exe（Win10+ 自带）→ 提示手动。
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import urllib.request
import zipfile
from pathlib import Path

from .i18n import T, get_lang

from .net import build_url_candidates, http_fetch
from . import textio

REPO = "hooke007/mpv_PlayKit"
GITHUB_API = f"https://api.github.com/repos/{REPO}/releases/latest"
USER_AGENT = "MPVConfigBuilder/0.1"


def default_install_dir():
    """默认安装目录：%LOCALAPPDATA%\\mpv-lazy（免管理员权限）。"""
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "mpv-lazy"


def fetch_latest_release(repo=REPO, timeout=25):
    """取最新 release 信息（不硬编码版本号）。"""
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    raw = http_fetch(url, timeout).decode("utf-8", "replace")
    data = json.loads(raw)
    assets = []
    for a in data.get("assets", []):
        assets.append({
            "name": a.get("name", ""),
            "size": int(a.get("size") or 0),
            "url": a.get("browser_download_url", ""),
            "digest": (a.get("digest") or "").replace("sha256:", "").strip(),
        })
    return {"tag": data.get("tag_name", ""), "name": data.get("name", ""), "assets": assets}


def pick_asset(assets):
    """优先 zip，其次 7z；同类里选体积最大的（通常是完整包）。"""
    def rank(a):
        n = a["name"].lower()
        if n.endswith(".zip"):
            return 0
        if n.endswith(".7z"):
            return 1
        return 9

    usable = [a for a in assets if rank(a) < 9 and a.get("url")]
    if not usable:
        return None
    usable.sort(key=lambda a: (rank(a), -a["size"]))
    return usable[0]


# ---------------------------------------------------------------- 该装哪一个包

# ⚠ 这段是**实测之后才写对的**。第一版直接用 pick_asset，结果选中了
# `mpv-lazy-xxx-noVS.7z`（47 MB）—— 名字里的 noVS = **没有 VapourSynth**。
# 而本项目的补帧 / 多脚本融合功能全都依赖 VapourSynth：装了这个包，
# 用户会得到一个"能放片但补帧用不了"的 mpv，而且他不知道为什么。
#
# 完整包（带 VS）是**分卷**的：`...-vsNV.7z.001` / `.002`，合计 2.7 GB。
# 所以这里做两件事：
#   ① 认出"完整包"和"精简包"，把差别**摆在用户面前**，让他自己选
#      （2.7 GB vs 47 MB 是真金白银的流量，不能替他决定）；
#   ② **分卷包必须所有卷都在**，少一卷就不算可用 —— 否则下到一半才失败。

VS_HINT = ("vs", "vapoursynth")
COMPACT_HINT = ("novs", "no-vs", "novapoursynth")


def _asset_ext(name):
    n = str(name or "").lower()
    m = re.search(r"\.(zip|7z)(\.\d{3})?$", n)
    return m.group(0) if m else ""


def _volume_no(name):
    m = re.search(r"\.(?:7z|zip)\.(\d{3})$", str(name or "").lower())
    return int(m.group(1)) if m else 0


# 7z 分卷的判据在**文件头里**，不在文件名里 —— 一个叫 `x.7z.001` 的文件
# 完全可能就是个名字带 `.001` 的普通单文件压缩包。
# `k_End` / `k_NextHeaderOffset` / `k_NextHeaderSize` 三个字段全为
# 0xFFFFFFFFFFFFFFFF 时，7z 才认为"这只是第一卷，后面还有"。
_7Z_SIG = b"7z\xBC\xAF\x27\x1C"
_U64_MAX = 0xFFFFFFFFFFFFFFFF


def sevenzip_is_split(path):
    """这个 7z 是不是"还有后续卷"？读文件头判断。

    返回 True / False / None（**None = 判断不了**，比如文件不全或不是 7z）。
    判断不了时上层要按"不确定"处理，不能当成"完整"。
    """
    try:
        with open(path, "rb") as f:
            head = f.read(32)
    except OSError:
        return None
    if len(head) < 32 or not head.startswith(_7Z_SIG):
        return None
    # 签名头布局：magic(6) ver(2) crc(4) | StartHeader: nextoff(8) nextsize(8) crc(4)
    next_off = int.from_bytes(head[12:20], "little")
    next_size = int.from_bytes(head[20:28], "little")
    if next_off == _U64_MAX or next_size == _U64_MAX:
        return True
    return False


def split_volumes_ok(vols, first_path=None):
    """分卷齐不齐？返回 (齐了吗, 缺哪几卷, 说明)。

    两件事都要查：
      ① 编号必须从 001 开始**连续**（有 001、003 却缺 002 就是坏的）；
      ② 光有 001 时，还得看 7z 文件头**自己怎么说** —— 它说"后面还有卷"
         而目录里没有，那就是真缺；它说"我就是完整的"，那就是个名字怪的单文件包。
    第 ② 条是实测逼出来的：只按"有没有 .002"判会误伤改名过的单文件包，
    只按编号判又会漏掉"001 后面还有但没下全"的情况。
    """
    vols = sorted(v for v in vols if v > 0)
    if not vols:
        return True, [], ""
    if vols[0] != 1:
        return False, [v for v in range(1, max(vols) + 1) if v not in vols], \
            T(f"分卷编号不是从 001 开始（最小是 {vols[0]:03d}）",
              f"Volume numbering does not start at 001 (smallest is {vols[0]:03d})")
    want = list(range(1, max(vols) + 1))
    missing = [v for v in want if v not in vols]
    if missing:
        return False, missing, T(
            f"缺第 {'、'.join(f'{v:03d}' for v in missing)} 卷",
            f"Missing volume(s) {', '.join(f'{v:03d}' for v in missing)}")
    if len(vols) == 1 and first_path is not None:
        split = sevenzip_is_split(first_path)
        if split is True:
            return False, [2], T(
                "文件头表明这是分卷的第一卷，但只找到这一卷",
                "The file header says this is the first volume of a split, but only this one was found")
    return True, [], ""


def classify_assets(assets):
    """把 release 里的资产分成"能用的完整包 / 精简包 / 安装器 / 不完整的"。

    返回 (可用列表, 说明列表)。**只报告，不替用户选。**
    """
    usable, notes = [], []
    # 只看包，不看别的附件
    packs = [a for a in assets if _asset_ext(a["name"]) and a.get("url")]
    installers = [a for a in assets
                  if a["name"].lower().endswith(".exe") and a.get("url")]
    if installers:
        notes.append(T(f"这个 release 还提供安装器（{installers[0]['name']}）—— "
                     "本项目只做「绿包 + 配置」，不碰安装器，要不要用你自己定。",
                     f"This release also ships an installer ({installers[0]['name']}) - "
                     "this project only does the portable package + config and never touches installers; that choice is yours."))

    # 归组：**分卷**按基名归（`a.7z.001` + `a.7z.002` 是一组），
    # **单文件**按完整扩展名归（`x.zip` 与 `x.7z` 是两个独立的包，不是一组）。
    # ⚠ 第一版一律剥掉扩展名，于是 `x.zip` 和 `x.7z` 被当成同一个包的两卷 ——
    # 既会算错大小，还会误报"缺卷"。扩展名必须留在 key 里。
    groups = {}
    for a in packs:
        low = a["name"].lower()
        m = re.match(r"^(.*\.(?:7z|zip))\.(\d{3})$", low)
        key = m.group(1) if m else low          # 分卷取基名；单文件取全名
        groups.setdefault(key, []).append(a)

    for key, members in groups.items():
        members.sort(key=lambda a: _volume_no(a["name"]))
        vols = [_volume_no(m["name"]) for m in members]
        split = any(v > 0 for v in vols)
        missing, why_missing = [], ""
        if split:
            # 只看文件名能判断的都在 split_volumes_ok 里；真正下下来的包
            # 会在下载完之后再按文件头复核一次（见 run_install 的 verify 段）。
            # 这里没有本地文件，所以只查编号。
            _ok, missing, why_missing = split_volumes_ok(vols, first_path=None)
        total = sum(m["size"] for m in members)
        low = " ".join(m["name"].lower() for m in members)
        compact = any(h in low for h in COMPACT_HINT)
        has_vs = any(h in low for h in VS_HINT) and not compact
        usable.append({
            "base": key,
            "name": members[0]["name"],
            "names": [m["name"] for m in members],
            "urls": [m["url"] for m in members],
            "url": members[0]["url"],
            "size": total,
            "split": split,
            "volumes": len(members),
            "missing_volumes": missing,
            "complete": not missing,
            "volume_note": why_missing,
            # 名字以 `.001` 结尾却只有一卷 —— 光看文件名分不清它是
            # "分卷的第一卷（后面丢了）"还是"名字怪的单文件包"。
            # 这种不确定要**让用户知道**，别装作没事。
            "risky_split": bool(split and len(members) == 1),
            "compact": compact,          # True = 没有 VapourSynth
            "has_vapoursynth": has_vs,
            "digest": asset_digest(members[0]),
            "digests": [asset_digest(m) for m in members],
        })
    usable.sort(key=lambda x: (not x["complete"], x["compact"], x["size"]))
    return usable, notes


def recommend_asset(assets, want_vapoursynth=True):
    """挑一个包，并**说清为什么**。

    返回 (包 或 None, 理由, 全部可用列表, 说明列表)。

    选法：能装下的完整包优先；用户要补帧（`want_vapoursynth`）就不要精简包；
    分卷缺卷的一律排除。挑不到就如实说"这个 release 里没有能直接装的包"。
    """
    usable, notes = classify_assets(assets)
    if not usable:
        return None, T("这个 release 里没有可直接下载的 zip/7z 包", "No directly downloadable zip/7z package in this release"), [], notes
    ok = [u for u in usable if u["complete"] and not u["risky_split"]]
    if not ok:
        # 只有"可能缺卷"的分卷包，或干脆没有完整的
        risky = [u for u in usable if u["complete"]]
        if risky:
            pick = risky[0]
            return pick, T(f"只能用 {pick['name']} —— ⚠ 它看上去是分卷的第一卷，"
                           "但 release 里只有这一卷，下完可能解不开",
                           f"Only {pick['name']} is usable - it looks like the first volume of a split, "
                           "but the release ships only this one; the download may not extract"), usable, notes
        first = usable[0]
        return None, T(f"包是分卷的，但缺了第 {first['missing_volumes']} 卷，"
                       "没法完整解压",
                       f"The package is split but volume(s) {first['missing_volumes']} are missing; "
                       "it cannot be extracted completely"), usable, notes
    if want_vapoursynth:
        full = [u for u in ok if u["has_vapoursynth"] and not u["compact"]]
        if full:
            pick = full[0]
            _vol = (T(f"，{pick['volumes']} 个分卷", f", {pick['volumes']} volumes")
                    if pick["split"] else "")
            return pick, T(f"选了带 VapourSynth 的完整包（{pick['name']}，"
                           f"{pick['size'] / (1 << 20):.0f} MB"
                           + _vol
                           + "）—— 补帧与多脚本融合都要它",
                           f"Picked the VapourSynth-complete package ({pick['name']}, "
                           f"{pick['size'] / (1 << 20):.0f} MB"
                           + _vol
                           + ") - MEMC and multi-script fusion depend on it"), usable, notes
        compact = [u for u in ok if u["compact"]]
        if compact:
            return compact[0], T("⚠ 这个 release 里**只有不带 VapourSynth 的精简包**"
                                 f"（{compact[0]['name']}）—— 装上能放片，"
                                 "但补帧 / 多脚本融合用不了",
                                 "⚠ This release ships ONLY the compact package without VapourSynth "
                                 f"({compact[0]['name']}) - playback works, "
                                 "but MEMC / multi-script fusion do not"), usable, notes
    pick = ok[0]
    return pick, T(f"选了 {pick['name']}（{pick['size'] / (1 << 20):.0f} MB）",
                   f"Picked {pick['name']} ({pick['size'] / (1 << 20):.0f} MB)"), usable, notes


def _content_range_start(value):
    """解析 "bytes 1024-2047/2048" 的起点；格式不对返回 None。"""
    m = re.match(r"\s*bytes\s+(\d+)-(\d+)/(\d+|\*)", str(value or ""))
    return int(m.group(1)) if m else None


def resume_plan(status, content_range, local_size):
    """决定这次是续传还是重下。返回 (start, mode, restarted)。

    · 本地没有片段            → 从 0 开始写
    · 非 206（镜像/CDN 忽略 Range，返回 200 全文）→ 必须从 0 重下
    · Content-Range 起点不符  → 本地片段不可信，重下
    · 其余                    → 续传

    旧实现只要本地有字节就 `ab` 追加，服务器不认 Range 时包体前段重复、后段错位。
    """
    local_size = int(local_size or 0)
    if local_size <= 0:
        return 0, "wb", False
    if status != 206:
        return 0, "wb", True
    start = _content_range_start(content_range)
    if start is None or start != local_size:
        return 0, "wb", True
    return local_size, "ab", False


def _part_meta_path(dest):
    return Path(str(dest) + ".meta")


def _read_part_meta(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_part_meta(path, data):
    try:
        textio.write_atomic(Path(path),
                            json.dumps(data, ensure_ascii=False).encode("utf-8"))
    except OSError:
        pass


def download_file(url, dest, progress_cb=None, cancel_cb=None,
                  chunk=1 << 16, timeout=30, resume=True):
    """流式下载，支持断点续传与取消。返回目标路径。

    续传前必须确认服务器真的按 Range 返回 `206` 且起点匹配 —— 镜像站忽略 Range
    返回 200 全文时，旧实现会直接 "ab" 追加，包体前段重复、后段错位（坏包）。
    旁挂的 `.meta` 记录 url / etag / 总长：没有可信元数据就不敢续。
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    meta_path = _part_meta_path(dest)

    start = dest.stat().st_size if (resume and dest.exists()) else 0
    meta = _read_part_meta(meta_path)
    if start and meta.get("url") != url:
        start = 0                      # 元数据缺失 / 换了下载源：不敢续

    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    if start:
        req.add_header("Range", f"bytes={start}-")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        length = int(resp.headers.get("Content-Length") or 0)
        start, mode, _restarted = resume_plan(
            resp.status, resp.headers.get("Content-Range"), start)
        total = length + start if resp.status == 206 else length
        if progress_cb:
            progress_cb(start, total)
        _write_part_meta(meta_path, {
            "url": url,
            "etag": resp.headers.get("ETag", ""),
            "total": total,
            "start": start,
        })
        done = start
        with open(dest, mode) as f:
            while True:
                if cancel_cb and cancel_cb():
                    raise RuntimeError("已取消")
                block = resp.read(chunk)
                if not block:
                    break
                f.write(block)
                done += len(block)
                if progress_cb:
                    progress_cb(done, total)
    try:
        meta_path.unlink()
    except OSError:
        pass
    return dest


def verify_sha256(path, digest):
    """返回 (是否通过, 实际值)。

    digest 为空时**不算通过** —— 以前写的是 `if not digest: return True, ""`，
    等于"没有校验值就放行"，而这个功能的卖点就是校验。
    调用方拿到 (False, actual) 后应当自己决定要不要提示用户"这次没能校验"。
    """
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    actual = h.hexdigest().lower()
    if not digest:
        return False, actual          # 没有期望值：校验不成立，但把实际值给出去
    return actual == digest.lower(), actual


def verify_size(path, expected_size):
    """退化的校验：文件大小是否与 API 报的一致（没有 digest 时兜底）。"""
    try:
        return int(expected_size) > 0 and Path(path).stat().st_size == int(expected_size), \
            Path(path).stat().st_size
    except OSError:
        return False, 0


def download_with_mirrors(url, dest, mirror_mode="自动（直连 → 镜像）",
                          progress_cb=None, cancel_cb=None, timeout=30):
    """按镜像线路依次尝试下载，返回 (路径, 用到的线路说明)。

    以前 `build_url_candidates` 被 import 了却从未使用 —— core 这一层的下载
    没有镜像回退，只有旧 Tkinter 界面自己拼了前缀。现在补上：直连失败就换镜像，
    全挂了才报错（并把最后一次的错误带出来）。
    """
    last_err = None
    for prefix in build_url_candidates(url, mirror_mode):
        target = (prefix + url) if prefix else url
        label = "直连" if not prefix else prefix.rstrip("/").replace("https://", "")
        try:
            download_file(target, dest, progress_cb=progress_cb,
                          cancel_cb=cancel_cb, timeout=timeout)
            return Path(dest), label
        except Exception as e:                      # 网络/HTTP/取消都换下一路
            last_err = e
            if cancel_cb and cancel_cb():
                raise
    raise RuntimeError(f"所有线路都失败了（最后一条：{last_err}）")


def safe_extract_members(names, target):
    """过滤出「解压后仍落在 target 里」的成员，防止 zip slip。

    zip 里可以写 `../../evil.txt` 这样的成员名，标准库 extract 会照写不误。
    """
    target = Path(target).resolve()
    ok, bad = [], []
    for name in names:
        dest = (target / name).resolve()
        try:
            dest.relative_to(target)
            ok.append(name)
        except ValueError:
            bad.append(name)
    return ok, bad


def extract_archive(archive, target, progress_cb=None):
    """解压到 target，返回使用的方法名。"""
    archive = Path(archive)
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)

    if archive.suffix.lower() == ".zip":
        with zipfile.ZipFile(archive) as zf:
            names = zf.namelist()
            safe, bad = safe_extract_members(names, target)
            if bad:
                raise RuntimeError(
                    f"压缩包里有 {len(bad)} 个越界路径（例如 {bad[0]}），拒绝解压")
            for i, name in enumerate(safe, 1):
                zf.extract(name, target)
                if progress_cb and (i % 50 == 0 or i == len(safe)):
                    progress_cb(i, len(safe))
        return "zipfile"

    seven = shutil.which("7z") or shutil.which("7za") or shutil.which("7zr")
    if seven:
        res = subprocess.run([seven, "x", "-y", f"-o{target}", str(archive)],
                             capture_output=True, text=True)
        if res.returncode == 0:
            return "7z"
        raise RuntimeError("7z 解压失败：" + (res.stderr or res.stdout or "").strip()[:200])

    tar = shutil.which("tar")
    if tar:
        res = subprocess.run([tar, "-xf", str(archive), "-C", str(target)],
                             capture_output=True, text=True)
        if res.returncode == 0:
            return "tar"
        raise RuntimeError("tar 解压失败：" + (res.stderr or "").strip()[:200])

    raise RuntimeError("系统没有 7z/tar，无法解压该格式；请手动解压后把目录填到上面")


def find_portable_config(root):
    """在解压结果里找 portable_config（兼容多套一层目录的情况）。"""
    root = Path(root)
    if not root.is_dir():
        return None
    first = root / "portable_config"
    if first.is_dir():
        return first
    for child in sorted(root.iterdir()):
        if child.is_dir() and (child / "portable_config").is_dir():
            return child / "portable_config"
    for child in sorted(root.iterdir()):
        if child.is_dir() and ((child / "mpv.exe").is_file() or (child / "mpv.conf").is_file()):
            return child
    for p in sorted(root.rglob("portable_config")):
        if p.is_dir():
            return p
    return None


def install_plan(target_dir, mirror_mode="自动（直连 → 镜像）"):
    """给界面用的一步式说明（不下载）：返回 (release 信息, 选中的资产)。"""
    rel = fetch_latest_release()
    asset = pick_asset(rel["assets"])
    if asset is None:
        raise RuntimeError("最新 release 里没有找到 zip/7z 包")
    return rel, asset


# ---------------------------------------------------------------- 一键安装（R-8w）

def asset_digest(asset):
    """资产的 sha256；拿不到就返回空串。

    **不要为空时假装通过。** GitHub 的 `digest` 字段是后加的，老 release
    可能没有；旧 Tkinter 里那句 `if not digest: return True` 就是这个问题
    （已修，见 `verify_sha256`）。这里统一成"拿到就校验、拿不到就如实说"。
    """
    d = str((asset or {}).get("digest") or "").strip().lower()
    if d.startswith("sha256:"):
        d = d[len("sha256:"):]
    if len(d) != 64 or any(ch not in "0123456789abcdef" for ch in d):
        return ""
    return d


def free_space(path):
    """目标盘剩余空间（字节）。取不到返回 None（不编造数字）。"""
    try:
        import shutil as _sh
        return _sh.disk_usage(str(path)).free
    except Exception:                                  # noqa: BLE001
        return None


def can_install(target_dir, asset, need_extra=0):
    """装得下吗？返回 (能不能, 说明, {总需, 可用})。

    为什么要有这一步：mpv-lazy 的完整包是 **GB 级**，下到一半发现盘满了
    是最糟糕的失败方式 —— 既浪费了流量，又留下半个包。
    所以先问一句，而且把"要不要额外解压空间"也算进去（解压后通常和压缩包
    一个量级，所以按 2 倍算）。
    """
    t = Path(target_dir)
    total_need = int((asset or {}).get("size") or 0) * 2 + int(need_extra or 0)
    free = free_space(t if t.exists() else (t.parent if t.parent.exists() else "."))
    info = {"need": total_need, "free": free,
            "pack": int((asset or {}).get("size") or 0)}
    if total_need <= 0:
        return True, T("包大小未知，跳过空间检查", "Package size unknown; skipping the space check"), info
    if free is None:
        return True, T("拿不到剩余空间，跳过检查（要自己留意盘够不够）",
                       "Free space unavailable; skipping the check (watch the disk yourself)"), info
    if free < total_need:
        return False, (T(f"空间不够：这个包 {info['pack'] // (1 << 20)} MB，"
                       f"解压后按 2 倍算需要 {total_need // (1 << 20)} MB，"
                       f"目标盘只剩 {free // (1 << 20)} MB",
                       f"Not enough space: the package is {info['pack'] // (1 << 20)} MB; "
                       f"extracted it needs about twice that ({total_need // (1 << 20)} MB), "
                       f"but the target drive only has {free // (1 << 20)} MB free")), info
    return True, "", info


def plan_install(target_dir, mirror_mode="自动（直连 → 镜像）", want_vapoursynth=True):
    """**不下载、不写盘**地把"要装什么、装到哪、装不装得下"算清楚。

    单独抽出来是为了能离线测试 —— 真正联网的部分只有 `fetch_latest_release`。
    也把**所有可用包**列出来：完整包 2.7 GB、精简包 47 MB，这个差别得让用户看见。
    """
    target = Path(target_dir)
    rel = fetch_latest_release()
    pick, why, usable, notes = recommend_asset(rel["assets"], want_vapoursynth)
    if pick is None:
        raise RuntimeError(why)
    ok, space_why, info = can_install(target, {"size": pick["size"]})
    exists = (target / "portable_config").is_dir()
    return {
        "tag": rel.get("tag", ""),
        "asset": {"name": pick["name"], "size": pick["size"],
                  "names": pick["names"], "split": pick["split"],
                  "volumes": pick["volumes"],
                  "url": pick["url"], "urls": pick["urls"],
                  "digest": pick["digest"], "digests": pick["digests"]},
        "reason": why,
        "notes": notes,
        "options": [{"name": u["name"], "size": u["size"], "split": u["split"],
                     "volumes": u["volumes"], "compact": u["compact"],
                     "has_vapoursynth": u["has_vapoursynth"],
                     "complete": u["complete"],
                     "missing_volumes": u["missing_volumes"]}
                    for u in usable],
        "target": str(target),
        "target_exists": target.is_dir(),
        "already_installed": exists,
        "space_ok": ok,
        "space_detail": space_why,
        "space": info,
        "mirror_mode": mirror_mode,
    }


def run_install(target_dir, mirror_mode="自动（直连 → 镜像）",
                stage_dir=None, progress=None, cancel_cb=None, timeout=60):
    """一键装 mpv-lazy 的完整流程：下载 → 校验 → 解压 → 定位。

    **安全规矩（跟别处一致）**：
      · 先下到 `stage/`，解压也在 `stage/`，**验完才搬到最终位置**；
      · 目标 `portable_config` 已存在时**不覆盖**，直接报"已经有了"；
      · sha256 拿不到就**如实说"未校验"**，绝不假装通过；
      · 每一步都通过 `progress(stage_name, percent, detail)` 上报。

    `progress` 回调的 stage 取值：check / download / verify / extract / locate / move。

    `timeout` 是每条线路的下载超时。默认 60s（GB 级的包要留足）；测试里
    会调小 —— 否则"下载失败"那条用例要等所有镜像线路轮完，单条就 60 秒。
    """
    def say(stage, percent, detail=""):
        if progress:
            try:
                progress(stage, int(percent), detail)
            except Exception:                          # noqa: BLE001
                pass

    target = Path(target_dir)
    if (target / "portable_config").is_dir():
        return {"ok": False, "detail": f"{target} 下已经有 portable_config 了，"
                                      "不覆盖已有的安装", "stage": "check"}

    say("check", 0, "读取最新版本…")
    # ⚠ 这里必须用 plan_install（走 recommend_asset），**不能用老的 install_plan** ——
    # 那条路是 pick_asset，会挑中 `-noVS` 精简包，装出来没有 VapourSynth，
    # 补帧和多脚本融合全废。见 recommend_asset 上面那段注释。
    try:
        plan = plan_install(target, mirror_mode)
    except Exception as e:                             # noqa: BLE001
        return {"ok": False, "detail": f"准备失败：{e}", "stage": "check"}
    asset = {"name": plan["asset"]["name"], "size": plan["asset"]["size"],
             "url": plan["asset"]["url"], "urls": plan["asset"]["urls"],
             "digest": plan["asset"]["digest"], "digests": plan["asset"]["digests"],
             "names": plan["asset"]["names"], "split": plan["asset"]["split"]}
    rel_tag = plan["tag"]
    # ⚠ 空间不够要**在这儿**就停，别开始下 —— 重写这段时漏掉过这个中止，
    # 结果是 2.7 GB 的包照下不误，下完才在别处失败。
    if not plan["space_ok"]:
        return {"ok": False, "detail": plan["space_detail"], "stage": "check",
                "space": plan.get("space")}
    if plan["space_detail"]:
        say("check", 2, plan["space_detail"])
    say("check", 2, plan["reason"])
    if plan["asset"]["split"] and plan["asset"]["volumes"] > 1:
        say("check", 2, f"这个包是分卷的（{plan['asset']['volumes']} 个），会依次下载")

    stage = Path(stage_dir) if stage_dir else (target / "_install_stage")
    stage.mkdir(parents=True, exist_ok=True)

    # --- 下载（带断点续传：stage 里的半个包下次还能接着用）---
    # 分卷包要**逐卷下**，而且文件名必须原样保留（`x.7z.001` / `.002`）——
    # 7z 靠这个命名认分卷，改名就解不开了。
    names = asset.get("names") or [asset["name"]]
    urls = asset.get("urls") or [asset["url"]]
    digests = asset.get("digests") or [asset["digest"]]
    total_all = asset["size"] or 1
    done_all = 0
    last = [-1]
    used = ""

    def on_bytes(done, total):
        overall = done_all + done
        pct = 3 + int(overall * 77 / total_all)
        if pct != last[0]:
            last[0] = pct
            say("download", min(pct, 80),
                f"{overall // (1 << 20)} MB / {total_all // (1 << 20)} MB")

    for idx, (nm, url) in enumerate(zip(names, urls)):
        arc = stage / nm
        if len(names) > 1:
            say("download", last[0] if last[0] > 0 else 3,
                f"第 {idx + 1}/{len(names)} 卷：{nm}")
        try:
            _path, used = download_with_mirrors(
                url, arc, mirror_mode=mirror_mode,
                progress_cb=on_bytes, cancel_cb=cancel_cb, timeout=timeout)
        except Exception as e:                         # noqa: BLE001
            return {"ok": False, "detail": f"下载失败（{nm}）：{e}",
                    "stage": "download", "staged": str(stage)}
        done_all += arc.stat().st_size if arc.exists() else 0

    # 解压入口是**第一卷**（7z 会自己去找同目录的后续卷）
    archive = stage / names[0]

    # 分卷的最终复核：文件名只能告诉我们"有几卷"，**文件头**才说得清
    # "这一卷后面还有没有"。缺卷的话现在就说，别等 7z 解到一半才报错。
    if asset.get("split"):
        got = [_volume_no(n) for n in names]
        ok_v, miss, why_v = split_volumes_ok(got, first_path=archive)
        if not ok_v:
            return {"ok": False,
                    "detail": f"分卷不完整：{why_v} —— 先别解压，"
                              f"卷都在 {stage} 里，补齐了再重跑",
                    "stage": "verify", "staged": str(stage)}

    # --- 校验（每一卷都校验）---
    verified = False
    checked = 0
    for nm, dig in zip(names, digests):
        if not dig:
            continue
        say("verify", 82, f"校验 sha256…（{nm}）" if len(names) > 1 else "校验 sha256…")
        good, actual = verify_sha256(stage / nm, dig)
        if not good:
            return {"ok": False,
                    "detail": f"{nm} 的 sha256 对不上，包可能坏了或被改过"
                              f"（期望 {dig[:12]}…，实际 {str(actual)[:12]}…）",
                    "stage": "verify", "staged": str(stage)}
        checked += 1
    if checked:
        verified = True
    else:
        say("verify", 82, "这个 release 没给 sha256，跳过校验（不做假通过）")

    # --- 解压 ---
    say("extract", 86, "解压中…")
    try:
        method = extract_archive(
            archive, stage,
            progress_cb=lambda i, n: say("extract", 86 + int(i * 6 / max(n, 1)),
                                         f"{i}/{n} 个文件"))
    except Exception as e:                             # noqa: BLE001
        return {"ok": False, "detail": f"解压失败：{e}", "stage": "extract",
                "staged": str(archive)}

    # --- 定位 ---
    say("locate", 93, "找 portable_config…")
    pc = find_portable_config(stage)
    if pc is None:
        return {"ok": False, "detail": "解压开了但没找到 portable_config，"
                                      "可能包结构变了 —— 去 stage 目录看看",
                "stage": "locate", "staged": str(stage)}

    # --- 就位：只把 portable_config 复制到目标 ---
    say("move", 95, "放到目标目录…")
    dest = target / "portable_config"
    if dest.exists():
        return {"ok": False, "detail": f"{dest} 已经存在，不覆盖",
                "stage": "move", "staged": str(pc)}
    try:
        import shutil as _sh
        dest.parent.mkdir(parents=True, exist_ok=True)
        _sh.copytree(pc, dest)
    except Exception as e:                             # noqa: BLE001
        return {"ok": False, "detail": f"复制到目标目录失败：{e}",
                "stage": "move", "staged": str(pc)}
    say("move", 100, "完成")
    return {"ok": True, "stage": "done", "verified": verified,
            "digest": asset.get("digest", ""), "mirror": used, "method": method,
            "tag": rel_tag, "asset": asset["name"],
            "volumes": len(names),
            "portable_config": str(dest), "staged": str(stage),
            "reason": plan.get("reason", ""),
            "detail": "装好了" + ("（sha256 已校验）" if verified
                                 else "（这个 release 没给 sha256，未校验）")}
