# -*- coding: utf-8 -*-
"""读取并解析 mpv.conf，供两个界面共用。

返回的结构刻意与前端状态一致：
    {
      "values":  {key: value},      # 全局（不在任何 [小节] 里）的键
      "present": [key, ...],        # 全局区出现过的已知键
      "shaders": [path, ...],       # glsl-shaders / glsl-shader 里的路径
      "memc":    "~~/vs/x.vpy",     # vf 里的 vapoursynth 脚本
      "memc_label": "@vs:",         # vf 里带的标签（有就保留，别弄丢）
      "profiles": [ {name, keys, desc, cond, values} ],
      "is_profile_file": bool,      # 整份文件只有 [小节]，没有全局键
      "includes": [ {target, path, exists, values, ...} ],
    }

为什么单独处理 [小节]：mpv 的 `[name]` 是 profile，里面的选项只在条件满足时生效。
把它们当全局选项读进来、再写回去，等于悄悄改了播放行为 —— 这里一律分开对待。
"""
from pathlib import Path
import re as _re

from . import textio
from .schema import (
    NATIVE_TYPES, PARAMS, db_known_keys, split_mpv_list, value_truncated_by_hash,
    strip_inline_comment,
)


def _known_keys():
    """界面认识 + 全量数据库认识的键（数据库读不到就退回界面认识的那批）。"""
    keys = {item[0] for items in PARAMS.values() for item in items} | set(NATIVE_TYPES)
    return keys | db_known_keys()


KNOWN_KEYS = _known_keys()
# `glsl-shaders` 是整表替换；`glsl-shader` 只是 `glsl-shaders-append` 的别名，
# 语义是往链尾追加 —— 两者必须分开跟踪，写回时不能合并成一行。
SHADER_LIST_KEYS = {"glsl-shaders"}
SHADER_APPEND_KEYS = {"glsl-shader", "glsl-shaders-append", "glsl-shader-append"}
VF_KEYS = {"vf", "vf-append"}
AF_KEYS = {"af", "af-append"}
INCLUDE_KEYS = {"include", "include-append"}
SECTION_RE = _re.compile(r"^\[(?P<name>[^\]]+)\]\s*$")


def split_vf_label(value):
    """把 `@label:vapoursynth="x.vpy"` 拆成 (标签, 路径)，标签形如 `@vs:`。"""
    v = str(value).strip().strip('"').strip("'")
    label = ""
    m = _re.match(r"^(@[^:]*:)(.*)$", v)
    if m:
        label, v = m.group(1), m.group(2)
    idx = v.find("vapoursynth=")
    if idx >= 0:
        v = v[idx + len("vapoursynth="):]
    return label, v.strip().strip('"').strip("'")


