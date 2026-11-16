# -*- coding: utf-8 -*-
"""mpv 全量选项数据库：解析 ``mpv --list-options`` 原始输出 + mpv 官方手册中文翻译。

两个数据来源：

1. ``_mpv_options_raw.txt``：``mpv.com --list-options`` 的原始输出。
   顶层选项行前导一个空格，形如::

        --deband-iterations              Integer (0 to 16) (default: 1)

   子选项行缩进 4 个空格（如 ``    --ad-lavc-o-add``），归入其上方的顶层选项。
2. ``mpv_doc-CN/official_man/options.rst``：官方手册中文翻译（GPL-3.0）。
   选项定义行形如 ````--deband-iterations=<0..16>````，其后缩进的段落是中文说明；
   ``====`` / ``----`` 组成的上一级标题即该选项所属分类。

公共接口：

* :func:`build_db` —— 重新解析两个来源并合并，返回数据库字典
* :func:`load_db` —— 读取已生成的 JSON（带缓存），失败时返回空库
* :func:`search` —— 按选项名 / 中文说明 / 中文标题模糊搜索
* :data:`DB_PATH` —— JSON 数据文件路径

只依赖标准库。
"""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path

# --------------------------------------------------------------------------
# 路径
# --------------------------------------------------------------------------
from .paths import bundle_root, data_dir    # noqa: E402

CORE_DIR = Path(__file__).resolve().parent
# 打包后 data/ 与 data/_mpv_options_raw.txt 在解包目录里（见 core/paths.py）
REPO_ROOT = bundle_root()

DB_PATH = data_dir() / "mpv_options_zh.json"
#: 原始选项输出的文件名（2026-11-17 从仓库根目录搬进 data/，根目录只留五个文档）
RAW_NAME = "_mpv_options_raw.txt"
RAW_PATH = data_dir() / RAW_NAME
# 中文手册的来源文件在**作者机器**上，不在仓库里 —— 只有重新生成选项库时才需要。
# 用环境变量 DSH_MPV_OPTIONS_RST 指到自己的那份；指不到也不影响读取已生成的 JSON。
RST_PATH = Path(os.environ.get("DSH_MPV_OPTIONS_RST")
                or (Path.home() / "mpv_doc-CN" / "official_man" / "options.rst"))

#: 中文说明长度上限
ZH_DESC_LIMIT = 600

#: 中文说明的段落分隔符（原文是 RST 的多个缩进段落，压成一段自然中文）
_ZH_JOIN = "。"

EMPTY_DB = {"options": {}, "groups": [], "meta": {}}


# --------------------------------------------------------------------------
# 小工具
# --------------------------------------------------------------------------
def _read_lines(path) -> list:
    """读 UTF-8 文本，返回按行列表（容忍 BOM，兼容 CRLF/LF）。"""
    text = Path(path).read_text(encoding="utf-8-sig")
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def _resolve_raw_path(raw_txt_path=None):
    """定位原始选项文件：显式参数 > 环境变量 > 仓库内默认位置。"""
    if raw_txt_path:
        return Path(raw_txt_path)
    env = os.environ.get("DSH_MPV_RAW_OPTIONS")
    if env:
        return Path(env)
    if RAW_PATH.exists():
        return RAW_PATH
    # 兼容旧布局：以前的仓库根目录 / 解包目录里直接放这份文件（2026-11-17 前）
    for parent in [REPO_ROOT] + list(REPO_ROOT.parents):
        cand = parent / RAW_NAME
        if cand.exists():
            return cand
    return RAW_PATH


def _resolve_rst_path(rst_path=None):
    """定位中文手册 options.rst：显式参数 > 环境变量 > 默认绝对路径。"""
    if rst_path:
        return Path(rst_path)
    env = os.environ.get("DSH_MPV_OPTIONS_RST")
    if env:
        return Path(env)
    return RST_PATH


