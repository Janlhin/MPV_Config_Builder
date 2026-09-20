# -*- coding: utf-8 -*-
"""选项中文说明与格式提示（R-25 / R-28 共用的那一层）。

**为什么要有这个模块**：829 项里有 466 项（56%）是「自由填值」——
`str 164 / float 156 / int 81 / list 54 / color 11`。这些项没有下拉可选，
用户必须自己知道该填什么格式。注释对它们不是锦上添花，而是**唯一的使用说明**。

两个入口共用这里：
  · R-25：生成配置时给每个选项附注释（`core/builder.py` 调 `annotate_lines`）
  · R-28：给已有配置补注释（`core/annotate.py`）

**两条诚实原则**（和全项目一致）：
  1. **查不到说明的不编造** —— 那行就不加注释，并且在统计里标出来，
     让用户知道是"库没收录"而不是"这行没问题"。
  2. **不假装知道格式** —— 格式提示只从库里真实存在的信息推（range / raw_sig /
     精选建议值），推不出来就不加括号。
"""
import re
from functools import lru_cache

from .schema import PARAMS, get_param_meta

# 行内注释压到 40–60 字（否则一行 200 列没法看）；上方注释可以到 90 字
INLINE_LIMIT = 56
ABOVE_LIMIT = 90

# 值本身是路径 / 文件
PATH_HINT = "路径"
# raw_sig 里这些片段当"类型提示"用（比 range 更能说明填什么）
_SIG_HINTS = (
    "window geometry", "file", "files", "path", "directory",
    "key/value list", "object settings list", "string list",
)

# 少数选项值得单独给一句话格式提示：它们的 raw_sig 是空的，
# 而 range 又推不出东西，但用户最容易在这里填错。
EXTRA_HINTS = {
    "sub-color": "#RRGGBB 或 #AARRGGBB（带 # 必须加引号）",
    "sub-border-color": "#RRGGBB 或 #AARRGGBB（带 # 必须加引号）",
    "sub-back-color": "#RRGGBB 或 #AARRGGBB（带 # 必须加引号）",
    "sub-shadow-color": "#RRGGBB 或 #AARRGGBB（带 # 必须加引号）",
    "geometry": "WxH+X+Y，或 50%:50%",
    "autofit": "WxH 或 百分比（如 100%x100%）",
    "autofit-larger": "WxH 或 百分比",
    "autofit-smaller": "WxH 或 百分比",
    "glsl-shaders": "分号分隔的路径列表",
    "glsl-shader": "单个 .glsl 路径（追加）",
    "sub-file-paths": "分号分隔的目录名",
    "audio-file-paths": "分号分隔的目录名",
    "vf": '如 vapoursynth="~~/vs/x.vpy"',
    "af": "如 lavfi=[dynaudnorm]",
    "watch-later-options": "逗号分隔的属性名",
    "screenshot-template": "支持 %{属性} 展开",
    "sub-font": "字体名（要先装到 fonts\\ 或系统里）",
}

_DEFAULT_IN_SIG = re.compile(r"\(default:\s*([^)]*)\)", re.IGNORECASE)
# 中文说明尾巴上的「（默认： x）」有十来种写法（空格位置不同），统一剥掉
_DEFAULT_IN_DESC = re.compile(r"[（(]\s*默认\s*[：:][^）)]*[）)]")


@lru_cache(maxsize=1)
def _db():
    """全量选项库（读不到就退化成空字典，一切照常工作）。"""
    try:
        from .options_db import load_db
        return load_db().get("options") or {}
    except Exception:
        return {}


def db_entry(key):
    return _db().get(key)


def default_in_sig(key):
    """从 raw_sig 里取默认值（取不到返回空串）。"""
    entry = db_entry(key) or {}
    m = _DEFAULT_IN_SIG.search(str(entry.get("raw_sig") or ""))
    return (m.group(1) or "").strip() if m else ""


def strip_default_suffix(text):
    """去掉中文说明尾巴上的「（默认： x）」。"""
    return _DEFAULT_IN_DESC.sub("", str(text or "")).strip()


