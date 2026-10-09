# -*- coding: utf-8 -*-
"""给已有配置补注释（R-28）。

**交互原则（用户明确要求过）**：补注释是「用户主动选的动作」，不是上传的副作用。
上传 / 选文件永远只读分析（`core/report.py`），一个字节都不改；
只有用户显式点了「✍️ 补注释」才走这里，而且默认只出预览、不落盘。

**七条设计决定**（2026-09-14 定；设计稿所在的那份文档已经拆了，
原文在 git 历史里，有效性以这里的清单与测试为准）：

1. 默认另存副本（`原名.说明版.conf`），写回原文件要二次确认
2. 默认「行尾注释」，可切「上方注释」
3. **已有注释的行绝不改** —— 行首 `#`、已有行尾 `#`、空行、`####` 分隔线一律原样保留
4. **查不到说明的留白，不编造**（在 `stats.missing` 里列出来）
5. 特殊行单独话术：`include` / `[小节]` / `glsl-shaders` / `vf=vapoursynth=`
6. 长度分档：行尾 40–60 字，上方可到 90 字
7. 做成「配置体检」页的一个动作
"""
import re

from .notes import INLINE_LIMIT, ABOVE_LIMIT, note_for
from .schema import strip_inline_comment

# 已经是注释的行 / 空行：一律不碰
COMMENT_RE = re.compile(r"^\s*[#;]")
SECTION_RE = re.compile(r"^\s*\[(?P<name>[^\]]+)\]\s*$")
# 分隔线（#### / ==== / ----）：也算注释，别去动它
RULE_RE = re.compile(r"^\s*[#;]?\s*[-=_*~#]{4,}\s*$")
# 键值行（允许 `--key=value` 写法）
KEY_RE = re.compile(r"^(?P<indent>\s*)(?P<dash>--)?(?P<key>[A-Za-z0-9_.\-]+)\s*=\s*(?P<value>.*)$")
BARE_RE = re.compile(r"^(?P<indent>\s*)(?P<key>[A-Za-z][A-Za-z0-9_.\-]*)\s*$")

# 这些键的说明要按特殊话术来（不查库）
SPECIAL_KEYS = {
    "glsl-shaders": "着色器链：按顺序依次处理，写在后面的最后生效",
    "glsl-shader": "往着色器链尾部追加一个（不覆盖已有的）",
    "glsl-shaders-append": "往着色器链尾部追加（不覆盖已有的）",
    "vf": "视频滤镜链。写 vapoursynth=… 就是挂补帧/超分脚本",
    "vf-append": "往视频滤镜链尾部追加一条",
    "af": "音频滤镜链",
    "af-append": "往音频滤镜链尾部追加一条",
    "input-conf": "快捷键文件的位置",
    "profile-desc": "这个 profile 的说明",
    "profile-cond": "条件满足时这个 profile 才生效",
    "profile-restore": "这个 profile 结束时如何还原状态",
}

def _has_inline_comment(line):
    """这一行已经有行尾注释了吗。

    用和解析器同一套规则（引号内的 # 不算注释），保证"有注释就不动"和
    "mpv 怎么看这一行"判断一致。
    """
    idx = line.find("=")
    if idx < 0:
        return False
    value_part = line[idx + 1:]
    stripped = strip_inline_comment(value_part)
    return stripped != value_part.strip()


def _note_for_key(key, style):
    if key in SPECIAL_KEYS:
        text = SPECIAL_KEYS[key]
        limit = ABOVE_LIMIT if style == "above" else INLINE_LIMIT
        return text if len(text) <= limit else text[:limit].rstrip("，,、 ") + "…"
    return note_for(key, style=style)


def annotate_text(text, style="inline", only_missing=True, with_hint=True):
    """给配置文本补中文注释。**纯函数，不碰磁盘。**

    返回 {"text": 新文本, "stats": {...}, "stats.details": {...}}

    stats 字段（《路线图》要求的那几个）：
        lines          总行数
        added          加了注释的行数
        skipped        跳过的行数（已有注释 / 空行 / 分隔线）
        missing        查不到说明、留白的行数
        profile_lines  落在 [小节] 里的**选项行**数
        include_lines  include 行数
        section_lines  [小节] 表头行数

    注意 `profile_lines` 的判定和 mpv 一致：从 `[name]` 的**下一行**起，
    直到下一个 `[next]` 或文件末尾，都算这个 profile 的（中间的空行与注释不算选项行）。
    这与 `core/loader.py` 分开返回 profile 的做法不冲突 —— loader 是为了
    "别把小节的值当全局值写回去"，这里是为了"告诉用户这行在什么作用域里生效"。
    """
    style = "above" if style == "above" else "inline"
    src_lines = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")

    out = []
    stats = {"lines": len(src_lines), "added": 0, "skipped": 0, "missing": 0,
             "profile_lines": 0, "include_lines": 0, "section_lines": 0,
             "already_commented": 0, "blank": 0}
    missing_keys = []
    current_section = None

    for line in src_lines:
        stripped = line.strip()

        # ---- 一律不碰的行 ----
        if not stripped:
            stats["skipped"] += 1
            stats["blank"] += 1
            out.append(line)
            continue
        if COMMENT_RE.match(line) or RULE_RE.match(line):
            stats["skipped"] += 1
            stats["already_commented"] += 1
            out.append(line)
            continue

        # ---- [小节] 表头 ----
        sec = SECTION_RE.match(stripped)
        if sec:
            current_section = sec.group("name").strip()
            stats["section_lines"] += 1
            if style == "above" and not _already_has_note_above(out):
                out.append(f"# ← profile「{current_section}」：只在条件满足或被调用时生效")
                stats["added"] += 1
            out.append(line)
            continue

        in_profile = current_section is not None

        # ---- 键值行 ----
        m = KEY_RE.match(line)
        key = None
        if m:
            key = m.group("key")
        elif BARE_RE.match(line):
            key = BARE_RE.match(line).group("key")     # `hwdec` 单写一行 = yes

        if key is None:
            stats["skipped"] += 1
            out.append(line)
            continue

        if in_profile:
            stats["profile_lines"] += 1
        if key in ("include", "include-append"):
            stats["include_lines"] += 1

        # 已经有行尾注释：绝不改
        if only_missing and _has_inline_comment(line):
            stats["skipped"] += 1
            stats["already_commented"] += 1
            out.append(line)
            continue

        note = _note_for_key(key, style)
        if not note:
            stats["missing"] += 1
            missing_keys.append(key)
            out.append(line)
            continue

        if style == "inline":
            out.append(f"{line}    # {note}")
        else:
            if in_profile:
                note = f"{note}（在此 profile 内生效）"
            out.append(f"# {note}")
            out.append(line)
        stats["added"] += 1

    stats["missing_keys"] = sorted(set(missing_keys))
    return {"text": "\n".join(out), "stats": stats}


def _already_has_note_above(out):
    """上一行是不是我们刚加的注释（避免重复插）。"""
    return bool(out) and out[-1].lstrip().startswith("# ← profile")


def out_name_for(path):
    """默认另存副本的文件名：`mpv.conf` → `mpv.说明版.conf`。"""
    s = str(path)
    for suffix in (".conf", ".cfg", ".txt"):
        if s.lower().endswith(suffix):
            return s[: -len(suffix)] + ".说明版" + s[-len(suffix):]
    return s + ".说明版.conf"


__all__ = ["annotate_text", "out_name_for", "SPECIAL_KEYS",
           "INLINE_LIMIT", "ABOVE_LIMIT"]