def _resolve_en_rst_path(en_rst_path=None):
    """定位**官方英文**手册 options.rst（第 5 项：选项英文说明）。

    与中文源对称：中文来自 mpv_doc-CN 的翻译，英文取 mpv 官方仓库原文——
    比翻译准，也比翻译省事（2026-09-14 拍板的第 7 条，见 ``DECISIONS.md``）。缺省找
    ``~/mpv_doc-en/options.rst``（官方 DOCS/man/options.rst 的单文件副本）；
    找不到返回 None——**没有英文源就照常出库，只是没有 en_desc**，不报错。
    """
    if en_rst_path:
        return Path(en_rst_path)
    env = os.environ.get("DSH_MPV_OPTIONS_EN_RST")
    if env:
        return Path(env)
    p = Path.home() / "mpv_doc-en" / "options.rst"
    return p if p.is_file() else None


def _uniq(seq):
    """保序去重。"""
    seen = set()
    out = []
    for item in seq:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


# --------------------------------------------------------------------------
# 1) 解析 mpv --list-options 原始输出
# --------------------------------------------------------------------------
# 顶层行的类型关键词（按长度降序匹配，避免 "Choice" 抢走 "Choices:"）
_RAW_TYPES = (
    "Choices:",
    "Object settings list",
    "Key/value list",
    "Relative time or percent position",
    "Audio channels or channel map",
    "String list",
    "Integer64",
    "Integer",
    "ByteSize",
    "Window size",
    "Image format",
    "Audio format",
    "Double",
    "Float",
    "Color",
    "Time",
    "Flag",
    "String",
    "Choice",
    "Object",
    "Aspect",
    "Print",
    "removed",
    "alias",
)
# 按长度降序匹配，长关键词优先（"Object settings list" 先于 "Object"）。
# 注意不能用 \b 收尾："Choices:" 后面若接空格，\b 永远不成立。
_RAW_TYPE_RE = re.compile(
    r"^("
    + "|".join(re.escape(k) for k in sorted(_RAW_TYPES, key=len, reverse=True))
    + r")(?![A-Za-z0-9_])"
)
_RANGE_RE = re.compile(
    r"^(?:-?[\w.]+\s+to\s+-?[\w.]+|to\s+any|any|\d*\s*to\s*\d*)$", re.IGNORECASE
)
_PAREN_RE = re.compile(r"\(([^()]*)\)")


def _split_parens(body):
    """按最外层括号切分，返回 (括号外的头部, [括号内文本, ...])。"""
    head = []
    groups = []
    depth = 0
    buf = []
    for ch in body:
        if ch == "(":
            depth += 1
            if depth == 1:
                buf = []
                continue
        elif ch == ")":
            if depth == 1:
                groups.append("".join(buf))
                buf = []
            depth = max(0, depth - 1)
            if depth == 0:
                continue
        if depth:
            buf.append(ch)
        else:
            head.append(ch)
    return "".join(head).strip(), groups


def _parse_raw_text(text):
    """解析 ``--list-options`` 输出，返回 (顶层选项字典, 子选项列表)。"""
    top = {}
    subs = []
    order = []
    cur_key = None

    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if not line.strip():
            continue
        if re.match(r"^ {2,}--", line):
            name = line.strip().split()[0]
            if name.startswith("--"):
                key = name[2:]
                if cur_key is not None:
                    top[cur_key]["sub_options"].append(name)
                subs.append(key)
            continue
        m = re.match(r"^ --(\S+)\s*(.*)$", line)
        if not m:
            continue  # 页眉 "Options:" / 页脚 "Total: N options"
        key, body = m.group(1), m.group(2).strip()
        entry = {
            "key": key,
            "raw_sig": body,
            "type": "",
            "range": "",
            "default": "",
            "choices": [],
            "flags": [],
            "deprecated": False,
            "sub_options": [],
        }
        _fill_raw_type(entry, body)
        top[key] = entry
        order.append(key)
        cur_key = key

    return {"options": top, "order": order}, _uniq(subs)