def parse_config_text(text):
    """解析配置文本。全局键 / profile 小节 / include 行分开返回。

    values     只含「工具界面认识」的键，用来回填界面
    all_values 全局区出现过的**所有** key=value，用来做冲突检测与分析 ——
               界面不认识不代表 mpv 不认识，冲突检测必须看全量
    shader_appends  append 型 shader 键（glsl-shader / glsl-shaders-append）
               的路径，顺序保留 —— 它们与 glsl-shaders 是两种语义，写回时不能合并
    memc_kind  memc 是从哪个键来的（"vf" 或 "vf-append"）—— 写回时要回到原键，
               否则一条 vf=vapoursynth= + 一条 vf-append= 会互相覆盖
    """
    values, present, shaders = {}, [], []
    all_values, unknown_keys = {}, []
    shader_appends = []
    shader_append_key = ""
    memc, memc_label, memc_kind = "", "", ""
    vf_filters, vf_append_filters, af_filters = [], [], []
    profiles, order = [], []
    includes = []
    hash_keys = []          # 值里有没加引号的 #（会被 mpv 当注释截掉）
    current = None

    for raw_line in text.splitlines():
        s = raw_line.strip()
        if not s or s.startswith("#") or s.startswith(";"):
            continue
        sec = SECTION_RE.match(s)
        if sec:
            current = {"name": sec.group("name").strip(), "values": {},
                       "keys": [], "desc": "", "cond": "", "raw": {}}
            profiles.append(current)
            continue
        if "=" not in s:
            # mpv 手册：没有值的选项写成一行就等于 yes（例如单写一个 hwdec）
            key, value = s, "yes"
        else:
            key, value = s.split("=", 1)
            key = key.strip()
            if key.startswith("--"):
                key = key[2:]
            raw_value = value
            value = strip_inline_comment(value.strip())
            # 只报「值真的被 # 吃掉了」的行（value_truncated_by_hash），
            # 不是「这一行出现过 #」。否则我们自己生成的提示文本
            # 「（#RRGGBB 或 #AARRGGBB…）」会把一行完全正确的配置报成
            # 「# 没加引号」—— 这个假警报就是被 R-25 的注释引出来的。
            if value_truncated_by_hash(raw_value):
                hash_keys.append(key)

        if key in INCLUDE_KEYS:
            includes.append(value.strip().strip('"').strip("'"))
            continue

        # mpv 的 profile 元信息
        if current is not None and key in ("profile-desc", "profile-cond", "profile-restore"):
            current["raw"][key] = value
            if key == "profile-desc":
                current["desc"] = value
            elif key == "profile-cond":
                current["cond"] = value
            continue

        if current is not None:
            current["values"][key] = value
            current["keys"].append(key)
            if key in SHADER_APPEND_KEYS:
                current["shaders"].extend(split_mpv_list(value))
            elif key in SHADER_LIST_KEYS:
                current.setdefault("shaders_replace", []).extend(split_mpv_list(value))
            elif key in VF_KEYS:
                lbl, path = split_vf_label(value)
                if path:
                    current["memc"] = path
                    current["memc_label"] = lbl
                    current["memc_kind"] = key
            continue

        all_values[key] = value
        # 注意顺序：glsl-shaders / vf 也在全量数据库里，必须先当成「列表/脚本」处理，
        # 否则会被当普通选项塞进 values，shader 链和补帧脚本就丢了。
        if key in AF_KEYS:
            # 音频滤镜链：本工具不做界面，原样留着别动
            if str(value).strip():
                af_filters.append(str(value).strip())
        elif key in SHADER_APPEND_KEYS:
            for path in split_mpv_list(value):
                if path and path not in shader_appends:
                    shader_appends.append(path)
            if not shader_append_key:        # 记住用户原用的写法，写回时别换名字
                shader_append_key = key
        elif key in SHADER_LIST_KEYS:
            # glsl-shaders 是整表替换：覆盖之前累积的（后出现的生效）
            shaders = [p for p in split_mpv_list(value) if p]
        elif key in VF_KEYS:
            label, path = split_vf_label(value)
            if "vapoursynth=" in str(value).lower() and path:
                # 记下来源键：vf 与 vf-append 语义不同，写回要回到各自的行
                memc, memc_label, memc_kind = path, label, key
            elif str(value).strip():
                # 普通滤镜链（format=... / lavfi=[...] / crop=...）：不是 VapourSynth
                # 脚本，本工具不认识也不该改 —— 原样留着，写回时按原键吐出，
                # 否则会被当成脚本路径写进 vf=vapoursynth=，等于毁掉用户的滤镜链。
                (vf_append_filters if key == "vf-append" else vf_filters).append(str(value).strip())
        elif key in KNOWN_KEYS:
            values[key] = value
            present.append(key)
            order.append(key)
        else:
            unknown_keys.append(key)

    for prof in profiles:
        prof.setdefault("shaders", [])
        prof.setdefault("shaders_replace", [])
        prof.setdefault("memc", "")
        prof.setdefault("memc_label", "")
        prof.setdefault("memc_kind", "")
        prof.setdefault("vf_filters", [])
        prof.setdefault("vf_append_filters", [])
        prof.setdefault("af_filters", [])

    return {
        "values": values,
        "present": present,
        "order": order,
        "all_values": all_values,
        "unknown": unknown_keys,
        "hash_keys": hash_keys,
        "shaders": shaders,
        "shader_appends": shader_appends,
        "shader_append_key": shader_append_key,
        "memc": memc,
        "memc_label": memc_label,
        "memc_kind": memc_kind,
        "vf_filters": vf_filters,
        "vf_append_filters": vf_append_filters,
        "af_filters": af_filters,
        "profiles": profiles,
        "includes": includes,
        "is_profile_file": bool(profiles) and not present,
    }


