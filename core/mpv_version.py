# -*- coding: utf-8 -*-
"""mpv 版本探测（只用标准库，不依赖界面）。

服务于「版本级兼容检测」（待做 §〇 第 13 项）的子能力 ②：
探测用户实际运行的 mpv 版本，供 ③ 判断「当前版本不支持 / 该版本引入」的参数。

设计要点（与 core/hardware.py 同一套约定）：
- 探测失败一律返回 ``None``，不抛异常 —— 界面据此降级为「未知版本」。
- 自动探测走 ``shutil.which``；也可显式传入可执行文件路径（用于检测用户指定的 mpv）。
- 版本解析只取第一个 ``X.Y.Z``，容忍 ``-git-xxx`` 这类后缀。
"""
import re
import shutil
import subprocess
from typing import List, Optional, Set

# mpv --version 输出形如：
#   mpv 0.39.0-123-gabcdef (C) 2000-2024 mpv/MPlayer/mplayer2
#   mpv 0.38.0 (C) ...
_MPV_VERSION_RE = re.compile(r"mpv\s+(\d+\.\d+\.\d+)")

# PATH 自动探测的候选名（Windows 上 mpv.com / mpv.exe；其它平台是 mpv）
_CANDIDATES: List[str] = ("mpv", "mpv.exe", "mpv.com")

# 探测超时：起一个外部进程，不能无限等
_TIMEOUT = 5


def parse_version(text: str) -> Optional[str]:
    """从 ``mpv --version`` 的输出里抽取第一个语义版本 ``X.Y.Z``。

    抽不到（空串 / 不含版本）返回 ``None``。
    """
    if not text:
        return None
    m = _MPV_VERSION_RE.search(text)
    return m.group(1) if m else None


def detect_mpv_version(exe_path: Optional[str] = None) -> Optional[str]:
    """探测 mpv 版本。

    :param exe_path: 显式可执行文件路径；为 ``None`` 时在 PATH 里按
        ``_CANDIDATES`` 自动探测。
    :returns: 版本字符串（如 ``"0.39.0"``），任何失败返回 ``None``。
    """
    exe = exe_path or _find_mpv()
    if not exe:
        return None
    try:
        out = subprocess.run(
            [exe, "--version"],
            capture_output=True, text=True, timeout=_TIMEOUT,
        )
        if out.returncode != 0:
            return None
        return parse_version(out.stdout or out.stderr)
    except (OSError, subprocess.SubprocessError):
        # FileNotFoundError / TimeoutExpired / 其它启动错误：降级为未知
        return None


def _find_mpv() -> Optional[str]:
    """在 PATH 里按候选名找 mpv，找到第一个即返回；没有返回 ``None``。"""
    for name in _CANDIDATES:
        found = shutil.which(name)
        if found:
            return found
    return None


def compare_versions(a: str, b: str) -> int:
    """比较两个版本字符串：``a < b`` 返回 ``-1``，相等 ``0``，``a > b`` 返回 ``1``。

    只比较前三个数字段，非数字段按 ``0`` 处理。供 ③ 判定「参数所需版本 ≤ 当前版本」
    时使用，避免字符串比较把 ``1.9.1`` 排到 ``1.10.0`` 之后这类错误。
    """
    def _parts(v: str) -> List[int]:
        nums = [int(x) for x in re.findall(r"\d+", v)[:3]]
        while len(nums) < 3:
            nums.append(0)
        return nums

    pa, pb = _parts(a), _parts(b)
    if pa < pb:
        return -1
    if pa > pb:
        return 1
    return 0


def capture_mpv_options(exe_path: Optional[str] = None) -> Optional[Set[str]]:
    """抓取用户 mpv 支持的参数集合（来自 ``mpv --list-options``）。

    服务于「版本级兼容检测」③：与参数库比对，库里有、用户 mpv 没有的，就是
    它不支持的参数。失败（没装 mpv / 超时 / 非零退出）返回 ``None``，由上层
    降级为「未知版本 → 不报警」。
    """
    exe = exe_path or _find_mpv()
    if not exe:
        return None
    try:
        out = subprocess.run(
            [exe, "--list-options"],
            capture_output=True, text=True, timeout=_TIMEOUT,
        )
        if out.returncode != 0:
            return None
        return _parse_list_options(out.stdout)
    except (OSError, subprocess.SubprocessError):
        return None


def _parse_list_options(text: str) -> Set[str]:
    """从 ``mpv --list-options`` 文本抽出参数名集合（去前导横线）。

    规则：去掉前导空白后以 ``--`` 开头的行视为参数定义行（顶层参数或子参数），
    取第一个 ``--token``；标题行 / 说明文字忽略。说明文字极少以 ``--`` 开头，
    即便误判也只是把某条「当作支持」，不会误报「不支持」——方向安全。
    """
    keys: Set[str] = set()
    for line in (text or "").splitlines():
        s = line.strip()
        if not s.startswith("--"):
            continue
        m = re.match(r"--([A-Za-z0-9_-]+)", s)
        if m:
            keys.add(m.group(1))
    return keys


def diff_unsupported(db_keys, user_options) -> Set[str]:
    """返回参数库里有、但用户 mpv 不支持的 key 集合。

    :param db_keys: 参数库所有 key（如 ``core/options_db`` 的 ``options`` 键）。
    :param user_options: 用户 mpv 支持的 key 集合；为 ``None``/空时返回空集合
        ——版本未知不报警，避免误伤。
    """
    user_options = set(user_options or set())
    if not user_options:
        return set()
    return {k for k in db_keys if k not in user_options}


__all__ = ["parse_version", "detect_mpv_version", "compare_versions",
           "capture_mpv_options", "diff_unsupported", "_parse_list_options"]