def _fill_raw_type(entry, body):
    """从 "Integer (0 to 16) (default: 1)" 这类文本里拆出类型/取值/默认值。"""
    entry["raw_sig"] = body
    if "[deprecated]" in body:
        entry["deprecated"] = True
    entry["flags"] = re.findall(r"\[([^\[\]]+)\]", body)
    body = re.sub(r"\[[^\[\]]*\]", " ", body).strip()

    head, groups = _split_parens(body)
    m = _RAW_TYPE_RE.match(head)
    if not m:
        entry["type"] = head or "Unknown"
        return

    keyword = m.group(1).strip()
    if keyword == "Choices:":
        entry["type"] = "Choice"
        entry["choices"] = head[len(keyword):].split()
    elif keyword == "alias":
        entry["type"] = "Alias"
        # 形如 "alias for aid" / "alias for --audio-files-append (CLI/config files only)"
        entry["default"] = re.sub(r"^alias\s+for\s+", "", head).strip(" -")
    elif keyword == "removed":
        entry["type"] = "removed"
    else:
        entry["type"] = keyword

    ranges = []
    for group in groups:
        g = group.strip()
        if g.startswith("default:"):
            entry["default"] = g[len("default:"):].strip()
        elif g and _RANGE_RE.match(g):
            ranges.append(g)
    entry["range"] = ", ".join(ranges)
    if not entry["type"]:
        entry["type"] = "Unknown"


# --------------------------------------------------------------------------
# 2) 解析中文手册 options.rst
# --------------------------------------------------------------------------
_HEADING_RE = re.compile(r"^([=\-~^*+#\"]{3,})\s*$")
# 选项定义行里的 ``--xxx`` 片段
_OPT_TOKEN_RE = re.compile(r"``(--[A-Za-z0-9_{}\-]+)(=[^`]*?)?``")
# 同上，但容忍单反引号（手册里个别行的笔误）
_OPT_TOKEN_LOOSE_RE = re.compile(r"`(--[A-Za-z0-9_{}\-]+)(=[^`]*?)?`+")
# 整行就是 "``--长选项, -X``" 这种带短别名的写法
_SHORT_ALIAS_LINE_RE = re.compile(r"^`+\s*(--[A-Za-z0-9_{}\-]+)\s*,\s*(-[A-Za-z0-9])\s*`+$")
# 逗号后面的裸选项（第二个起没有反引号），如 ``--gpu-tex-pad-x``, ``--gpu-tex-pad-y``
# 也用于整行是 "``--vd-queue-max-bytes=<bytesize>``, ``--ad-queue-max-bytes``" 的情况
_OPT_BARE_RE = re.compile(r",\s*(--[A-Za-z0-9_{}\-]+)(=[^,`\s]*)?")
# 裸写的短别名，如 --version, -V
_SHORT_ALIAS_RE = re.compile(r"(?<=,)\s*(-[A-Za-z0-9])(?=[\s,;:]|$)")
# 反引号之外只允许出现：逗号开头的裸选项 / 短别名，以及标点空白
_BARE_ONLY_RE = re.compile(
    r"(?:(?:,\s*--[A-Za-z0-9_{}\-]+(?:=[^\s,`]*)?)|(?:,\s*-[A-Za-z0-9])|[\s,;:。]*)+"
)
# 定义行尾部的括号补充说明，如 ``--vd-lavc-fast`` （MPEG-1/2和H.264独占）
_TRAIL_NOTE_RE = re.compile(
    r"[\s(（]+[^()（）]*?(?:独占|只读|已废弃|deprecated|仅|alias|别名)[^()（）]*[)）]\s*$"
)
# 同上，但容忍中英文括号混用
_TRAIL_NOTE_MIXED_RE = re.compile(
    r"[\s(（]+[^()（）]*?(?:独占|只读|已废弃|deprecated|仅|alias|别名)[^()（）]*\s*[)）]\s*$"
)
# 行内代码（含跨行续行）
_INLINE_CODE_RE = re.compile(r"``(.+?)``", re.DOTALL)
# 交叉引用 `列表选项`_
_REF_RE = re.compile(r"`([^`<>]+?)`_")
# 其它 RST 行内标记（**粗体** / *斜体*）
_MARKUP_RE = re.compile(r"\*\*(.+?)\*\*|\*([^*\n]+?)\*(?!\*)")
# RST 指令块（.. note:: / .. admonition:: 示例 / .. warning:: ...）
_DIRECTIVE_RE = re.compile(r"^\s*\.\.\s+([A-Za-z][A-Za-z0-9_\-]*)::")
_DROP_DIRECTIVES = {"note", "warning", "admonition", "seealso", "deprecated", "caution"}
# 中文（含全角）句末标点：拼接段落时不再补句号
_CN_END = "。！？；：、，,.!?;:）)》」』\"'"
# 段落开头的 RST 行内标记残留
_LEAD_STRIP = "`*_ \t"