# ---------------------------------------------------------------- include 链

MAX_INCLUDE_DEPTH = 8
MAX_INCLUDE_FILES = 24


def resolve_include_path(target, base_dir, root_dir):
    """把 mpv 的 include 目标解析成绝对路径。`~~/` 相对于主配置目录。"""
    t = str(target).strip().strip('"').strip("'")
    if not t:
        return None
    low = t.lower()
    if low.startswith("~~desktop/") or low.startswith("~~home/"):
        return None                       # 不是配置文件，跳过
    if t.startswith("~~/"):
        return (Path(root_dir) / t[3:]).resolve()
    if t.startswith("~~"):
        return (Path(root_dir) / t[2:].lstrip("/\\")).resolve()
    p = Path(t)
    if not p.is_absolute():
        p = Path(base_dir) / p
    return p.resolve()


def load_chain(path, root_dir=None, _seen=None, _depth=0):
    """跟着 include 一行行走下去，返回 (节点列表, 读到的文件数)。

    节点顺序 = mpv 的展开顺序，后面的覆盖前面的。缺文件不报错，只记 missing。
    """
    p = Path(path).resolve()
    if _seen is None:
        _seen = set()
    nodes = []
    if _depth > MAX_INCLUDE_DEPTH or len(_seen) >= MAX_INCLUDE_FILES:
        return nodes, len(_seen)
    if p in _seen or not p.is_file():
        return nodes, len(_seen)
    _seen.add(p)

    tf = textio.read(p)
    if tf is None:
        return nodes, len(_seen)
    root = Path(root_dir).resolve() if root_dir else p.parent
    data = parse_config_text(tf.text)
    nodes.append({
        "path": str(p),
        "name": p.name,
        "dir": str(p.parent),
        "text_file": tf,
        "values": data["values"],
        "all_values": data["all_values"],
        "unknown": data["unknown"],
        "hash_keys": data["hash_keys"],
        "present": data["present"],
        "shaders": data["shaders"],
        "shader_appends": data["shader_appends"],
        "shader_append_key": data["shader_append_key"],
        "memc": data["memc"],
        "memc_label": data["memc_label"],
        "memc_kind": data["memc_kind"],
        "vf_filters": data["vf_filters"],
        "vf_append_filters": data["vf_append_filters"],
        "af_filters": data["af_filters"],
        "profiles": data["profiles"],
        "is_profile_file": data["is_profile_file"],
        "missing": [],
    })
    for target in data["includes"]:
        child = resolve_include_path(target, p.parent, root)
        if child is None:
            continue
        if not child.is_file():
            nodes[0]["missing"].append({"target": target, "path": str(child)})
            continue
        sub, _count = load_chain(child, root, _seen, _depth + 1)
        nodes.extend(sub)
    return nodes, len(_seen)


