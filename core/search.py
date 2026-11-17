# -*- coding: utf-8 -*-
"""统一搜索：一份关键词，四类东西一起找。

四类 = 配置项（813 项选项库）/ uosc 选项 / 当前键位表 / 目标目录里的脚本。
只做「找」，不做「改」；每条结果带上它属于哪个页面，界面据此给跳转提示。

为什么放核心层而不是界面里：键位要从目标目录读、选项库要查缓存，
这些都是有 I/O 的活；界面只负责把结果画出来。
"""
from pathlib import Path

from . import keys, options_db, uosc

LIMIT_PER_GROUP = 8


def _hit(text, needle):
    return needle in str(text or "").lower()


def _options(needle):
    db = options_db.load_db()
    hits = options_db.search(db, needle, limit=LIMIT_PER_GROUP)
    items = []
    for e in hits:
        items.append({
            "key": e.get("key", ""),
            "title": e.get("zh_sig") or e.get("zh_desc") or e.get("key", ""),
            "detail": (e.get("zh_desc") or "")[:120],
            "page": "expert",
            "page_label": "完全体",
            "copy": e.get("key", ""),
        })
    return items


def _uosc(needle):
    items = []
    for key, meta in uosc.META.items():
        if _hit(key, needle) or _hit(meta["zh"], needle):
            items.append({
                "key": key,
                "title": meta["zh"],
                "detail": f"默认 {meta['default'] or '（空）'} · {uosc.GROUP_LABEL[meta['group']]}",
                "page": "expert",
                "page_label": "完全体 → uosc 设置",
                "copy": key,
            })
        if len(items) >= LIMIT_PER_GROUP:
            break
    return items


def _keybinds(target, needle):
    if not target:
        return []
    try:
        info = keys.load_keymap(target)
    except Exception:
        return []
    items = []
    files = info.get("files") or []
    rows = []
    for f in files:
        if f.get("active"):
            rows = f.get("rows") or []
            break
    if not rows and files:
        rows = files[0].get("rows") or []
    for row in rows:
        if row.get("kind") != "bind" or not row.get("enabled", True):
            continue
        if _hit(row.get("key"), needle) or _hit(row.get("cmd"), needle) \
                or _hit(row.get("comment"), needle):
            items.append({
                "key": row.get("key", ""),
                "title": row.get("desc") or row.get("comment") or row.get("cmd", ""),
                "detail": row.get("cmd", ""),
                "page": "keys",
                "page_label": "快捷键",
                "copy": row.get("key", ""),
            })
        if len(items) >= LIMIT_PER_GROUP:
            break
    return items


def _scripts(target, needle):
    if not target:
        return []
    base = Path(target)
    items = []
    for sub, label in (("scripts", "脚本"), ("script-opts", "脚本配置")):
        d = base / sub
        if not d.is_dir():
            continue
        for p in sorted(d.iterdir()):
            if not p.is_file() or not _hit(p.name, needle):
                continue
            items.append({
                "key": p.name,
                "title": f"{label}：{p.name}",
                "detail": str(p),
                "page": "downloads",
                "page_label": "下载中心",
                "copy": str(p),
            })
            if len(items) >= LIMIT_PER_GROUP:
                return items
    return items


def search(target, keyword):
    """按关键词搜四类内容，返回 {ok, q, total, groups}。"""
    q = str(keyword or "").strip()
    if not q:
        return {"ok": False, "detail": "输入几个字再搜（键名、中文说明、键位都行）"}
    needle = q.lower()
    groups = []
    for gid, name, fn in (
        ("options", "📖 配置项", lambda: _options(needle)),
        ("uosc", "🎛️ uosc", lambda: _uosc(needle)),
        ("keys", "⌨️ 键位", lambda: _keybinds(target, needle)),
        ("scripts", "📦 脚本", lambda: _scripts(target, needle)),
    ):
        items = fn()
        if items:
            groups.append({"id": gid, "name": name, "items": items})
    total = sum(len(g["items"]) for g in groups)
    return {"ok": True, "q": q, "total": total, "groups": groups,
            "target": str(target or "")}