def _rst_heading_lines(lines):
    """返回 [(行号(0 基), 下划线字符, 标题文本)]：标题下一行由 ==== / ---- 组成。"""
    out = []
    for i in range(len(lines) - 1):
        text = lines[i].strip()
        if not text or len(text) > 80:
            continue
        m = _HEADING_RE.match(lines[i + 1])
        if m:
            out.append((i, m.group(1)[0], text))
    return out


def _strip_rst_inline(text):
    """清掉行内代码/引用/粗斜体等 RST 标记，保留文字本身。"""
    if "``" in text:
        # 行内代码跨行时，行尾与续行首的空白要一起吃掉
        text = re.sub(r"``\s*\n\s*", "", text)
        text = re.sub(r"\s*``", "", text)
    text = _REF_RE.sub(r"\1", text)
    text = _MARKUP_RE.sub(lambda m: m.group(1) or m.group(2), text)
    text = text.replace("\\", "")
    text = re.sub(r"[ \t]+", " ", text).strip()
    return text.strip(_LEAD_STRIP)


def _collect_body(lines, start, stop):
    """收集 [start, stop) 之间的正文段落，跳过指令块（note/warning/示例）。"""
    paras = []
    buf = []
    skipping = False
    skip_indent = 0

    def flush():
        if buf:
            text = _strip_rst_inline(" ".join(buf).strip())
            if text:
                paras.append(text)
            del buf[:]

    for idx in range(start, stop):
        line = lines[idx].rstrip()
        stripped = line.strip()
        if not stripped:
            if not (skipping and (len(line) - len(line.lstrip(" "))) > skip_indent):
                flush()
            continue
        indent = len(line) - len(line.lstrip(" "))
        if skipping:
            if indent > skip_indent:
                continue
            skipping = False  # 指令块结束，本行按正文处理
        m = _DIRECTIVE_RE.match(line)
        if m and m.group(1) in _DROP_DIRECTIVES:
            flush()
            skipping = True
            skip_indent = indent
            continue
        if stripped.startswith(".."):
            continue  # 其它 RST 注释 / 锚点，整行丢掉
        if stripped.startswith(":") and re.match(r"^:\S+:", stripped):
            continue  # 定义列表字段（如 :none: 从不跳过），不是正文
        buf.append(stripped)

    flush()
    return _uniq(paras)


def _join_zh(paras, limit=ZH_DESC_LIMIT):
    """把多段说明压成一段自然中文，长度不超过 limit。"""
    pieces = []
    for para in paras:
        para = para.strip()
        if not para:
            continue
        if pieces and pieces[-1][-1] not in _CN_END:
            pieces.append(_ZH_JOIN)
        pieces.append(para)
    text = "".join(pieces).strip()
    if limit and len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def _collect_tokens(line, pattern):
    """用给定正则收集一行里的 (``--name``, ``=签名``)。"""
    return [(m.group(1), m.group(2)) for m in pattern.finditer(line)]