def effective_config(path):
    """算出「mpv 实际会用到什么」：按 include 展开，后面的覆盖前面的。

    返回 {
      files:   [{name, path, count, missing, encoding}],
      values:  {key: value},               # 生效值
      sources: {key: 文件名},               # 这个值是从哪个文件来的
      shaders / memc / memc_label,          # 生效的 shader 链与 vpy
      profiles: [{name, file, keys}],
      warnings: [str],
    }
    """
    nodes, _ = load_chain(path)
    if not nodes:
        return {"files": [], "values": {}, "sources": {}, "shaders": [],
                "shader_appends": [], "shader_append_key": "",
                "memc": "", "memc_label": "", "memc_kind": "",
                "vf_filters": [], "vf_append_filters": [], "af_filters": [],
                "profiles": [], "warnings": [], "main": None, "lossy": False}
    main = nodes[0]
    files, values, sources, shaders, memc, memc_label = [], {}, {}, [], "", ""
    shader_appends = []
    shader_append_key = ""
    memc_kind = ""
    vf_filters, vf_append_filters, af_filters = [], [], []
    all_values, unknown, hash_keys = {}, [], []
    profiles, warnings = [], []
    for node in nodes:
        files.append({"name": node["name"], "path": node["path"],
                      "count": len(node["present"]),
                      "profiles": len(node["profiles"]),
                      "missing": node["missing"],
                      "encoding": node["text_file"].encoding_label})
        for key, val in node["values"].items():
            values[key] = val                 # 后面的文件覆盖前面的
            sources[key] = node["name"]
        all_values.update(node["all_values"])
        for key in node["unknown"]:
            if key not in unknown:
                unknown.append(key)
        for key in node.get("hash_keys") or []:
            if key not in hash_keys:
                hash_keys.append(key)
        if node["shaders"]:
            shaders = list(node["shaders"])   # glsl-shaders 是整表替换
        for path in node.get("shader_appends") or []:
            if path not in shader_appends:    # append 型是累加，跨文件叠加
                shader_appends.append(path)
        if not shader_append_key and node.get("shader_append_key"):
            shader_append_key = node["shader_append_key"]
        if node["memc"]:
            memc, memc_label = node["memc"], node["memc_label"]
            memc_kind = node.get("memc_kind") or "vf"
        for key, bucket in (("vf_filters", vf_filters),
                            ("vf_append_filters", vf_append_filters),
                            ("af_filters", af_filters)):
            for item in node.get(key) or []:
                if item not in bucket:       # 滤镜链是累加语义
                    bucket.append(item)
        for prof in node["profiles"]:
            profiles.append({"name": prof["name"], "file": node["name"],
                             "keys": prof["keys"], "desc": prof.get("desc", ""),
                             "cond": prof.get("cond", ""),
                             "values": prof.get("values", {})})
        if node["text_file"].lossy:
            warnings.append(f"{node['name']} 里有字节无法按 {node['text_file'].encoding} 解码，"
                            f"保底替换过，建议先另存一份再改。")
    return {
        "files": files,
        "values": values,
        "all_values": all_values,
        "unknown": unknown,
        "hash_keys": hash_keys,
        "sources": sources,
        "shaders": shaders,
        "shader_appends": shader_appends,
        "shader_append_key": shader_append_key,
        "memc": memc,
        "memc_label": memc_label,
        "memc_kind": memc_kind,
        "vf_filters": vf_filters,
        "vf_append_filters": vf_append_filters,
        "af_filters": af_filters,
        "profiles": profiles,
        "warnings": warnings,
        "main": main,
        "lossy": any(n["text_file"].lossy for n in nodes),
    }


# ---------------------------------------------------------------- 对外接口

def load_config_file(path, deep=True):
    """读一个配置文件；deep=True 时顺带把 include 链也算出来。"""
    p = Path(path)
    tf = textio.read(p)
    if tf is None:
        return {"ok": False, "detail": f"读不了这个文件：{p}"}
    data = parse_config_text(tf.text)
    data.update({
        "ok": True,
        "path": str(p),
        "name": p.name,
        "raw": tf.text,
        "bom": tf.bom,
        "encoding": tf.encoding,
        "encoding_label": tf.encoding_label,
        "lossy": tf.lossy,
        "newline": tf.newline,
    })
    if deep:
        chain = effective_config(p)
        data["chain"] = {
            "files": chain["files"],
            "sources": chain["sources"],
            "effective_count": len(chain["values"]),
            "profiles": chain["profiles"],
        }
        data["warnings"] = list(chain["warnings"])
    else:
        data["chain"] = {"files": [], "sources": {}, "effective_count": 0, "profiles": []}
        data["warnings"] = []
    if tf.lossy:
        data["warnings"].append(
            f"这个文件不是 UTF-8（识别为 {tf.encoding_label}），有字节没能解码；"
            f"写入会尽量按原编码还原，但建议先备份。")
    hashes = (data.get("chain") or {}).get("hash_keys") or data.get("hash_keys") or []
    if hashes:
        shown = "、".join(f"<{k}>" for k in hashes[:6])
        data["warnings"].append(
            f"{len(hashes)} 个选项的值里有没加引号的 #（{shown}）：mpv 规定 # 之后一律算注释，"
            f"这些值其实被截断了。写成 键=\"#值\" 才对。")
    if data["is_profile_file"]:
        data["warnings"].append(
            "这是一份 profile 集合（只有 [小节]，没有全局选项）。"
            "小节里的设置只在条件满足时生效，不能当全局配置写入。")
    return data


__all__ = ["KNOWN_KEYS", "parse_config_text", "load_config_file", "effective_config",
           "load_chain", "resolve_include_path", "split_vf_label", "split_mpv_list"]
