# -*- coding: utf-8 -*-
"""版本检测。

两类检查：
    check_tool_update()  工具自身（需要填 TOOL_MANIFEST_URL，没有就静默跳过）
    check_lazy_update()  已安装的 mpv-lazy（对比本地记录的 tag 与最新 release）
"""
import json
import re

from .installer import REPO, fetch_latest_release
from .net import http_fetch
from .schema import VERSION

# 发布后填这里：一个返回 {"version": "0.2.0", "url": "...", "notes": "..."} 的地址
TOOL_MANIFEST_URL = ""


def version_tuple(text):
    nums = [int(x) for x in re.findall(r"\d+", str(text))[:3]]
    while len(nums) < 3:
        nums.append(0)
    return tuple(nums)


def is_newer(latest, current):
    return version_tuple(latest) > version_tuple(current)


def check_tool_update(current=VERSION, manifest_url=TOOL_MANIFEST_URL, timeout=15):
    """有新版本返回 {'version','url','notes'}，否则返回 None。未配置地址时始终 None。"""
    if not manifest_url:
        return None
    try:
        raw = http_fetch(manifest_url, timeout).decode("utf-8", "replace")
        data = json.loads(raw)
    except Exception:
        return None
    latest = str(data.get("version", "")).strip()
    if latest and is_newer(latest, current):
        return {"version": latest, "url": data.get("url", ""), "notes": data.get("notes", "")}
    return None


def check_lazy_update(known_tag, repo=REPO):
    """本地记录的 tag 与最新 release 不同时返回最新 tag，否则 None。"""
    if not known_tag:
        return None
    try:
        rel = fetch_latest_release(repo)
    except Exception:
        return None
    tag = (rel.get("tag") or "").strip()
    if tag and tag != known_tag:
        return tag
    return None