def _def_line_tokens(line):
    """判断一行是不是选项定义行；是则返回 [(``--name``, ``=签名``), ...]。

    容错点：手册里个别行有笔误（如 `` `--screen-name=<string>``` `` 少了一个反引号），
    以及 ``--a``, ``--b`` 这种第二个选项不带反引号的写法。
    """
    line = _TRAIL_NOTE_RE.sub("", line)
    # 中英文括号混用时上面的正则可能不匹配，再补一刀
    m_note = _TRAIL_NOTE_MIXED_RE.search(line)
    if m_note:
        line = line[: m_note.start()]
    # 定义行必须以反引号开头（允许手册里少打一个反引号的笔误）
    if not line.strip().startswith("`"):
        return None

    tokens = _collect_tokens(line, _OPT_TOKEN_RE)
    short_line = _SHORT_ALIAS_LINE_RE.match(line.strip())
    if short_line:
        tokens += [(short_line.group(1), None), (short_line.group(2), None)]
    if not tokens:
        # 如 `--screen-name=<string>``` ，反引号打错了，放宽再试一次
        tokens = _collect_tokens(line, _OPT_TOKEN_LOOSE_RE)
    if not tokens:
        return None

    # 去掉反引号片段后，剩下的只能是"裸选项 / 短别名 / 标点空白"
    outside = line
    for pattern in (_OPT_TOKEN_RE, _OPT_TOKEN_LOOSE_RE):
        outside = pattern.sub(" ", outside)
    if short_line:
        outside = _SHORT_ALIAS_LINE_RE.sub(" ", outside)
    if not _BARE_ONLY_RE.fullmatch(outside):
        return None

    for name, sig in _OPT_BARE_RE.findall(outside):
        if name not in [t[0] for t in tokens]:
            tokens.append((name, sig))
    for alias in _SHORT_ALIAS_RE.findall(outside):
        if alias not in [t[0] for t in tokens]:
            tokens.append((alias, None))
    return tokens or None


def _parse_rst_text(text):
    """解析中文手册，返回 ({选项名: {...}}, [章节顺序的分类名])。"""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    headings = _rst_heading_lines(lines)

    # 第一个标题是文档大标题（"选项" / "===="），其余标题才是分类。
    # 若第一个标题之下还有更深一级的标题，则以最深一级为准。
    rest = headings[1:]
    if rest:
        chars = [ch for _, ch, _ in rest]
        level = max(chars, key=chars.count)
        groups = [(ln, title) for ln, ch, title in rest if ch == level]
    else:
        groups = [(ln, title) for ln, _ch, title in headings]

    result = {}
    group_order = [title for _ln, title in groups]
    if not groups:
        return result, group_order

    bounds = [
        (ln, title, groups[i + 1][0] if i + 1 < len(groups) else len(lines))
        for i, (ln, title) in enumerate(groups)
    ]
    headings_at = {ln for ln, _ch, _t in headings}

    for head_ln, group, stop in bounds:
        i = head_ln + 2  # 跳过标题行 + 下划线行
        while i < stop:
            if i in headings_at:
                i += 2
                continue
            tokens = _def_line_tokens(lines[i])
            if not tokens:
                i += 1
                continue
            # 本条定义的结束位置：下一个定义行 / 标题行
            end = i + 1
            while end < stop:
                if end in headings_at:
                    break
                if _def_line_tokens(lines[end]):
                    break
                end += 1
            desc = _join_zh(_collect_body(lines, i + 1, end))
            for name, sig in tokens:
                # 短别名（-V / -v）在 --list-options 里就是单横线，去掉前导横线即可
                key = name[2:] if name.startswith("--") else name.lstrip("-")
                entry = result.setdefault(
                    key, {"zh_sig": "", "zh_desc": "", "group": group}
                )
                if sig and not entry["zh_sig"]:
                    entry["zh_sig"] = name + sig
                if desc and not entry["zh_desc"]:
                    entry["zh_desc"] = desc
            i = end
    return result, group_order


