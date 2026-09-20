# -*- coding: utf-8 -*-
"""硬件/显示环境探测（只用标准库，不依赖界面）。

检测失败一律返回 0 或空串，由界面降级为手动输入。
"""
import ctypes
import subprocess

VREFRESH = 116  # GetDeviceCaps 的刷新率索引

_CACHE = None   # detect_all() 的结果缓存（进程内）


def screen_size():
    """返回主显示器分辨率 (w, h)，失败返回 (0, 0)。"""
    try:
        user32 = ctypes.windll.user32
        return int(user32.GetSystemMetrics(0)), int(user32.GetSystemMetrics(1))
    except Exception:
        return 0, 0


def refresh_rate():
    """返回主显示器刷新率（Hz），失败返回 0。"""
    try:
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        hdc = user32.GetDC(0)
        try:
            return int(gdi32.GetDeviceCaps(hdc, VREFRESH))
        finally:
            user32.ReleaseDC(0, hdc)
    except Exception:
        return 0


def gpu_name():
    """返回第一块显卡的名字，失败返回空串。"""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance Win32_VideoController | "
             "Select-Object -First 1 -ExpandProperty Name)"],
            capture_output=True, text=True, timeout=8)
        return (out.stdout or "").strip()
    except Exception:
        return ""


def detect_all(use_cache=True):
    """一次性返回探测结果字典。

    结果默认进程内缓存：GPU 名要靠**起一个 PowerShell 进程**问出来（慢、有 8 秒超时），
    而 /api/status 每次刷新都会调这里 —— 不缓存的话界面每动一下就等一次进程启动。
    以前 `refresh_rate()` 还在同一个函数里被调了两次。
    """
    global _CACHE
    if use_cache and _CACHE is not None:
        return dict(_CACHE)
    w, h = screen_size()
    hz = refresh_rate()
    result = {
        "resolution": f"{w}x{h}" if w and h else "",
        "refresh": f"{hz}" if hz else "",
        "gpu": gpu_name(),
    }
    if use_cache:
        _CACHE = dict(result)
    return result


def clear_cache():
    """清掉探测缓存（界面上的「重新检测」用）。"""
    global _CACHE
    _CACHE = None