def first_sentence(text, limit):
    """压成一句、并截到 limit 字（超了加省略号）。

    先按中文句号切，再按分号切；都不行就硬截 —— 目标是"读得懂一眼"，
    不是"保留全部细节"（细节在界面的说明抽屉里）。
    """
    s = strip_default_suffix(text).replace("\n", " ").strip()
    if not s:
        return ""
    for sep in ("。", "；", ";"):
        idx = s.find(sep)
        if 0 < idx <= limit:
            return s[:idx + 1]
    if len(s) <= limit:
        return s
    return s[:limit].rstrip("，,、 ") + "…"


def curated_desc(key):
    """精选层的中文说明（工具自己写的那句话）。"""
    meta = get_param_meta(key)
    if meta:
        return str(meta[2] or "").strip()
    return ""


def option_note(key, style="above"):
    """这个选项的一句话中文说明（查不到返回空串 —— **不编造**）。

    style: "above" 用 90 字上限，"inline" 用 56 字。
    """
    limit = ABOVE_LIMIT if style == "above" else INLINE_LIMIT
    # 精选层的话是工具自己写的，本来就短，优先用
    desc = curated_desc(key)
    if not desc:
        entry = db_entry(key) or {}
        desc = entry.get("zh_desc") or ""
    return first_sentence(desc, limit)


def option_hint(key):
    """格式提示（推不出来返回空串）。

    来源优先级：手工补的特殊项 → 精选层建议值 → 枚举取值表 → 全量库 range → raw_sig。
    """
    if key in EXTRA_HINTS:
        return EXTRA_HINTS[key]
    entry = db_entry(key) or {}

    # 精选层的建议值：挑几个代表值，比"0.001 to 100"更好懂。
    # 太多就只取前几个（和枚举分支一个规矩），否则一行能到 200 列。
    meta = get_param_meta(key)
    if meta:
        values = [str(v) for v in (meta[3] or []) if str(v).strip()]
        if values:
            if len(values) <= 4:
                return " / ".join(values)
            return " / ".join(values[:5]) + " / …"

    # 枚举类：把可选值列出来（太多就取前 5 个 + 省略号）
    raw_low = str(entry.get("raw_sig") or "").lower()
    if "choice" in raw_low or str(entry.get("type") or "").lower() in ("choice", "choices"):
        choices = [str(c) for c in (entry.get("choices") or []) if str(c).strip()]
        if choices:
            head = " / ".join(choices[:5])
            return head + (" / …" if len(choices) > 5 else "")

    rng = str(entry.get("range") or "").strip()
    if rng:
        return rng.replace(" to ", " ~ ")

    for frag in _SIG_HINTS:
        if frag in raw_low:
            if "file" in frag:
                return "文件路径"
            if "geometry" in frag:
                return "WxH+X+Y，或 50%:50%"
            if "list" in frag:
                return "列表（见手册该选项的语法）"
            if "path" in frag or "directory" in frag:
                return PATH_HINT
            return "见 mpv 手册"
    return ""


def note_for(key, style="above", with_hint=True):
    """合成一行注释文本（不含 `#`）。查不到就返回空串。"""
    note = option_note(key, style=style)
    hint = option_hint(key) if with_hint else ""
    if note and hint:
        return f"{note}（{hint}）"
    return note or (f"（{hint}）" if hint else "")


def coverage(keys=None):
    """统计说明覆盖率（给文档/界面用，便于回答"到底能注多少项"）。"""
    keys = list(keys) if keys is not None else list(_db().keys())
    if not keys:
        keys = [item[0] for items in PARAMS.values() for item in items]
    have = [k for k in keys if option_note(k)]
    hints = [k for k in keys if option_hint(k)]
    return {"total": len(keys), "with_note": len(have), "with_hint": len(hints),
            "missing": sorted(set(keys) - set(have))}


# ---------------------------------------------------------------- 特殊行

SPECIAL = {
    "include": "引入另一个配置文件（相对 ~~/ 即配置目录）",
    "include-append": "再引入一个配置文件",
    "profile-desc": "这个 profile 的说明文字",
    "profile-cond": "满足条件时这个 profile 才生效",
    "profile-restore": "这个 profile 结束时如何还原状态",
}


def special_note(line_key):
    """`include` / profile 元信息这类不是普通选项的行。"""
    return SPECIAL.get(line_key, "")


__all__ = [
    "option_note", "option_hint", "note_for", "coverage", "special_note",
    "SPECIAL", "INLINE_LIMIT", "ABOVE_LIMIT", "EXTRA_HINTS",
    "db_entry", "default_in_sig", "strip_default_suffix", "first_sentence",
]