# --------------------------------------------------------------------------
# 3) 合并
# --------------------------------------------------------------------------
def build_db(raw_txt_path=None, rst_path=None, en_rst_path=None):
    """解析两个来源并合并，返回数据库字典。

    :param raw_txt_path: ``mpv --list-options`` 输出路径，缺省用仓库内的文件
    :param rst_path: 中文手册 options.rst 路径，缺省用默认中文文档路径
    :param en_rst_path: **官方英文**手册 options.rst 路径（第 5 项），
        缺省找 ``~/mpv_doc-en/options.rst``；找不到就没有 en_desc，不报错
    :returns: ``{"meta": {...}, "groups": [...], "options": {...}}``
    """
    raw_file = _resolve_raw_path(raw_txt_path)
    rst_file = _resolve_rst_path(rst_path)
    en_file = _resolve_en_rst_path(en_rst_path)

    raw_options, _subs = _parse_raw_text(raw_file.read_text(encoding="utf-8-sig"))
    rst_map, rst_groups = _parse_rst_text(rst_file.read_text(encoding="utf-8-sig"))
    # 第 5 项：官方英文原文用**同一个解析器**——mpv_doc-CN 就是按它的结构翻的，
    # 实测 723/726 命中（3 条是官方已更名的别名，回退中文）
    en_map = {}
    if en_file is not None:
        en_map, _en_groups = _parse_rst_text(en_file.read_text(encoding="utf-8-sig"))

    options = {}
    with_zh = 0
    with_en = 0
    used = set()
    for key in raw_options["order"]:
        src = raw_options["options"][key]
        zhs = rst_map.get(key, {})
        zh_desc = zhs.get("zh_desc", "") or ""
        group = zhs.get("group") or "其它"
        if zh_desc:
            with_zh += 1
        en_desc = (en_map.get(key, {}).get("zh_desc") or "") if en_map else ""
        if en_desc:
            with_en += 1
        used.add(group)
        options[key] = {
            "key": key,
            "type": src["type"],
            "range": src["range"],
            "default": src["default"],
            "choices": list(src["choices"]),
            "deprecated": bool(src["deprecated"]),
            "sub_options": list(src["sub_options"]),
            "group": group,
            "zh_sig": zhs.get("zh_sig", "") or "",
            "zh_desc": zh_desc,
            "en_desc": en_desc,
            # 便于排查的原始信息（raw 行的类型描述 + 方括号标记）
            "raw_sig": src.get("raw_sig", ""),
            "flags": list(src.get("flags", [])),
        }

    # 分类顺序照中文手册的章节顺序，未归类的"其它"排最后
    groups = [g for g in rst_groups if g in used and g != "其它"]
    for g in rst_groups:  # 手册里没出现过的分类兜底（正常不会有）
        if g in used and g not in groups and g != "其它":
            groups.append(g)
    if "其它" in used:
        groups.append("其它")

    meta = {
        "source_mpv": "data/_mpv_options_raw.txt（mpv --list-options 输出）",
        "source_zh": "mpv_doc-CN official_man/options.rst",
        "source_en": ("mpv 官方 DOCS/man/options.rst（~/mpv_doc-en/）" if en_map else ""),
        "license_note": "中文说明来自 mpv_doc-CN，GPL-3.0；本文件是其衍生数据。"
                        "英文说明来自 mpv 官方手册（GPL-2.0+/LGPL-2.1+）",
        "count": len(options),
        "with_zh": with_zh,
        "with_en": with_en,
    }
    return {"meta": meta, "groups": groups, "options": options}


#: 不在配置文件里生效的选项（mpv 的 dump 自己标注 `[not in config files]`）。
#: 实测来源：`mpv --list-options` 里有 `--V` / `--{` / `--}` 三条，raw_sig 都带
#: `[not in config files]` —— 它们只用于命令行。放进"完全体"会误导用户
#: 往 mpv.conf 里写，所以读取时滤掉。
#:
#: 这个发现来自拿官方手册（mpv_CFanStation 的 official_man）反向核对选项库：
#: 库里有 3 项在手册正文里找不到，查下来是这三条命令行专用的。
NOT_IN_CONFIG_FILES = ("V", "{", "}")


def is_config_option(key, entry=None):
    """这个选项能不能写进 mpv.conf。"""
    if key in NOT_IN_CONFIG_FILES:
        return False
    if entry is not None:
        sig = str((entry or {}).get("raw_sig") or "").lower()
        if "[not in config files]" in sig:
            return False
    return True


# --------------------------------------------------------------------------
# 4) 读取 / 搜索
# --------------------------------------------------------------------------
@lru_cache(maxsize=1)
def load_db():
    """读取 :data:`DB_PATH` 指向的 JSON（带缓存）。

    文件缺失或损坏时返回空库 ``{"options": {}, "groups": [], "meta": {}}``。
    **读取时会滤掉不能写进配置文件的选项**（见 :data:`NOT_IN_CONFIG_FILES`），
    并把 meta.count 同步成滤完的真实条数 —— 免得界面上说"829 项"、实际只能填 826。
    """
    try:
        with open(DB_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {"options": {}, "groups": [], "meta": {}}
    if not isinstance(data, dict):
        return {"options": {}, "groups": [], "meta": {}}
    raw_options = data.get("options") or {}
    options = {k: v for k, v in raw_options.items() if is_config_option(k, v)}
    meta = dict(data.get("meta") or {})
    if len(options) != len(raw_options):
        meta["count"] = len(options)
        meta["filtered"] = len(raw_options) - len(options)
        meta["filtered_note"] = ("滤掉了命令行专用选项（mpv 标注 not in config files）："
                                 + "、".join(sorted(set(raw_options) - set(options))))
        # with_zh 是**过滤前**统计的，滤完就过期了 —— 继续用它会让界面宣称
        # 「726 条中文说明」而实际滤完只剩 714 条。count 已经同步了，它没同步。
        meta["with_zh"] = sum(1 for v in options.values() if v.get("zh_desc"))
        meta["with_en"] = sum(1 for v in options.values() if v.get("en_desc"))
    return {
        "meta": meta,
        "groups": list(data.get("groups") or []),
        "options": options,
    }


def reset_cache():
    """清掉 :func:`load_db` 的缓存（重新生成 JSON 后调用）。"""
    load_db.cache_clear()


def _match_rank(entry, needle):
    """命中位置评分：0 选项名完全相同 > 1 选项名前缀 > 2 选项名包含
    > 3 分类名 > 4 中文签名 > 5 中文说明；未命中返回 None。"""
    key = (entry.get("key") or "").lower()
    if key == needle:
        return 0
    if key.startswith(needle):
        return 1
    if needle in key:
        return 2
    if needle in (entry.get("group") or "").lower():
        return 3
    if needle in (entry.get("zh_sig") or "").lower():
        return 4
    if needle in (entry.get("zh_desc") or "").lower():
        return 5
    return None


def search(db, keyword, limit=None):
    """按选项名 / 中文说明 / 中文标题模糊搜索。

    结果按命中位置排序：选项名精确命中排最前，其次前缀、包含，再是分类、
    中文签名、中文说明；同一档次内保持数据库原有顺序。

    :param db: :func:`build_db` 或 :func:`load_db` 返回的数据库
    :param keyword: 关键词（大小写不敏感，中文原样匹配）
    :param limit: 最多返回多少条，None 表示不限
    :returns: 命中的选项字典列表
    """
    if not keyword:
        return []
    needle = str(keyword).strip().lower()
    if not needle:
        return []
    options = (db or {}).get("options") or {}
    scored = []
    for index, (key, entry) in enumerate(options.items()):
        rank = _match_rank(entry, needle)
        if rank is not None:
            scored.append((rank, index, entry))
    scored.sort(key=lambda item: (item[0], item[1]))
    hits = [entry for _rank, _index, entry in scored]
    return hits if limit is None else hits[:limit]


if __name__ == "__main__":  # pragma: no cover - 手动调试用
    import sys

    _db = load_db()
    if not _db["options"]:
        _db = build_db()
    print(
        "顶层 %d 项 / 有中文 %d 项 / 分类 %d 个"
        % (_db["meta"].get("count", 0), _db["meta"].get("with_zh", 0), len(_db["groups"]))
    )
    if len(sys.argv) > 1:
        for hit in search(_db, sys.argv[1], limit=20):
            print("  --%s  [%s]  %s" % (hit["key"], hit["group"], hit["zh_desc"][:60]))
